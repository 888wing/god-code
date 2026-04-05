"""Scenario-driven playtest harness."""

from __future__ import annotations

import copy
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.runtime.design_memory import GameplayIntentProfile, resolved_quality_target, DesignMemory
from godot_agent.runtime.runtime_bridge import (
    RuntimeEvent,
    RuntimeSnapshot,
    add_runtime_screenshot,
    advance_runtime_ticks,
    get_runtime_snapshot,
    load_runtime_scene,
    press_runtime_action,
    runtime_contract_events,
    runtime_contract_state,
    runtime_events_since,
    runtime_state_dict,
    set_runtime_fixture,
    update_runtime_snapshot,
)
from godot_agent.runtime.visual_regression import build_artifact_path, compare_image_files, resolve_baseline_path, write_failure_bundle
from godot_agent.tools.godot_cli import build_screenshot_script, resolve_godot_path


SCENARIO_DIR = Path(__file__).with_name("scenario_specs")

_NODE_SCENARIO_HINTS: dict[str, dict[str, Any]] = {
    "CharacterBody2D": {
        "required_inputs": ["move_left", "move_right", "jump"],
        "required_events": ["player_moved"],
        "path_contains": ["player", "character"],
    },
    "Area2D": {
        "path_contains": ["trigger", "pickup", "hitbox", "hurtbox"],
    },
    "AnimatedSprite2D": {
        "required_nodes_partial": True,
    },
    "AudioStreamPlayer": {
        "forbid_runtime_errors": True,
    },
    "AudioStreamPlayer2D": {
        "forbid_runtime_errors": True,
    },
    "CanvasLayer": {
        "path_contains": ["hud", "ui", "overlay"],
        "required_nodes_partial": True,
    },
    "Camera2D": {
        "required_nodes_partial": True,
    },
}

_SIGNAL_EVENT_MAP: dict[str, str] = {
    "body_entered": "collision_detected",
    "area_entered": "area_triggered",
    "timeout": "timer_fired",
    "pressed": "button_pressed",
    "animation_finished": "animation_completed",
    "scene_changed": "scene_changed",
}


@dataclass
class ScenarioSpec:
    id: str
    title: str
    description: str
    path_contains: list[str] = field(default_factory=list)
    required_scene: str = ""
    required_nodes: list[str] = field(default_factory=list)
    required_events: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    forbid_runtime_errors: bool = True
    genres: list[str] = field(default_factory=list)
    enemy_models: list[str] = field(default_factory=list)
    testing_focus: list[str] = field(default_factory=list)
    quality_targets: list[str] = field(default_factory=list)
    fixtures: dict[str, Any] = field(default_factory=dict)
    steps: list["ScenarioStep"] = field(default_factory=list)
    source: str = "manual"
    confidence: str = "high"
    evidence_policy: str = "advisory"
    authoritative_assertions: list[str] = field(default_factory=list)
    source_scene: str = ""


@dataclass
class VisualAssert:
    baseline_id: str
    actual_path: str = ""
    tolerance: int = 0
    region: list[int] = field(default_factory=list)


@dataclass
class ScenarioStep:
    title: str
    action: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    ticks: int = 0
    expect_scene: str = ""
    expect_state: dict[str, Any] = field(default_factory=dict)
    expect_events: list[str] = field(default_factory=list)
    visual_asserts: list[VisualAssert] = field(default_factory=list)
    route_segments: list["RouteSegment"] = field(default_factory=list)
    sample_asserts: list["SampleAssert"] = field(default_factory=list)


@dataclass
class RouteSegment:
    ticks: int = 0
    press: list[str] = field(default_factory=list)
    release: list[str] = field(default_factory=list)
    state_updates: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    capture_as: str = ""


@dataclass
class SampleAssert:
    label: str = ""
    left_sample: str = ""
    left_key: str = ""
    op: str = "=="
    right_sample: str = ""
    right_key: str = ""
    value: Any = None


@dataclass
class StepExecutionResult:
    snapshot: RuntimeSnapshot | None
    observations: list[str] = field(default_factory=list)
    samples: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    id: str
    title: str
    status: str
    observations: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    failure_bundle: str = ""
    evidence_source: str = ""
    evidence_level: str = ""


@dataclass
class PlaytestReport:
    scenarios: list[ScenarioResult] = field(default_factory=list)
    profile_genre: str = ""

    @property
    def verdict(self) -> str:
        statuses = {scenario.status for scenario in self.scenarios}
        if "FAIL" in statuses:
            return "FAIL"
        if "PARTIAL" in statuses or "WARN" in statuses:
            return "PARTIAL"
        return "PASS"


@dataclass
class AuthoritativePlaytestEvidence:
    scene_path: str
    summary_path: str
    summary: dict[str, Any]
    assertions: dict[str, dict[str, Any]]
    snapshot: RuntimeSnapshot
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


def _load_scenario_specs(directory: Path = SCENARIO_DIR) -> list[ScenarioSpec]:
    specs: list[ScenarioSpec] = []
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        steps = [
            ScenarioStep(
                title=step.get("title", "Unnamed Step"),
                action=step.get("action", ""),
                args=step.get("args", {}),
                ticks=step.get("ticks", 0),
                expect_scene=step.get("expect_scene", ""),
                expect_state=step.get("expect_state", {}),
                expect_events=step.get("expect_events", []),
                visual_asserts=[VisualAssert(**visual) for visual in step.get("visual_asserts", [])],
                route_segments=[
                    RouteSegment(**segment)
                    for segment in step.get("route_segments", step.get("segments", []))
                ],
                sample_asserts=[SampleAssert(**assertion) for assertion in step.get("sample_asserts", [])],
            )
            for step in data.get("steps", [])
        ]
        specs.append(
            ScenarioSpec(
                id=data["id"],
                title=data["title"],
                description=data["description"],
                path_contains=data.get("path_contains", []),
                required_scene=data.get("required_scene", ""),
                required_nodes=data.get("required_nodes", []),
                required_events=data.get("required_events", []),
                required_inputs=data.get("required_inputs", []),
                forbid_runtime_errors=data.get("forbid_runtime_errors", True),
                genres=data.get("genres", []),
                enemy_models=data.get("enemy_models", []),
                testing_focus=data.get("testing_focus", []),
                quality_targets=data.get("quality_targets", []),
                fixtures=data.get("fixtures", {}),
                steps=steps,
                source=data.get("source", "manual"),
                confidence=data.get("confidence", "high"),
                evidence_policy=data.get("evidence_policy", "advisory"),
                authoritative_assertions=list(data.get("authoritative_assertions") or []),
                source_scene=data.get("source_scene", ""),
            )
        )
    return specs


def _tokenize_path(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]


def _as_res_path(project_root: Path, file_path: Path) -> str:
    return "res://" + str(file_path.resolve().relative_to(project_root.resolve())).replace("\\", "/")


def _authoritative_evidence(snapshot: RuntimeSnapshot | None) -> bool:
    return snapshot is not None and snapshot.source in {"live_editor", "headless"}


def _snapshot_evidence(snapshot: RuntimeSnapshot | None) -> tuple[str, str]:
    if snapshot is None:
        return "", ""
    return snapshot.source, snapshot.evidence_level


def _apply_evidence_policy(
    *,
    spec: ScenarioSpec,
    status: str,
    observations: list[str],
    snapshot: RuntimeSnapshot | None,
) -> tuple[str, list[str]]:
    source, level = _snapshot_evidence(snapshot)
    if source:
        observations.append(f"Evidence source: {source} ({level})")

    if status == "PASS" and spec.source == "generated" and not _authoritative_evidence(snapshot):
        observations.append("Generated baseline scenario passed with synthetic-only evidence; verdict downgraded to PARTIAL.")
        return "PARTIAL", observations

    if status == "PASS" and spec.evidence_policy == "require_live_for_pass" and not _authoritative_evidence(snapshot):
        observations.append("Scenario requires live or headless runtime evidence for a full PASS; verdict downgraded to PARTIAL.")
        return "PARTIAL", observations

    return status, observations


_PLAYTEST_SUMMARY_RE = re.compile(r"PLAYTEST_SUMMARY\s+(.+)")


def _discover_headless_playtest_scene(project_root: Path) -> str:
    preferred = [
        project_root / "scenes" / "playtests" / "scripted_combat_playtest.tscn",
        project_root / "scenes" / "playtests" / "scripted_playtest.tscn",
    ]
    for candidate in preferred:
        if candidate.exists():
            return _as_res_path(project_root, candidate)

    playtest_dir = project_root / "scenes" / "playtests"
    if playtest_dir.exists():
        for candidate in sorted(playtest_dir.glob("*.tscn")):
            if candidate.is_file():
                return _as_res_path(project_root, candidate)
    return ""


def _extract_summary_path(output: str) -> str:
    match = _PLAYTEST_SUMMARY_RE.search(output)
    if match:
        return match.group(1).strip()
    return ""


def _fallback_summary_path(project_root: Path) -> str:
    artifact_dir = project_root / ".god-code-artifacts" / "playtests"
    if not artifact_dir.exists():
        return ""
    candidates = sorted(
        artifact_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return str(candidates[0]) if candidates else ""


def _authoritative_screenshot_paths(summary: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add_path(value: Any) -> None:
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        paths.append(normalized)

    sections: list[dict[str, Any]] = [summary]
    for key in ("wave", "boss", "visual"):
        section = summary.get(key)
        if isinstance(section, dict):
            sections.append(section)

    for section in sections:
        screenshots = section.get("screenshots")
        if not isinstance(screenshots, list):
            continue
        for item in screenshots:
            if isinstance(item, dict):
                add_path(item.get("path"))
            else:
                add_path(item)
    return paths


def _authoritative_visual_observations(summary: dict[str, Any]) -> list[str]:
    observations: list[str] = []
    seen: set[str] = set()
    visual = summary.get("visual")
    if not isinstance(visual, dict):
        return observations

    for item in visual.get("observations") or []:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        observations.append(normalized)
    return observations


def _capture_authoritative_visual_artifacts(project_root: Path, scene_path: str) -> list[dict[str, Any]]:
    capture_plan = [
        ("wave-pressure", 2500, ["pattern_readability", "wave_pressure"]),
        ("boss-telegraph", 7000, ["phase_banner", "screen_flash", "boss_transition"]),
        ("combat-feedback", 8500, ["hit_feedback", "enemy_defeated", "combat_feedback"]),
    ]
    resolved_godot_path = resolve_godot_path("godot")
    captures: list[dict[str, Any]] = []
    scene_stem = Path(scene_path).stem or "playtest"

    for label, delay_ms, tags in capture_plan:
        output_path = build_artifact_path(
            project_root,
            category="playtests",
            name=f"{scene_stem}-{label}",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "capture.gd"
            script_path.write_text(
                build_screenshot_script(scene_path, str(output_path), delay_ms),
                encoding="utf-8",
            )
            try:
                proc = subprocess.run(
                    [resolved_godot_path, "-s", str(script_path)],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=max(45, int(delay_ms / 1000) + 20),
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
        if proc.returncode not in (0, None) or not output_path.exists():
            continue
        captures.append(
            {
                "path": str(output_path),
                "label": label.replace("-", " ").title(),
                "tags": tags,
            }
        )
    return captures


def _snapshot_from_authoritative_summary(
    *,
    scene_path: str,
    summary_path: str,
    summary: dict[str, Any],
) -> RuntimeSnapshot:
    state: dict[str, Any] = {"authoritative_summary_path": summary_path}
    events: list[RuntimeEvent] = []
    screenshot_paths = _authoritative_screenshot_paths(summary)

    wave = summary.get("wave") if isinstance(summary.get("wave"), dict) else {}
    samples = wave.get("samples") if isinstance(wave, dict) else []
    if isinstance(samples, list) and samples:
        opening = samples[0] if isinstance(samples[0], dict) else {}
        closing = samples[-1] if isinstance(samples[-1], dict) else {}
        state.update(
            {
                "enemy_bullets": closing.get("enemy_bullets", opening.get("enemy_bullets", 0)),
                "player_bullets": closing.get("player_bullets", opening.get("player_bullets", 0)),
                "enemies_alive": closing.get("enemies", opening.get("enemies", 0)),
                "player_lives": closing.get("lives", opening.get("lives", 0)),
            }
        )

    boss = summary.get("boss") if isinstance(summary.get("boss"), dict) else {}
    if boss:
        phases_seen = boss.get("phases_seen") or []
        if phases_seen:
            state["boss_phase"] = phases_seen[-1]
        if "remaining_enemy_bullets" in boss:
            state["enemy_bullets"] = boss.get("remaining_enemy_bullets", state.get("enemy_bullets", 0))
        if "bullets_before_clear" in boss:
            state["boss_transition_pressure"] = max(boss.get("bullets_before_clear") or [0])

    visual = summary.get("visual") if isinstance(summary.get("visual"), dict) else {}
    cues = visual.get("cues") if isinstance(visual.get("cues"), dict) else {}
    if "phase_banner_visible" in cues:
        state["phase_banner_visible"] = bool(cues.get("phase_banner_visible"))
    if "screen_flash" in cues:
        state["screen_flash"] = int(bool(cues.get("screen_flash")))
    if cues.get("hit_feedback"):
        events.append(RuntimeEvent(name="hit_feedback", tick=0))
    if cues.get("enemy_defeated"):
        events.append(RuntimeEvent(name="enemy_defeated", tick=0))

    for assertion in summary.get("assertions") or []:
        if not isinstance(assertion, dict):
            continue
        name = str(assertion.get("name", "")).strip()
        if not name:
            continue
        if name.startswith("wave_"):
            events.append(RuntimeEvent(name="wave_pressure", tick=0))
        if name.startswith("boss_phase_"):
            events.append(RuntimeEvent(name="boss_phase_changed", tick=0))
        if name == "boss_transitions_clear_bullets":
            events.append(RuntimeEvent(name="boss_transition_cleared", tick=0))

    snapshot = RuntimeSnapshot(
        active_scene=scene_path,
        current_tick=int(state.get("boss_phase", 0) or 0),
        events=events,
        state=state,
        screenshot_paths=screenshot_paths,
        source="headless",
        evidence_level="high",
        bridge_connected=False,
    )
    return update_runtime_snapshot(snapshot)


def _run_authoritative_headless_playtest(project_root: Path) -> AuthoritativePlaytestEvidence | None:
    scene_path = _discover_headless_playtest_scene(project_root)
    if not scene_path:
        return None

    summary_guess = Path(_fallback_summary_path(project_root))
    if summary_guess.exists():
        try:
            summary_guess.unlink()
        except OSError:
            pass

    cmd = [resolve_godot_path("godot"), "--headless", "--path", str(project_root), scene_path]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    output = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    summary_path = _extract_summary_path(output) or _fallback_summary_path(project_root)
    if not summary_path:
        return None
    summary_file = Path(summary_path)
    if not summary_file.exists():
        return None

    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not _authoritative_screenshot_paths(summary):
        supplemental_captures = _capture_authoritative_visual_artifacts(project_root, scene_path)
        if supplemental_captures:
            visual = summary.get("visual")
            if not isinstance(visual, dict):
                visual = {}
            screenshots = visual.get("screenshots")
            if not isinstance(screenshots, list):
                screenshots = []
            screenshots.extend(supplemental_captures)
            visual["screenshots"] = screenshots
            summary["visual"] = visual

    assertions: dict[str, dict[str, Any]] = {}
    for assertion in summary.get("assertions") or []:
        if isinstance(assertion, dict):
            name = str(assertion.get("name", "")).strip()
            if name:
                assertions[name] = assertion

    snapshot = _snapshot_from_authoritative_summary(
        scene_path=scene_path,
        summary_path=str(summary_file),
        summary=summary,
    )
    return AuthoritativePlaytestEvidence(
        scene_path=scene_path,
        summary_path=str(summary_file),
        summary=summary,
        assertions=assertions,
        snapshot=snapshot,
        exit_code=int(proc.returncode or 0),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def generate_scenario_specs(
    project_root: Path,
    existing_specs: list[ScenarioSpec] | None = None,
) -> list[ScenarioSpec]:
    existing_ids = {spec.id for spec in existing_specs or []}
    generated: list[ScenarioSpec] = []

    for scene_path in sorted(project_root.rglob("*.tscn")):
        if ".godot" in str(scene_path):
            continue

        scene = parse_tscn(scene_path.read_text(encoding="utf-8", errors="replace"))
        required_inputs: list[str] = []
        required_events: list[str] = []
        path_contains = set(_tokenize_path(scene_path.stem))
        required_nodes: list[str] = []
        forbid_runtime_errors = False
        matched = False

        for node in scene.nodes:
            hint = _NODE_SCENARIO_HINTS.get(node.type)
            if hint is None:
                if node.type == "CollisionShape2D":
                    required_nodes.append(node.name)
                continue
            matched = True
            required_inputs.extend(str(item) for item in hint.get("required_inputs", []))
            required_events.extend(str(item) for item in hint.get("required_events", []))
            path_contains.update(str(item) for item in hint.get("path_contains", []))
            if hint.get("required_nodes_partial"):
                required_nodes.append(node.name)
            forbid_runtime_errors = forbid_runtime_errors or bool(hint.get("forbid_runtime_errors"))

        for connection in scene.connections:
            mapped_event = _SIGNAL_EVENT_MAP.get(connection.signal)
            if mapped_event:
                matched = True
                required_events.append(mapped_event)

        if not matched:
            continue

        if scene.nodes:
            required_nodes.insert(0, scene.nodes[0].name)

        scene_id = f"auto_{re.sub(r'[^a-z0-9]+', '_', scene_path.stem.lower()).strip('_')}"
        if not scene_id or scene_id in existing_ids:
            continue

        source_scene = _as_res_path(project_root, scene_path)
        generated.append(
            ScenarioSpec(
                id=scene_id,
                title=f"{scene_path.stem.replace('_', ' ').title()} Baseline",
                description=f"Auto-generated baseline coverage for {source_scene}.",
                path_contains=sorted(path_contains),
                required_scene=source_scene,
                required_nodes=list(dict.fromkeys(required_nodes)),
                required_events=list(dict.fromkeys(required_events)),
                required_inputs=list(dict.fromkeys(required_inputs)),
                forbid_runtime_errors=forbid_runtime_errors or True,
                source="generated",
                confidence="low",
                evidence_policy="require_live_for_pass",
                source_scene=source_scene,
            )
        )
        existing_ids.add(scene_id)

    return generated


def _scenario_matches_profile(
    spec: ScenarioSpec,
    intent_profile: GameplayIntentProfile | None,
    quality_target: str = "prototype",
) -> bool:
    if spec.quality_targets and quality_target not in spec.quality_targets:
        return False

    if intent_profile is None or intent_profile.is_empty:
        return bool(spec.quality_targets and quality_target in spec.quality_targets)

    explicit_match = False
    if spec.genres:
        if intent_profile.genre not in spec.genres:
            return False
        explicit_match = True
    if spec.enemy_models:
        if intent_profile.enemy_model not in spec.enemy_models:
            return False
        explicit_match = True
    if explicit_match:
        return True

    if spec.testing_focus and set(spec.testing_focus) & set(intent_profile.testing_focus):
        return True
    if spec.quality_targets and quality_target in spec.quality_targets:
        return True
    return False


def _scenario_constraints_compatible(
    spec: ScenarioSpec,
    intent_profile: GameplayIntentProfile | None,
    quality_target: str,
) -> bool:
    if spec.quality_targets and quality_target not in spec.quality_targets:
        return False
    if spec.genres:
        if intent_profile is None or intent_profile.is_empty or intent_profile.genre not in spec.genres:
            return False
    if spec.enemy_models:
        if intent_profile is None or intent_profile.is_empty or intent_profile.enemy_model not in spec.enemy_models:
            return False
    return True


def select_relevant_scenarios(
    changed_files: set[str],
    impact_report: ImpactAnalysisReport | None = None,
    directory: Path = SCENARIO_DIR,
    intent_profile: GameplayIntentProfile | None = None,
    quality_target: str = "prototype",
    specs: list[ScenarioSpec] | None = None,
) -> list[ScenarioSpec]:
    changed_paths = {Path(path).name.lower() for path in changed_files}
    if impact_report is not None:
        changed_paths.update(path.lower() for path in impact_report.affected_files)

    relevant: list[ScenarioSpec] = []
    for spec in specs or _load_scenario_specs(directory):
        triggers = [token.lower() for token in spec.path_contains]
        path_match = (
            bool(triggers)
            and _scenario_constraints_compatible(spec, intent_profile, quality_target)
            and any(token in path for token in triggers for path in changed_paths)
        )
        profile_match = _scenario_matches_profile(spec, intent_profile, quality_target=quality_target)
        if path_match or profile_match:
            relevant.append(spec)
    return relevant


def _step_to_contract(step: ScenarioStep) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": step.title,
        "action": step.action,
    }
    if step.args:
        payload["args"] = dict(step.args)
    if step.ticks:
        payload["ticks"] = step.ticks
    if step.expect_scene:
        payload["expect_scene"] = step.expect_scene
    if step.expect_state:
        payload["expect_state"] = dict(step.expect_state)
    if step.expect_events:
        payload["expect_events"] = list(step.expect_events)
    if step.visual_asserts:
        payload["visual_asserts"] = [asdict(visual) for visual in step.visual_asserts]
    if step.route_segments:
        payload["route_segments"] = [asdict(segment) for segment in step.route_segments]
    if step.sample_asserts:
        payload["sample_asserts"] = [asdict(assertion) for assertion in step.sample_asserts]
    return payload


def scenario_contract(spec: ScenarioSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "required_scene": spec.required_scene,
        "genres": list(spec.genres),
        "enemy_models": list(spec.enemy_models),
        "testing_focus": list(spec.testing_focus),
        "quality_targets": list(spec.quality_targets),
        "source": spec.source,
        "confidence": spec.confidence,
        "evidence_policy": spec.evidence_policy,
        "authoritative_assertions": list(spec.authoritative_assertions),
        "steps": [_step_to_contract(step) for step in spec.steps],
    }


def list_scenario_specs(
    *,
    directory: Path = SCENARIO_DIR,
    intent_profile: GameplayIntentProfile | None = None,
    quality_target: str = "prototype",
    project_root: Path | None = None,
    include_generated: bool = False,
) -> list[dict[str, Any]]:
    specs = _load_scenario_specs(directory)
    if include_generated and project_root is not None:
        specs.extend(generate_scenario_specs(project_root, existing_specs=specs))
    return [
        {
            "id": spec.id,
            "title": spec.title,
            "description": spec.description,
            "has_steps": bool(spec.steps),
            "genres": list(spec.genres),
            "enemy_models": list(spec.enemy_models),
            "testing_focus": list(spec.testing_focus),
            "quality_targets": list(spec.quality_targets),
            "path_contains": list(spec.path_contains),
            "authoritative_assertions": list(spec.authoritative_assertions),
            "relevant": _scenario_matches_profile(spec, intent_profile, quality_target=quality_target),
        }
        for spec in specs
    ]


def list_contracts(
    *,
    directory: Path = SCENARIO_DIR,
    scenario_id: str = "",
    intent_profile: GameplayIntentProfile | None = None,
    quality_target: str = "prototype",
    project_root: Path | None = None,
    include_generated: bool = False,
    match_profile: bool = True,
) -> list[dict[str, Any]]:
    specs = _load_scenario_specs(directory)
    if include_generated and project_root is not None:
        specs.extend(generate_scenario_specs(project_root, existing_specs=specs))
    if scenario_id:
        specs = [spec for spec in specs if spec.id == scenario_id]
    elif match_profile:
        specs = [spec for spec in specs if _scenario_matches_profile(spec, intent_profile, quality_target=quality_target)]
    return [scenario_contract(spec) for spec in specs]


def _evaluate_scenario(spec: ScenarioSpec, snapshot: RuntimeSnapshot | None) -> ScenarioResult:
    if snapshot is None:
        return ScenarioResult(
            id=spec.id,
            title=spec.title,
            status="PARTIAL",
            observations=["No runtime snapshot available for this scenario."],
            evidence_source="",
            evidence_level="",
        )

    observations: list[str] = []
    status = "PASS"
    node_paths = {node.path for node in snapshot.nodes}
    node_names = {node.path.split("/")[-1] for node in snapshot.nodes}
    event_names = {event.name for event in runtime_contract_events(snapshot)}
    input_names = set(snapshot.input_actions)

    if spec.required_scene and snapshot.active_scene != spec.required_scene:
        status = "FAIL"
        observations.append(f"Expected active scene {spec.required_scene}, got {snapshot.active_scene or '(none)'}")
    if spec.required_nodes:
        missing_nodes = [node for node in spec.required_nodes if node not in node_paths and node not in node_names]
        if missing_nodes:
            status = "FAIL"
            observations.append("Missing nodes: " + ", ".join(missing_nodes))
    if spec.required_events:
        missing_events = [event for event in spec.required_events if event not in event_names]
        if missing_events:
            status = "PARTIAL" if status == "PASS" else status
            observations.append("Missing events: " + ", ".join(missing_events))
    if spec.required_inputs:
        missing_inputs = [action for action in spec.required_inputs if action not in input_names]
        if missing_inputs:
            status = "PARTIAL" if status == "PASS" else status
            observations.append("Missing input evidence: " + ", ".join(missing_inputs))
    if spec.forbid_runtime_errors and snapshot.errors:
        status = "FAIL"
        observations.append("Runtime errors present: " + " | ".join(snapshot.errors[:5]))

    if not observations:
        observations.append("Scenario expectations satisfied.")
    status, observations = _apply_evidence_policy(spec=spec, status=status, observations=observations, snapshot=snapshot)
    source, level = _snapshot_evidence(snapshot)
    return ScenarioResult(
        id=spec.id,
        title=spec.title,
        status=status,
        observations=observations,
        evidence_source=source,
        evidence_level=level,
    )


def _current_snapshot(seed_snapshot: RuntimeSnapshot | None) -> RuntimeSnapshot | None:
    if seed_snapshot is not None:
        update_runtime_snapshot(copy.deepcopy(seed_snapshot))
    return get_runtime_snapshot()


def _capture_route_sample(snapshot: RuntimeSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {"current_tick": 0, "state": {}, "contract_state": {}, "active_inputs": [], "fixtures": {}}
    return {
        "current_tick": snapshot.current_tick,
        "state": dict(snapshot.state),
        "contract_state": runtime_contract_state(snapshot),
        "active_inputs": list(snapshot.active_inputs),
        "fixtures": dict(snapshot.fixtures),
    }


def _execute_scripted_route(step: ScenarioStep) -> StepExecutionResult:
    snapshot = get_runtime_snapshot()
    observations: list[str] = []
    samples: dict[str, dict[str, Any]] = {}

    for segment in step.route_segments:
        for action in segment.release:
            snapshot = press_runtime_action(action, pressed=False)
        for action in segment.press:
            snapshot = press_runtime_action(action, pressed=True)
        snapshot = advance_runtime_ticks(
            segment.ticks,
            state_updates=segment.state_updates,
            events=segment.events,
        )
        if segment.capture_as:
            samples[segment.capture_as] = _capture_route_sample(snapshot)
            observations.append(
                f"Captured sample {segment.capture_as} at tick {samples[segment.capture_as]['current_tick']}."
            )

    return StepExecutionResult(snapshot=snapshot, observations=observations, samples=samples)


def _execute_step_action(step: ScenarioStep, scenario: ScenarioSpec) -> StepExecutionResult:
    action = step.action.strip().lower()
    args = step.args
    if action == "load_scene":
        return StepExecutionResult(snapshot=load_runtime_scene(str(args.get("scene_path") or scenario.required_scene)))
    if action == "set_fixture":
        if "name" in args:
            return StepExecutionResult(snapshot=set_runtime_fixture(str(args["name"]), args.get("payload", {})))
        snapshot = get_runtime_snapshot()
        for fixture_name, payload in args.items():
            snapshot = set_runtime_fixture(str(fixture_name), payload)
        return StepExecutionResult(snapshot=snapshot)
    if action == "press_action":
        return StepExecutionResult(
            snapshot=press_runtime_action(str(args.get("action", "")), pressed=bool(args.get("pressed", True)))
        )
    if action == "release_action":
        return StepExecutionResult(snapshot=press_runtime_action(str(args.get("action", "")), pressed=False))
    if action == "advance_ticks":
        return StepExecutionResult(
            snapshot=advance_runtime_ticks(
                step.ticks or int(args.get("count", 1)),
                state_updates=args.get("state_updates", {}),
                events=args.get("events", []),
            )
        )
    if action == "scripted_route":
        return _execute_scripted_route(step)
    if action == "capture_viewport":
        path_value = str(args.get("actual_path", "")).strip()
        if path_value:
            add_runtime_screenshot(path_value)
        return StepExecutionResult(snapshot=get_runtime_snapshot())
    return StepExecutionResult(snapshot=get_runtime_snapshot())


def _resolve_sample_value(
    *,
    sample_name: str,
    key: str,
    samples: dict[str, dict[str, Any]],
    snapshot: RuntimeSnapshot | None,
) -> Any:
    payload = _capture_route_sample(snapshot) if not sample_name or sample_name == "current" else samples.get(sample_name)
    if payload is None:
        raise KeyError(f"sample {sample_name!r} was not captured")
    if key in {"current_tick", "tick"}:
        return payload.get("current_tick")
    if key.startswith("contract."):
        return payload.get("contract_state", {}).get(key.split(".", 1)[1])
    if key.startswith("state."):
        return payload.get("state", {}).get(key.split(".", 1)[1])
    if key.startswith("fixture."):
        return payload.get("fixtures", {}).get(key.split(".", 1)[1])
    if key == "active_inputs":
        return payload.get("active_inputs", [])
    if key in payload.get("contract_state", {}):
        return payload.get("contract_state", {}).get(key)
    return payload.get("state", {}).get(key)


def _sample_assertion_message(assertion: SampleAssert) -> str:
    return assertion.label or f"{assertion.left_sample or 'current'}.{assertion.left_key} {assertion.op}"


def _evaluate_sample_asserts(
    *,
    step: ScenarioStep,
    samples: dict[str, dict[str, Any]],
    snapshot: RuntimeSnapshot | None,
) -> list[str]:
    observations: list[str] = []
    operators = {
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
    }

    for assertion in step.sample_asserts:
        comparator = operators.get(assertion.op)
        if comparator is None:
            observations.append(f"Unsupported sample assertion operator: {assertion.op}")
            continue
        try:
            left = _resolve_sample_value(
                sample_name=assertion.left_sample,
                key=assertion.left_key,
                samples=samples,
                snapshot=snapshot,
            )
            if assertion.right_sample or assertion.right_key:
                right = _resolve_sample_value(
                    sample_name=assertion.right_sample,
                    key=assertion.right_key,
                    samples=samples,
                    snapshot=snapshot,
                )
            else:
                right = assertion.value
        except KeyError as exc:
            observations.append(f"{_sample_assertion_message(assertion)}: {exc}")
            continue
        if comparator(left, right):
            observations.append(
                f"Sample assertion passed: {_sample_assertion_message(assertion)} "
                f"({left!r} {assertion.op} {right!r})."
            )
            continue
        observations.append(
            f"Sample assertion failed: {_sample_assertion_message(assertion)} "
            f"({left!r} {assertion.op} {right!r})."
        )
    return observations


def _run_visual_asserts(
    *,
    project_root: Path,
    step: ScenarioStep,
    snapshot: RuntimeSnapshot | None,
) -> tuple[list[str], dict[str, str], str]:
    observations: list[str] = []
    artifacts: dict[str, str] = {}
    failure_bundle = ""

    for visual in step.visual_asserts:
        actual_path = visual.actual_path or (snapshot.screenshot_paths[-1] if snapshot and snapshot.screenshot_paths else "")
        if not actual_path:
            observations.append(f"Missing actual screenshot for baseline {visual.baseline_id}.")
            continue
        actual = Path(actual_path)
        baseline = resolve_baseline_path(project_root, visual.baseline_id)
        comparison = compare_image_files(
            project_root=project_root,
            actual_path=actual,
            baseline_path=baseline,
            tolerance=visual.tolerance,
            region=visual.region,
        )
        artifacts["actual"] = comparison.actual_path
        artifacts["expected"] = comparison.baseline_path
        if comparison.diff_path:
            artifacts["diff"] = comparison.diff_path
        if comparison.matched:
            observations.append(f"Baseline matched for {visual.baseline_id}.")
            continue
        observations.append(
            f"Baseline mismatch for {visual.baseline_id}: {comparison.reason or 'visual_diff'} "
            f"(pixels={comparison.pixel_diff_count}, max_delta={comparison.max_channel_delta})"
        )
        failure_payload = {
            "test_id": visual.baseline_id.replace("/", "_"),
            "step": step.title,
            "reason": comparison.reason or "visual_diff_exceeded",
            "scene": snapshot.active_scene if snapshot else "",
            "ui_state": runtime_state_dict(snapshot),
            "image_assert": comparison.to_dict(),
            "artifacts": artifacts,
        }
        failure_bundle = str(
            write_failure_bundle(
                project_root,
                test_id=f"{visual.baseline_id.replace('/', '_')}-{step.title.lower().replace(' ', '-')}",
                payload=failure_payload,
            )
        )
        break

    return observations, artifacts, failure_bundle


def _execute_authoritative_scenario(
    *,
    spec: ScenarioSpec,
    project_root: Path,
    evidence: AuthoritativePlaytestEvidence,
) -> ScenarioResult | None:
    if not spec.authoritative_assertions:
        return None

    observations = [
        f"Authoritative headless playtest scene: {evidence.scene_path}",
        f"Authoritative summary: {evidence.summary_path}",
    ]
    artifacts = {"summary": evidence.summary_path}
    screenshot_paths = _authoritative_screenshot_paths(evidence.summary)
    if screenshot_paths:
        artifacts["screenshots"] = screenshot_paths
    for observation in _authoritative_visual_observations(evidence.summary):
        observations.append(observation)
    missing: list[str] = []
    failures: list[tuple[str, dict[str, Any]]] = []

    for assertion_name in spec.authoritative_assertions:
        assertion = evidence.assertions.get(assertion_name)
        if assertion is None:
            missing.append(assertion_name)
            continue
        passed = bool(assertion.get("passed", False))
        details = assertion.get("details", {})
        if passed:
            observations.append(f"Authoritative assertion passed: {assertion_name}.")
        else:
            observations.append(f"Authoritative assertion failed: {assertion_name}.")
            failures.append((assertion_name, details if isinstance(details, dict) else {"details": details}))

    if failures:
        assertion_name, details = failures[0]
        failure_bundle = str(
            write_failure_bundle(
                project_root,
                test_id=f"{spec.id}-authoritative",
                payload={
                    "test_id": spec.id,
                    "step": "authoritative_headless_playtest",
                    "reason": f"authoritative_assertion_failed:{assertion_name}",
                    "scene": evidence.scene_path,
                    "ui_state": runtime_state_dict(evidence.snapshot),
                    "artifacts": artifacts,
                    "details": details,
                },
            )
        )
        return ScenarioResult(
            id=spec.id,
            title=spec.title,
            status="FAIL",
            observations=observations,
            artifacts=artifacts,
            failure_bundle=failure_bundle,
            evidence_source="headless",
            evidence_level=evidence.snapshot.evidence_level,
        )

    if missing:
        observations.append("Missing authoritative assertions: " + ", ".join(missing))
        return ScenarioResult(
            id=spec.id,
            title=spec.title,
            status="PARTIAL",
            observations=observations,
            artifacts=artifacts,
            evidence_source="headless",
            evidence_level=evidence.snapshot.evidence_level,
        )

    observations.append(f"Evidence source: headless ({evidence.snapshot.evidence_level})")
    return ScenarioResult(
        id=spec.id,
        title=spec.title,
        status="PASS",
        observations=observations,
        artifacts=artifacts,
        evidence_source="headless",
        evidence_level=evidence.snapshot.evidence_level,
    )


def _execute_step_scenario(
    *,
    spec: ScenarioSpec,
    project_root: Path,
    runtime_snapshot: RuntimeSnapshot | None,
    authoritative_evidence: AuthoritativePlaytestEvidence | None = None,
) -> ScenarioResult:
    authoritative_result = None
    if authoritative_evidence is not None:
        authoritative_result = _execute_authoritative_scenario(
            spec=spec,
            project_root=project_root,
            evidence=authoritative_evidence,
        )
    if authoritative_result is not None:
        return authoritative_result

    snapshot = _current_snapshot(runtime_snapshot) if runtime_snapshot is not None else None
    if snapshot is None:
        snapshot = load_runtime_scene(spec.required_scene)
    elif spec.required_scene and snapshot.active_scene != spec.required_scene:
        snapshot = load_runtime_scene(spec.required_scene)

    for fixture_name, payload in spec.fixtures.items():
        set_runtime_fixture(fixture_name, payload)

    observations: list[str] = []
    artifacts: dict[str, str] = {}
    for index, step in enumerate(spec.steps, start=1):
        before_tick = snapshot.current_tick if snapshot else 0
        execution = _execute_step_action(step, spec)
        snapshot = execution.snapshot or get_runtime_snapshot()
        step_status = "PASS"
        step_observations: list[str] = list(execution.observations)

        expected_scene = step.expect_scene or ""
        if expected_scene and (snapshot is None or snapshot.active_scene != expected_scene):
            step_status = "FAIL"
            step_observations.append(
                f"Expected active scene {expected_scene}, got {snapshot.active_scene if snapshot else '(none)'}."
            )

        state_payload = runtime_state_dict(snapshot)
        state = state_payload.get("contract_state", {}) or state_payload.get("state", {})
        for key, expected_value in step.expect_state.items():
            actual_value = state.get(key)
            if actual_value != expected_value:
                step_status = "FAIL"
                step_observations.append(f"State mismatch for {key}: expected {expected_value!r}, got {actual_value!r}.")

        if step.expect_events:
            recent_events = {event.name for event in runtime_contract_events(snapshot) if event.tick > before_tick}
            missing = [name for name in step.expect_events if name not in recent_events]
            if missing:
                step_status = "FAIL"
                step_observations.append("Missing events: " + ", ".join(missing))

        sample_assertions = _evaluate_sample_asserts(
            step=step,
            samples=execution.samples,
            snapshot=snapshot,
        )
        step_observations.extend(sample_assertions)
        if any(observation.startswith("Sample assertion failed:") or "Unsupported sample assertion operator" in observation for observation in sample_assertions):
            step_status = "FAIL"

        visual_observations, visual_artifacts, failure_bundle = _run_visual_asserts(
            project_root=project_root,
            step=step,
            snapshot=snapshot,
        )
        step_observations.extend(visual_observations)
        artifacts.update({key: value for key, value in visual_artifacts.items() if value})
        if failure_bundle:
            source, level = _snapshot_evidence(snapshot)
            return ScenarioResult(
                id=spec.id,
                title=spec.title,
                status="FAIL",
                observations=[*observations, f"Step {index}: {step.title} [FAIL]", *step_observations],
                artifacts=artifacts,
                failure_bundle=failure_bundle,
                evidence_source=source,
                evidence_level=level,
            )

        observations.append(f"Step {index}: {step.title} [{step_status}]")
        observations.extend(step_observations or ["Scenario step passed."])
        if step_status == "FAIL":
            failure_payload = {
                "test_id": spec.id,
                "step": step.title,
                "reason": "step_assertion_failed",
                "scene": snapshot.active_scene if snapshot else "",
                "ui_state": runtime_state_dict(snapshot),
                "artifacts": artifacts,
                "details": {"observations": step_observations},
            }
            failure_bundle = str(write_failure_bundle(project_root, test_id=f"{spec.id}-{index:02d}", payload=failure_payload))
            source, level = _snapshot_evidence(snapshot)
            return ScenarioResult(
                id=spec.id,
                title=spec.title,
                status="FAIL",
                observations=observations,
                artifacts=artifacts,
                failure_bundle=failure_bundle,
                evidence_source=source,
                evidence_level=level,
            )

    final_status, observations = _apply_evidence_policy(
        spec=spec,
        status="PASS",
        observations=observations or ["Scenario expectations satisfied."],
        snapshot=snapshot,
    )
    source, level = _snapshot_evidence(snapshot)
    return ScenarioResult(
        id=spec.id,
        title=spec.title,
        status=final_status,
        observations=observations,
        artifacts=artifacts,
        evidence_source=source,
        evidence_level=level,
    )


def run_playtest_harness(
    *,
    project_root: Path,
    changed_files: set[str],
    impact_report: ImpactAnalysisReport | None = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    directory: Path = SCENARIO_DIR,
    intent_profile: GameplayIntentProfile | None = None,
    design_memory: DesignMemory | None = None,
    auto_generate: bool = True,
) -> PlaytestReport:
    quality_target = resolved_quality_target(design_memory)
    specs = _load_scenario_specs(directory)
    if auto_generate:
        specs.extend(generate_scenario_specs(project_root, existing_specs=specs))
    scenarios = select_relevant_scenarios(
        changed_files,
        impact_report,
        directory=directory,
        intent_profile=intent_profile,
        quality_target=quality_target,
        specs=specs,
    )
    if not scenarios:
        return PlaytestReport(
            scenarios=[ScenarioResult(id="none", title="No matching scenarios", status="PASS", observations=["No scenario matched the current change set."])],
            profile_genre=intent_profile.genre if intent_profile else "",
        )
    results: list[ScenarioResult] = []
    for spec in scenarios:
        if spec.steps:
            results.append(_execute_step_scenario(spec=spec, project_root=project_root, runtime_snapshot=runtime_snapshot))
        else:
            results.append(_evaluate_scenario(spec, runtime_snapshot))
    return PlaytestReport(scenarios=results, profile_genre=intent_profile.genre if intent_profile else "")


def run_scripted_playtest(
    *,
    project_root: Path,
    scenario_ids: list[str] | None = None,
    changed_files: set[str] | None = None,
    impact_report: ImpactAnalysisReport | None = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    directory: Path = SCENARIO_DIR,
    intent_profile: GameplayIntentProfile | None = None,
    design_memory: DesignMemory | None = None,
    auto_generate: bool = False,
    run_all: bool = False,
) -> PlaytestReport:
    quality_target = resolved_quality_target(design_memory)
    specs = _load_scenario_specs(directory)
    if auto_generate:
        specs.extend(generate_scenario_specs(project_root, existing_specs=specs))

    authoritative_evidence = None
    if not _authoritative_evidence(runtime_snapshot):
        authoritative_evidence = _run_authoritative_headless_playtest(project_root)
        if authoritative_evidence is not None:
            runtime_snapshot = authoritative_evidence.snapshot
            update_runtime_snapshot(copy.deepcopy(runtime_snapshot))
    elif runtime_snapshot is not None:
        update_runtime_snapshot(copy.deepcopy(runtime_snapshot))

    if run_all:
        scenarios = [spec for spec in specs if spec.steps]
    elif scenario_ids:
        wanted = {scenario_id.strip() for scenario_id in scenario_ids if scenario_id.strip()}
        scenarios = [spec for spec in specs if spec.id in wanted]
    else:
        scenarios = select_relevant_scenarios(
            changed_files or set(),
            impact_report,
            directory=directory,
            intent_profile=intent_profile,
            quality_target=quality_target,
            specs=specs,
        )
    step_scenarios = [spec for spec in scenarios if spec.steps]
    if not step_scenarios:
        return PlaytestReport(
            scenarios=[
                ScenarioResult(
                    id="none",
                    title="No scripted scenarios",
                    status="PASS",
                    observations=["No scripted playtest scenario matched the current selection."],
                )
            ],
            profile_genre=intent_profile.genre if intent_profile else "",
        )
    results = [
        _execute_step_scenario(
            spec=spec,
            project_root=project_root,
            runtime_snapshot=runtime_snapshot,
            authoritative_evidence=authoritative_evidence,
        )
        for spec in step_scenarios
    ]
    return PlaytestReport(scenarios=results, profile_genre=intent_profile.genre if intent_profile else "")


def format_playtest_report(report: PlaytestReport) -> str:
    lines = [f"Playtest VERDICT: {report.verdict}"]
    if report.profile_genre:
        lines.append(f"Profile: {report.profile_genre}")
    for scenario in report.scenarios:
        lines.append(f"- {scenario.title} [{scenario.status}]")
        for observation in scenario.observations:
            lines.append(f"  {observation}")
        if scenario.evidence_source:
            lines.append(f"  Evidence: {scenario.evidence_source} ({scenario.evidence_level})")
        if scenario.failure_bundle:
            lines.append(f"  Failure bundle: {scenario.failure_bundle}")
    return "\n".join(lines)

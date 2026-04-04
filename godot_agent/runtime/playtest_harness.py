"""Scenario-driven playtest harness."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.runtime.design_memory import GameplayIntentProfile
from godot_agent.runtime.runtime_bridge import (
    RuntimeSnapshot,
    add_runtime_screenshot,
    advance_runtime_ticks,
    get_runtime_snapshot,
    load_runtime_scene,
    press_runtime_action,
    runtime_events_since,
    runtime_state_dict,
    set_runtime_fixture,
    update_runtime_snapshot,
)
from godot_agent.runtime.visual_regression import compare_image_files, resolve_baseline_path, write_failure_bundle


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
    fixtures: dict[str, Any] = field(default_factory=dict)
    steps: list["ScenarioStep"] = field(default_factory=list)
    source: str = "manual"
    confidence: str = "high"
    evidence_policy: str = "advisory"
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
        if "PARTIAL" in statuses:
            return "PARTIAL"
        return "PASS"


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
                fixtures=data.get("fixtures", {}),
                steps=steps,
                source=data.get("source", "manual"),
                confidence=data.get("confidence", "high"),
                evidence_policy=data.get("evidence_policy", "advisory"),
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


def _scenario_matches_profile(spec: ScenarioSpec, intent_profile: GameplayIntentProfile | None) -> bool:
    if intent_profile is None or intent_profile.is_empty:
        return False
    if spec.genres and intent_profile.genre in spec.genres:
        return True
    if spec.enemy_models and intent_profile.enemy_model in spec.enemy_models:
        return True
    if spec.testing_focus and set(spec.testing_focus) & set(intent_profile.testing_focus):
        return True
    return False


def select_relevant_scenarios(
    changed_files: set[str],
    impact_report: ImpactAnalysisReport | None = None,
    directory: Path = SCENARIO_DIR,
    intent_profile: GameplayIntentProfile | None = None,
    specs: list[ScenarioSpec] | None = None,
) -> list[ScenarioSpec]:
    changed_paths = {Path(path).name.lower() for path in changed_files}
    if impact_report is not None:
        changed_paths.update(path.lower() for path in impact_report.affected_files)

    relevant: list[ScenarioSpec] = []
    for spec in specs or _load_scenario_specs(directory):
        triggers = [token.lower() for token in spec.path_contains]
        path_match = not triggers or any(token in path for token in triggers for path in changed_paths)
        profile_match = _scenario_matches_profile(spec, intent_profile)
        if path_match or profile_match:
            relevant.append(spec)
    return relevant


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
    event_names = {event.name for event in snapshot.events}
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


def _execute_step_action(step: ScenarioStep, scenario: ScenarioSpec) -> RuntimeSnapshot | None:
    action = step.action.strip().lower()
    args = step.args
    if action == "load_scene":
        return load_runtime_scene(str(args.get("scene_path") or scenario.required_scene))
    if action == "set_fixture":
        if "name" in args:
            return set_runtime_fixture(str(args["name"]), args.get("payload", {}))
        snapshot = get_runtime_snapshot()
        for fixture_name, payload in args.items():
            snapshot = set_runtime_fixture(str(fixture_name), payload)
        return snapshot
    if action == "press_action":
        return press_runtime_action(str(args.get("action", "")), pressed=bool(args.get("pressed", True)))
    if action == "release_action":
        return press_runtime_action(str(args.get("action", "")), pressed=False)
    if action == "advance_ticks":
        return advance_runtime_ticks(
            step.ticks or int(args.get("count", 1)),
            state_updates=args.get("state_updates", {}),
            events=args.get("events", []),
        )
    if action == "capture_viewport":
        path_value = str(args.get("actual_path", "")).strip()
        if path_value:
            add_runtime_screenshot(path_value)
        return get_runtime_snapshot()
    return get_runtime_snapshot()


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


def _execute_step_scenario(
    *,
    spec: ScenarioSpec,
    project_root: Path,
    runtime_snapshot: RuntimeSnapshot | None,
) -> ScenarioResult:
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
        snapshot = _execute_step_action(step, spec)
        snapshot = get_runtime_snapshot()
        step_status = "PASS"
        step_observations: list[str] = []

        expected_scene = step.expect_scene or ""
        if expected_scene and (snapshot is None or snapshot.active_scene != expected_scene):
            step_status = "FAIL"
            step_observations.append(
                f"Expected active scene {expected_scene}, got {snapshot.active_scene if snapshot else '(none)'}."
            )

        state = runtime_state_dict(snapshot).get("state", {})
        for key, expected_value in step.expect_state.items():
            actual_value = state.get(key)
            if actual_value != expected_value:
                step_status = "FAIL"
                step_observations.append(f"State mismatch for {key}: expected {expected_value!r}, got {actual_value!r}.")

        if step.expect_events:
            recent_events = {event.name for event in runtime_events_since(before_tick)}
            missing = [name for name in step.expect_events if name not in recent_events]
            if missing:
                step_status = "FAIL"
                step_observations.append("Missing events: " + ", ".join(missing))

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
    auto_generate: bool = True,
) -> PlaytestReport:
    specs = _load_scenario_specs(directory)
    if auto_generate:
        specs.extend(generate_scenario_specs(project_root, existing_specs=specs))
    scenarios = select_relevant_scenarios(
        changed_files,
        impact_report,
        directory=directory,
        intent_profile=intent_profile,
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

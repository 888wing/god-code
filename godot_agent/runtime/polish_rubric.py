"""Demo-polish rubric checks layered on top of technical playtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.runtime.design_memory import (
    DesignMemory,
    GameplayIntentProfile,
    resolved_polish_profile,
    resolved_quality_target,
)
from godot_agent.runtime.playtest_harness import PlaytestReport
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot


@dataclass
class PolishCheck:
    description: str
    observed_output: str
    status: str  # PASS / WARN / FAIL / PARTIAL


@dataclass
class PolishRubricReport:
    checks: list[PolishCheck] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = {check.status for check in self.checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "PARTIAL" in statuses or "WARN" in statuses:
            return "PARTIAL"
        return "PASS"


def _append(report: PolishRubricReport, description: str, observed_output: str, status: str) -> None:
    report.checks.append(
        PolishCheck(
            description=description,
            observed_output=observed_output,
            status=status,
        )
    )


def _playtest_terms(playtest_report: PlaytestReport | None) -> str:
    if playtest_report is None:
        return ""
    parts: list[str] = []
    for scenario in playtest_report.scenarios:
        parts.append(scenario.id)
        parts.append(scenario.title)
        parts.extend(scenario.observations)
    return " ".join(parts).lower()


def _scenario_ids(playtest_report: PlaytestReport | None) -> set[str]:
    if playtest_report is None:
        return set()
    return {scenario.id for scenario in playtest_report.scenarios}


def _changed_file_terms(changed_files: set[str]) -> list[str]:
    return [Path(path).name.lower() for path in changed_files]


def _read_changed_text(project_root: Path, changed_files: set[str]) -> str:
    chunks: list[str] = []
    for path_str in changed_files:
        path = Path(path_str)
        if not path.exists():
            candidate = project_root / path_str
            path = candidate if candidate.exists() else path
        if not path.exists() or path.suffix.lower() not in {".gd", ".tscn", ".txt", ".md"}:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[:2000].lower())
        except OSError:
            continue
    return "\n".join(chunks)


def evaluate_demo_polish(
    *,
    project_root: Path,
    changed_files: set[str],
    design_memory: DesignMemory,
    intent_profile: GameplayIntentProfile,
    runtime_snapshot: RuntimeSnapshot | None,
    playtest_report: PlaytestReport | None,
) -> PolishRubricReport:
    report = PolishRubricReport()
    quality_target = resolved_quality_target(design_memory)
    polish_profile = resolved_polish_profile(design_memory, quality_target=quality_target)

    _append(
        report,
        "Quality target",
        f"Project quality target is `{quality_target}`.",
        "PASS",
    )

    if quality_target != "demo":
        return report

    if runtime_snapshot and runtime_snapshot.screenshot_paths:
        _append(
            report,
            "Visual evidence for demo-quality review",
            f"Captured {len(runtime_snapshot.screenshot_paths)} screenshot artifact(s) for review.",
            "PASS",
        )
    else:
        _append(
            report,
            "Visual evidence for demo-quality review",
            "No screenshot or viewport evidence was captured. Demo-quality review is therefore incomplete.",
            "WARN",
        )

    playtest_text = _playtest_terms(playtest_report)
    scenario_ids = _scenario_ids(playtest_report)
    if playtest_report is None:
        _append(
            report,
            "Playtest coverage for demo readiness",
            "No playtest report was available for demo-quality validation.",
            "WARN",
        )
    else:
        _append(
            report,
            "Playtest coverage for demo readiness",
            f"Playtest verdict is {playtest_report.verdict}.",
            "PASS" if playtest_report.verdict == "PASS" else "PARTIAL",
        )
        if not any(scenario_id.startswith("demo_") for scenario_id in scenario_ids):
            _append(
                report,
                "Demo-specific contract coverage",
                "No demo-specific scripted scenario was executed for this review.",
                "WARN",
            )
        else:
            _append(
                report,
                "Demo-specific contract coverage",
                "Demo-specific scripted contracts were exercised in the current playtest run.",
                "PASS",
            )

    if intent_profile.genre == "bullet_hell":
        missing_focus: list[str] = []
        focus_terms = {
            "wave_timing": ("wave", "staggered", "pacing"),
            "pattern_readability": ("pattern", "readability", "baseline", "diff"),
            "boss_phase_clear": ("phase", "boss", "clear", "cleanup"),
        }
        for focus in intent_profile.testing_focus:
            terms = focus_terms.get(focus, (focus.replace("_", " "),))
            if not any(term in playtest_text for term in terms):
                missing_focus.append(focus)
        if missing_focus:
            _append(
                report,
                "Bullet-hell coverage depth",
                "Demo review is missing explicit coverage for: " + ", ".join(missing_focus),
                "WARN",
            )
        else:
            _append(
                report,
                "Bullet-hell coverage depth",
                "Playtest output references wave, pattern, and phase-oriented checks.",
                "PASS",
            )
        if "demo_boss_transition" in scenario_ids and (
            "phase banner visible" in playtest_text
            or "demo transition announces phase" in playtest_text
            or "screen flash" in playtest_text
        ):
            _append(
                report,
                "Boss telegraph cues",
                "Boss transition coverage includes banner/flash readability assertions.",
                "PASS",
            )
        else:
            _append(
                report,
                "Boss telegraph cues",
                "Demo-quality bullet-hell review did not capture strong boss telegraph cues.",
                "WARN",
            )

    changed_text = _read_changed_text(project_root, changed_files)
    file_terms = " ".join(_changed_file_terms(changed_files))
    if intent_profile.genre == "bullet_hell":
        drift_terms = ("turret", "tower defense", "place_turret", "build_tower")
        if any(term in changed_text or term in file_terms for term in drift_terms):
            _append(
                report,
                "Genre copy drift",
                "Changed files still reference turret-defense language inside a bullet-hell project.",
                "WARN",
            )

    if polish_profile.combat_feedback == "required":
        feedback_terms = ("flash", "shake", "explosion", "telegraph", "hit", "impact")
        runtime_feedback_present = (
            "hit_feedback" in playtest_text
            or "screen_flash" in playtest_text
            or "enemy_defeated" in playtest_text
        )
        if changed_files and any(term in changed_text for term in feedback_terms):
            _append(
                report,
                "Combat feedback hooks",
                "Changed content includes feedback-oriented hooks or language.",
                "PASS",
            )
        elif not changed_files and runtime_feedback_present:
            _append(
                report,
                "Combat feedback hooks",
                "Runtime playtest evidence demonstrates hit, flash, or defeat feedback even without a code diff context.",
                "PASS",
            )
        else:
            _append(
                report,
                "Combat feedback hooks",
                "No strong hit/telegraph/explosion feedback cues were detected in the changed files.",
                "WARN",
            )

    if "hit_feedback" in playtest_text or "screen_flash" in playtest_text or "enemy_defeated" in playtest_text:
        _append(
            report,
            "Runtime feedback evidence",
            "Playtest output includes runtime evidence for hit, flash, or defeat feedback.",
            "PASS",
        )
    elif quality_target == "demo":
        _append(
            report,
            "Runtime feedback evidence",
            "No explicit runtime feedback evidence was found in the current playtest output.",
            "WARN",
        )

    return report

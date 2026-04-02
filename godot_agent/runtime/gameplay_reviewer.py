"""Gameplay-oriented reviewer checks layered on top of technical validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.design_memory import DesignMemory
from godot_agent.runtime.playtest_harness import PlaytestReport, format_playtest_report
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, format_runtime_snapshot


@dataclass
class GameplayCheck:
    description: str
    observed_output: str
    status: str


@dataclass
class GameplayReviewReport:
    checks: list[GameplayCheck] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = {check.status for check in self.checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "PARTIAL" in statuses:
            return "PARTIAL"
        return "PASS"


def review_gameplay_constraints(
    *,
    project_root: Path,
    changed_files: set[str],
    design_memory: DesignMemory,
    impact_report: ImpactAnalysisReport | None,
    runtime_snapshot: RuntimeSnapshot | None,
    playtest_report: PlaytestReport | None,
) -> GameplayReviewReport:
    _ = project_root
    report = GameplayReviewReport()
    changed_rel = {Path(path).name for path in changed_files}

    if design_memory.is_empty:
        report.checks.append(
            GameplayCheck(
                description="Design memory coverage",
                observed_output="No project design memory is defined, so gameplay intent cannot be checked robustly.",
                status="PASS",
            )
        )
    else:
        report.checks.append(
            GameplayCheck(
                description="Design memory coverage",
                observed_output=f"Loaded {len(design_memory.pillars)} gameplay pillars and {len(design_memory.control_rules)} control rules.",
                status="PASS",
            )
        )

    changed_scenes = {f"res://{Path(path).name}" for path in changed_files if path.endswith(".tscn")}
    undocumented = [scene for scene in changed_scenes if scene not in design_memory.scene_ownership]
    if undocumented:
        report.checks.append(
            GameplayCheck(
                description="Scene ownership coverage",
                observed_output="Changed scenes without design ownership notes: " + ", ".join(sorted(undocumented)),
                status="PARTIAL",
            )
        )
    elif changed_scenes:
        report.checks.append(
            GameplayCheck(
                description="Scene ownership coverage",
                observed_output="All changed scenes are represented in design memory ownership notes.",
                status="PASS",
            )
        )

    if impact_report and impact_report.input_actions:
        if runtime_snapshot and set(impact_report.input_actions) & set(runtime_snapshot.input_actions):
            report.checks.append(
                GameplayCheck(
                    description="Input-sensitive gameplay review",
                    observed_output="Runtime snapshot includes impacted input actions: " + ", ".join(sorted(set(impact_report.input_actions) & set(runtime_snapshot.input_actions))),
                    status="PASS",
                )
            )
        else:
            report.checks.append(
                GameplayCheck(
                    description="Input-sensitive gameplay review",
                    observed_output="Impacted input actions were inferred (" + ", ".join(impact_report.input_actions) + ") but no runtime input evidence was captured.",
                    status="PARTIAL",
                )
            )

    if runtime_snapshot is not None:
        status = "FAIL" if runtime_snapshot.errors else "PASS"
        report.checks.append(
            GameplayCheck(
                description="Runtime snapshot health",
                observed_output=format_runtime_snapshot(runtime_snapshot),
                status=status,
            )
        )

    if playtest_report is not None:
        report.checks.append(
            GameplayCheck(
                description="Scenario playtest review",
                observed_output=format_playtest_report(playtest_report),
                status=playtest_report.verdict,
            )
        )

    if design_memory.non_goals:
        mentioned = [goal for goal in design_memory.non_goals if any(token.lower() in " ".join(changed_rel).lower() for token in goal.split())]
        if mentioned:
            report.checks.append(
                GameplayCheck(
                    description="Non-goal drift check",
                    observed_output="Changed files overlap with declared non-goals: " + ", ".join(mentioned),
                    status="PARTIAL",
                )
            )

    return report

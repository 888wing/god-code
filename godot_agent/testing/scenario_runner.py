"""Helpers for building runtime snapshots and scenario reports in tests."""

from __future__ import annotations

from pathlib import Path

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.playtest_harness import PlaytestReport, run_playtest_harness
from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot


def make_runtime_snapshot(
    *,
    active_scene: str = "",
    node_paths: list[str] | None = None,
    event_names: list[str] | None = None,
    input_actions: list[str] | None = None,
    errors: list[str] | None = None,
) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        active_scene=active_scene,
        nodes=[RuntimeNodeState(path=path, type=path.split("/")[-1] or "Node") for path in (node_paths or [])],
        events=[RuntimeEvent(name=name) for name in (event_names or [])],
        input_actions=list(input_actions or []),
        errors=list(errors or []),
    )


def run_scenario_report(
    *,
    project_root: Path,
    changed_files: set[str],
    runtime_snapshot: RuntimeSnapshot | None = None,
    impact_report: ImpactAnalysisReport | None = None,
) -> PlaytestReport:
    return run_playtest_harness(
        project_root=project_root,
        changed_files=changed_files,
        impact_report=impact_report,
        runtime_snapshot=runtime_snapshot,
    )

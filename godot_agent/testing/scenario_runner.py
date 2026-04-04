"""Helpers for building runtime snapshots and scenario reports in tests."""

from __future__ import annotations

from pathlib import Path

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.playtest_harness import PlaytestReport, run_playtest_harness
from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot


def make_runtime_snapshot(
    *,
    active_scene: str = "",
    current_tick: int = 0,
    node_paths: list[str] | None = None,
    event_names: list[str] | None = None,
    input_actions: list[str] | None = None,
    errors: list[str] | None = None,
    state: dict | None = None,
    fixtures: dict | None = None,
    screenshot_paths: list[str] | None = None,
    source: str = "synthetic",
    evidence_level: str = "low",
    bridge_connected: bool = False,
) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        active_scene=active_scene,
        current_tick=current_tick,
        nodes=[RuntimeNodeState(path=path, type=path.split("/")[-1] or "Node") for path in (node_paths or [])],
        events=[RuntimeEvent(name=name) for name in (event_names or [])],
        input_actions=list(input_actions or []),
        state=dict(state or {}),
        fixtures=dict(fixtures or {}),
        errors=list(errors or []),
        screenshot_paths=list(screenshot_paths or []),
        source=source,
        evidence_level=evidence_level,
        bridge_connected=bridge_connected,
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

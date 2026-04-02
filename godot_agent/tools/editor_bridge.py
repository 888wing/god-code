"""Tools backed by the runtime/editor bridge."""

from __future__ import annotations

from pydantic import BaseModel, Field

from godot_agent.godot.impact_analysis import analyze_change_impact, format_impact_report
from godot_agent.runtime.playtest_harness import format_playtest_report, run_playtest_harness
from godot_agent.runtime.runtime_bridge import (
    format_runtime_snapshot,
    get_runtime_snapshot,
    runtime_snapshot_dict,
)
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class GetRuntimeSnapshotTool(BaseTool):
    name = "get_runtime_snapshot"
    description = "Read the latest runtime/editor bridge snapshot if one is available."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")

    class Output(BaseModel):
        report: str
        snapshot: dict

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        _, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        snapshot = get_runtime_snapshot()
        return ToolResult(output=self.Output(report=format_runtime_snapshot(snapshot), snapshot=runtime_snapshot_dict(snapshot)))


class RunPlaytestTool(BaseTool):
    name = "run_playtest"
    description = "Run the scenario-based playtest harness against the latest runtime snapshot."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        changed_files: list[str] = Field(default_factory=list, description="Absolute paths that were changed")

    class Output(BaseModel):
        report: str
        verdict: str
        scenarios: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        impact_report = analyze_change_impact(project_path, set(input.changed_files))
        report = run_playtest_harness(
            project_root=project_path,
            changed_files=set(input.changed_files),
            impact_report=impact_report,
            runtime_snapshot=get_runtime_snapshot(),
        )
        return ToolResult(
            output=self.Output(
                report=format_impact_report(impact_report) + "\n\n" + format_playtest_report(report),
                verdict=report.verdict,
                scenarios=[scenario.__dict__ for scenario in report.scenarios],
            )
        )

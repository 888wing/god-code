"""Tools backed by the runtime/editor bridge."""

from __future__ import annotations

from pydantic import BaseModel, Field

from godot_agent.godot.impact_analysis import analyze_change_impact, format_impact_report
from godot_agent.runtime.design_memory import (
    load_design_memory,
    resolved_quality_target,
)
from godot_agent.runtime.gameplay_reviewer import review_gameplay_constraints
from godot_agent.runtime.playtest_harness import (
    format_playtest_report,
    list_contracts,
    list_scenario_specs,
    run_playtest_harness,
    run_scripted_playtest,
)
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
        gameplay_review_verdict: str = ""
        gameplay_checks: list[dict] = Field(default_factory=list)

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
            design_memory=load_design_memory(project_path),
        )
        design_memory = load_design_memory(project_path)
        gameplay_review = review_gameplay_constraints(
            project_root=project_path,
            changed_files=set(input.changed_files),
            design_memory=design_memory,
            intent_profile=design_memory.gameplay_intent,
            impact_report=impact_report,
            runtime_snapshot=get_runtime_snapshot(),
            playtest_report=report,
        )
        return ToolResult(
            output=self.Output(
                report=(
                    format_impact_report(impact_report)
                    + "\n\n"
                    + format_playtest_report(report)
                    + "\n\n"
                    + "\n".join(
                        f"- {check.description} [{check.status}]\n  {check.observed_output}"
                        for check in gameplay_review.checks
                    )
                ),
                verdict=report.verdict,
                scenarios=[scenario.__dict__ for scenario in report.scenarios],
                gameplay_review_verdict=gameplay_review.verdict,
                gameplay_checks=[check.__dict__ for check in gameplay_review.checks],
            )
        )


class ListScenariosTool(BaseTool):
    name = "list_scenarios"
    description = "List built-in playtest scenarios and show which ones are relevant to the current gameplay profile."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        include_generated: bool = Field(default=False, description="Include auto-generated baseline scenarios")

    class Output(BaseModel):
        quality_target: str
        scenarios: list[dict[str, object]]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        design_memory = load_design_memory(project_path)
        return ToolResult(
            output=self.Output(
                quality_target=resolved_quality_target(design_memory),
                scenarios=list_scenario_specs(
                    project_root=project_path,
                    intent_profile=design_memory.gameplay_intent,
                    quality_target=resolved_quality_target(design_memory),
                    include_generated=input.include_generated,
                ),
            )
        )


class ListContractsTool(BaseTool):
    name = "list_contracts"
    description = "List detailed scripted-route contracts for the current gameplay profile or a specific scenario id."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        scenario_id: str = Field(default="", description="Optional scenario id to inspect in detail")
        include_generated: bool = Field(default=False, description="Include generated scenarios when listing contracts")
        show_all: bool = Field(default=False, description="Show all built-in contracts instead of only those matching the current profile")

    class Output(BaseModel):
        quality_target: str
        contracts: list[dict[str, object]]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        design_memory = load_design_memory(project_path)
        quality_target = resolved_quality_target(design_memory)
        return ToolResult(
            output=self.Output(
                quality_target=quality_target,
                contracts=list_contracts(
                    project_root=project_path,
                    scenario_id=input.scenario_id,
                    intent_profile=design_memory.gameplay_intent,
                    quality_target=quality_target,
                    include_generated=input.include_generated,
                    match_profile=not input.show_all,
                ),
            )
        )


class RunScriptedPlaytestTool(BaseTool):
    name = "run_scripted_playtest"
    description = "Run scripted-route playtest contracts against the runtime harness or the latest live runtime snapshot."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        scenario_ids: list[str] = Field(default_factory=list, description="Optional explicit scripted scenario ids to run")
        changed_files: list[str] = Field(default_factory=list, description="Changed files used to select relevant scripted scenarios when scenario_ids is empty")
        run_all: bool = Field(default=False, description="Run all built-in scripted scenarios instead of only relevant or explicit ids")

    class Output(BaseModel):
        report: str
        verdict: str
        scenarios: list[dict]
        gameplay_review_verdict: str = ""
        gameplay_checks: list[dict] = Field(default_factory=list)

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        design_memory = load_design_memory(project_path)
        impact_report = analyze_change_impact(project_path, set(input.changed_files))
        report = run_scripted_playtest(
            project_root=project_path,
            scenario_ids=input.scenario_ids,
            changed_files=set(input.changed_files),
            impact_report=impact_report,
            runtime_snapshot=get_runtime_snapshot(),
            design_memory=design_memory,
            intent_profile=design_memory.gameplay_intent,
            run_all=input.run_all,
        )
        gameplay_review = review_gameplay_constraints(
            project_root=project_path,
            changed_files=set(input.changed_files),
            design_memory=design_memory,
            intent_profile=design_memory.gameplay_intent,
            impact_report=impact_report,
            runtime_snapshot=get_runtime_snapshot(),
            playtest_report=report,
        )
        return ToolResult(
            output=self.Output(
                report=(
                    format_playtest_report(report)
                    + "\n\n"
                    + "\n".join(
                        f"- {check.description} [{check.status}]\n  {check.observed_output}"
                        for check in gameplay_review.checks
                    )
                ),
                verdict=report.verdict,
                scenarios=[scenario.__dict__ for scenario in report.scenarios],
                gameplay_review_verdict=gameplay_review.verdict,
                gameplay_checks=[check.__dict__ for check in gameplay_review.checks],
            )
        )

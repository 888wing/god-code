"""Project-level Godot analysis tools."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.godot.consistency_checker import check_consistency, format_consistency_report
from godot_agent.godot.dependency_graph import build_dependency_graph
from godot_agent.godot.impact_analysis import analyze_change_impact, format_impact_report
from godot_agent.runtime.error_loop import format_validation_for_llm, validate_project
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class ValidateProjectTool(BaseTool):
    name = "validate_project"
    description = "Run Godot headless validation for the current project."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        godot_path: str = Field(default="godot", description="Path to the Godot executable")

    class Output(BaseModel):
        success: bool
        report: str
        errors: list[dict]
        warnings: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        result = await validate_project(str(project_path), godot_path=input.godot_path, timeout=30)
        return ToolResult(
            output=self.Output(
                success=result.success,
                report=format_validation_for_llm(result),
                errors=[error.__dict__ for error in result.errors],
                warnings=[warning.__dict__ for warning in result.warnings],
            )
        )


class CheckConsistencyTool(BaseTool):
    name = "check_consistency"
    description = "Run cross-file Godot consistency checks."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")

    class Output(BaseModel):
        issue_count: int
        report: str
        issues: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        issues = check_consistency(project_path)
        return ToolResult(
            output=self.Output(
                issue_count=len(issues),
                report=format_consistency_report(issues),
                issues=[issue.__dict__ for issue in issues],
            )
        )


class ProjectDependencyGraphTool(BaseTool):
    name = "project_dependency_graph"
    description = "Build a dependency graph for scenes, scripts, resources, and autoloads."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")

    class Output(BaseModel):
        summary: str
        nodes: dict[str, dict]
        autoloads: dict[str, str]
        main_scene: str

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        graph = build_dependency_graph(project_path)
        return ToolResult(
            output=self.Output(
                summary=graph.format_summary(),
                nodes={
                    path: {
                        "type": node.type,
                        "depends_on": node.depends_on,
                        "depended_by": node.depended_by,
                    }
                    for path, node in graph.nodes.items()
                },
                autoloads=graph.autoloads,
                main_scene=graph.main_scene,
            )
        )


class AnalyzeImpactTool(BaseTool):
    name = "analyze_impact"
    description = "Analyze which files, scenes, autoloads, and validation steps are affected by a change."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        changed_files: list[str] = Field(default_factory=list, description="Absolute paths that are expected to change")

    class Output(BaseModel):
        report: str
        affected_files: list[str]
        validation_focus: list[str]
        input_actions: list[str]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        report = analyze_change_impact(project_path, set(input.changed_files))
        return ToolResult(
            output=self.Output(
                report=format_impact_report(report),
                affected_files=report.affected_files,
                validation_focus=report.validation_focus,
                input_actions=report.input_actions,
            )
        )

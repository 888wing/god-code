"""Tools for reading and updating project design memory."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.runtime.design_memory import format_design_memory, load_design_memory, update_design_memory
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class ReadDesignMemoryTool(BaseTool):
    name = "read_design_memory"
    description = "Read the project's persistent design memory and gameplay constraints."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")

    class Output(BaseModel):
        report: str
        memory: dict

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        memory = load_design_memory(project_path)
        return ToolResult(output=self.Output(report=format_design_memory(memory), memory=memory.__dict__))


class UpdateDesignMemoryTool(BaseTool):
    name = "update_design_memory"
    description = "Persist gameplay intent, non-goals, and scene ownership notes into project design memory."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        section: str = Field(description="Section name, e.g. pillars, control_rules, scene_ownership, mechanic_notes:combat")
        text: str = Field(default="", description="Freeform text value for scalar sections")
        items: list[str] = Field(default_factory=list, description="List values for list sections")
        mapping: dict[str, str] = Field(default_factory=dict, description="Mapping values for dict sections")
        append: bool = Field(default=False, description="Append/merge into the existing section")

    class Output(BaseModel):
        report: str
        memory: dict

    def is_destructive(self) -> bool:
        return False

    def validate_input(self, input: Input) -> str | None:
        if not input.text and not input.items and not input.mapping:
            return "Provide text, items, or mapping to update design memory."
        return None

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        try:
            memory = update_design_memory(
                project_path,
                section=input.section,
                text=input.text,
                items=input.items,
                mapping=input.mapping,
                append=input.append,
            )
        except ValueError as exc:
            return ToolResult(error=str(exc))
        return ToolResult(output=self.Output(report=format_design_memory(memory), memory=memory.__dict__))

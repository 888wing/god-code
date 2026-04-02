"""Godot-aware GDScript tools."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.godot.gdscript_linter import format_lint_report, lint_gdscript
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class ReadScriptTool(BaseTool):
    name = "read_script"
    description = "Read a GDScript file with line numbers."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .gd file")
        offset: int = Field(default=0, description="Start line (0-indexed)")
        limit: int = Field(default=400, description="Max lines to read")

    class Output(BaseModel):
        content: str
        line_count: int

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".gd"):
            return "read_script only works on .gd files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        selected = lines[input.offset: input.offset + input.limit]
        content = "".join(f"{input.offset + idx + 1}\t{line}" for idx, line in enumerate(selected))
        return ToolResult(output=self.Output(content=content, line_count=len(selected)))


class EditScriptTool(BaseTool):
    name = "edit_script"
    description = "Replace a specific string in a GDScript file. Prefer this over generic edit_file for .gd files."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .gd file")
        old_string: str = Field(description="Exact text to replace")
        new_string: str = Field(description="Replacement text")
        replace_all: bool = Field(default=False, description="Replace every matching occurrence")

    class Output(BaseModel):
        replacements: int

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".gd"):
            return "edit_script only works on .gd files"
        if input.old_string == input.new_string:
            return "old_string and new_string are identical"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count(input.old_string)
        if count == 0:
            return ToolResult(error=f"old_string not found in {input.path}")
        if count > 1 and not input.replace_all:
            return ToolResult(error=f"old_string found {count} times; use replace_all=true or provide more context")

        replacements = count if input.replace_all else 1
        new_text = text.replace(input.old_string, input.new_string, -1 if input.replace_all else 1)
        path.write_text(new_text, encoding="utf-8")
        return ToolResult(output=self.Output(replacements=replacements))


class LintScriptTool(BaseTool):
    name = "lint_script"
    description = "Run the built-in GDScript linter on a .gd file."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .gd file")

    class Output(BaseModel):
        issue_count: int
        report: str
        issues: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".gd"):
            return "lint_script only works on .gd files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        issues = lint_gdscript(text, path.name)
        return ToolResult(
            output=self.Output(
                issue_count=len(issues),
                report=format_lint_report(issues, path.name),
                issues=[
                    {
                        "line": issue.line,
                        "severity": issue.severity,
                        "rule": issue.rule,
                        "message": issue.message,
                    }
                    for issue in issues
                ],
            )
        )

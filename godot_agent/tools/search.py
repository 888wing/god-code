from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class GrepTool(BaseTool):
    """Search for a regex pattern in files, returning matching lines."""

    name = "grep"
    description = (
        "Search for a regex pattern in files. "
        "Returns matching lines with file paths and line numbers."
    )

    class Input(BaseModel):
        pattern: str = Field(description="Regex pattern to search for")
        path: str = Field(description="Directory to search in")
        glob: str = Field(default="*", description="File glob filter (e.g. '*.gd')")

    class Output(BaseModel):
        matches: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        try:
            root, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            regex = re.compile(input.pattern)
            matches: list[dict] = []
            for f in sorted(root.rglob(input.glob)):
                if not f.is_file():
                    continue
                try:
                    for i, line in enumerate(
                        f.read_text(errors="replace").splitlines(), 1
                    ):
                        if regex.search(line):
                            matches.append(
                                {"file": str(f), "line": i, "content": line.rstrip()}
                            )
                except (UnicodeDecodeError, PermissionError):
                    continue
            return ToolResult(output=self.Output(matches=matches[:200]))
        except Exception as e:
            return ToolResult(error=str(e))


class GlobTool(BaseTool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = "Find files matching a glob pattern."

    class Input(BaseModel):
        pattern: str = Field(description="Glob pattern (e.g. '**/*.gd')")
        path: str = Field(description="Root directory to search from")

    class Output(BaseModel):
        files: list[str]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        try:
            root, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            files = sorted(
                str(f) for f in root.glob(input.pattern) if f.is_file()
            )
            return ToolResult(output=self.Output(files=files[:500]))
        except Exception as e:
            return ToolResult(error=str(e))

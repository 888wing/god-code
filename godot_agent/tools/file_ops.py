"""File operation tools with path containment security."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult

# Set by CLI at startup — all file ops restricted to this directory
_project_root: Path | None = None


def set_project_root(root: Path) -> None:
    """Set the project root for path containment. Called by CLI on startup."""
    global _project_root
    _project_root = root.resolve()


def _validate_path(path_str: str) -> tuple[Path, str | None]:
    """Resolve and validate a path is within project root. Returns (path, error)."""
    p = Path(path_str).resolve()
    if _project_root and not str(p).startswith(str(_project_root)):
        return p, f"Access denied: {path_str} is outside project root {_project_root}"
    return p, None


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Supports .gd, .tscn, .tres, .json, .cfg, .gdshader and any text file."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the file")
        offset: int = Field(default=0, description="Start line (0-indexed)")
        limit: int = Field(default=2000, description="Max lines to read")

    class Output(BaseModel):
        content: str
        line_count: int

    async def execute(self, input: Input) -> ToolResult:
        try:
            p, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            if not p.exists():
                return ToolResult(error=f"File not found: {input.path}")
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines(keepends=True)
            selected = lines[input.offset : input.offset + input.limit]
            content = "".join(
                f"{input.offset + i + 1}\t{line}" for i, line in enumerate(selected)
            )
            return ToolResult(output=self.Output(content=content, line_count=len(selected)))
        except Exception as e:
            return ToolResult(error=str(e))


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Creates parent directories if needed."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the file")
        content: str = Field(description="Content to write")

    class Output(BaseModel):
        bytes_written: int

    async def execute(self, input: Input) -> ToolResult:
        try:
            p, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(input.content, encoding="utf-8")
            return ToolResult(output=self.Output(bytes_written=len(input.content.encode("utf-8"))))
        except Exception as e:
            return ToolResult(error=str(e))


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Replace a specific string in a file. The old_string must be unique within the file."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the file")
        old_string: str = Field(description="Exact text to find and replace")
        new_string: str = Field(description="Replacement text")

    class Output(BaseModel):
        success: bool

    async def execute(self, input: Input) -> ToolResult:
        try:
            p, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            if not p.exists():
                return ToolResult(error=f"File not found: {input.path}")
            text = p.read_text(encoding="utf-8")
            count = text.count(input.old_string)
            if count == 0:
                return ToolResult(error=f"old_string not found in {input.path}")
            if count > 1:
                return ToolResult(error=f"old_string found {count} times, must be unique")
            new_text = text.replace(input.old_string, input.new_string, 1)
            p.write_text(new_text, encoding="utf-8")
            return ToolResult(output=self.Output(success=True))
        except Exception as e:
            return ToolResult(error=str(e))

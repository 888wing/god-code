# godot_agent/tools/list_dir.py
from __future__ import annotations

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and directories at a given path. Shows type (file/dir), size, and name."

    class Input(BaseModel):
        path: str = Field(description="Directory path to list")
        recursive: bool = Field(default=False, description="List recursively")
        pattern: str = Field(default="*", description="Glob filter pattern")

    class Output(BaseModel):
        entries: list[dict]
        total: int

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        try:
            root, err = _validate_path(input.path)
            if err:
                return ToolResult(error=err)
            if not root.exists():
                return ToolResult(error=f"Path not found: {input.path}")
            if not root.is_dir():
                return ToolResult(error=f"Not a directory: {input.path}")

            entries = []
            iter_fn = root.rglob if input.recursive else root.glob
            for item in sorted(iter_fn(input.pattern)):
                entries.append({
                    "name": str(item.relative_to(root)),
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })
                if len(entries) >= 500:
                    break

            return ToolResult(output=self.Output(entries=entries, total=len(entries)))
        except Exception as e:
            return ToolResult(error=str(e))

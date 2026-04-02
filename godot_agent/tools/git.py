from __future__ import annotations

import asyncio
import shlex

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


class GitTool(BaseTool):
    """Run git commands in a specified working directory."""

    name = "git"
    description = (
        "Run git commands. "
        "Supports: status, diff, log, add, commit, branch, checkout."
    )

    class Input(BaseModel):
        command: str = Field(
            description="Git subcommand and flags (e.g. 'status', 'diff', 'log --oneline -5')"
        )
        cwd: str = Field(default=".", description="Working directory for the git command")

    class Output(BaseModel):
        stdout: str
        stderr: str
        exit_code: int

    def validate_input(self, input: Input) -> str | None:
        if not input.command.strip():
            return "Git command cannot be empty"
        return None

    async def execute(self, input: Input) -> ToolResult:
        try:
            args = ["git"] + shlex.split(input.command)
            cwd, err = _validate_path(input.cwd)
            if err:
                return ToolResult(error=err)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            return ToolResult(
                output=self.Output(
                    stdout=stdout.decode(errors="replace"),
                    stderr=stderr.decode(errors="replace"),
                    exit_code=proc.returncode or 0,
                )
            )
        except Exception as e:
            return ToolResult(error=str(e))

# godot_agent/tools/shell.py
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Execute a shell command and return stdout/stderr. Use for build commands, file operations, or any CLI tool."

    class Input(BaseModel):
        command: str = Field(description="Shell command to execute")
        cwd: str = Field(default=".", description="Working directory")
        timeout: int = Field(default=60, description="Timeout in seconds")

    class Output(BaseModel):
        stdout: str
        stderr: str
        exit_code: int

    async def execute(self, input: Input) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=input.cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=input.timeout
            )
            return ToolResult(output=self.Output(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            ))
        except asyncio.TimeoutError:
            return ToolResult(error=f"Command timed out after {input.timeout}s")
        except Exception as e:
            return ToolResult(error=str(e))

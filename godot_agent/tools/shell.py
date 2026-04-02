"""Shell command execution with safety restrictions."""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _project_root

log = logging.getLogger(__name__)

# Commands that are never allowed
_BLOCKED_PATTERNS = [
    r'\brm\s+-rf\s+/',        # rm -rf /
    r'\brm\s+-rf\s+~',        # rm -rf ~
    r'\bcurl\b.*\|.*\bsh\b',  # curl | sh
    r'\bwget\b.*\|.*\bsh\b',  # wget | sh
    r'\bchmod\s+777\b',       # chmod 777
    r'\bsudo\b',              # sudo anything
    r'\bmkfs\b',              # format disk
    r'\bdd\s+if=',            # dd disk operations
]


def _is_blocked(command: str) -> str | None:
    """Check if a command matches blocked patterns. Returns reason or None."""
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"Blocked: command matches dangerous pattern '{pattern}'"
    return None


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Execute a shell command within the project directory. Dangerous commands (sudo, rm -rf /, etc.) are blocked."

    class Input(BaseModel):
        command: str = Field(description="Shell command to execute")
        cwd: str = Field(default=".", description="Working directory")
        timeout: int = Field(default=60, description="Timeout in seconds")

    class Output(BaseModel):
        stdout: str
        stderr: str
        exit_code: int

    async def execute(self, input: Input) -> ToolResult:
        blocked = _is_blocked(input.command)
        if blocked:
            return ToolResult(error=blocked)

        # Restrict cwd to project root
        cwd = input.cwd
        if _project_root and cwd == ".":
            cwd = str(_project_root)

        log.info("shell: %s (cwd=%s)", input.command, cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=input.timeout)
            return ToolResult(output=self.Output(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            ))
        except asyncio.TimeoutError:
            return ToolResult(error=f"Command timed out after {input.timeout}s")
        except Exception as e:
            return ToolResult(error=str(e))

"""Shell command execution with safety restrictions."""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _project_root

log = logging.getLogger(__name__)

# Safety level — set by CLI on startup
_safety_level: str = "normal"  # strict, normal, permissive

def set_safety_level(level: str) -> None:
    global _safety_level
    _safety_level = level

# Patterns blocked at each safety level
_ALWAYS_BLOCKED = [
    r'\brm\s+-rf\s+/',        # rm -rf /
    r'\brm\s+-rf\s+~',        # rm -rf ~
    r'\bmkfs\b',              # format disk
    r'\bdd\s+if=',            # dd disk operations
]

_NORMAL_BLOCKED = _ALWAYS_BLOCKED + [
    r'\bcurl\b.*\|.*\bsh\b',  # curl | sh
    r'\bwget\b.*\|.*\bsh\b',  # wget | sh
    r'\bchmod\s+777\b',       # chmod 777
    r'\bsudo\b',              # sudo anything
]

_STRICT_BLOCKED = _NORMAL_BLOCKED + [
    r'\bcurl\b',              # any curl
    r'\bwget\b',              # any wget
    r'\bnpm\s+install\b',     # npm install
    r'\bpip\s+install\b',     # pip install
    r'\bgit\s+push\b',        # git push
    r'\bgit\s+reset\b',       # git reset
]


def _is_blocked(command: str) -> str | None:
    """Check if a command matches blocked patterns based on safety level."""
    if _safety_level == "permissive":
        patterns = _ALWAYS_BLOCKED
    elif _safety_level == "strict":
        patterns = _STRICT_BLOCKED
    else:
        patterns = _NORMAL_BLOCKED
    for pattern in patterns:
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

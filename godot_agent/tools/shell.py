"""Shell command execution with safety restrictions."""

from __future__ import annotations

import asyncio
import logging
import os
import re

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _project_root, _validate_path

log = logging.getLogger(__name__)

# Safety level — set by CLI on startup
_safety_level: str = "normal"  # strict, normal, permissive

def set_safety_level(level: str) -> None:
    global _safety_level
    _safety_level = level

# Environment variables that may carry credentials/secrets — filtered from
# subprocess env so commands like `env` cannot exfiltrate them. Matches any
# name containing these substrings (case-insensitive).
_SECRET_ENV_SUBSTRING = re.compile(
    r'(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|PRIVATE|CERT)',
    re.IGNORECASE,
)


def _build_safe_env() -> dict[str, str]:
    """Return a copy of os.environ with credential-bearing variables removed.

    This is defense-in-depth against an LLM being tricked into running `env`,
    `printenv`, or `cat $SECRET_FILE`: even if the command executes, the
    sensitive environment values are not available to the subprocess.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not _SECRET_ENV_SUBSTRING.search(name)
    }

# Patterns blocked at each safety level
_ALWAYS_BLOCKED = [
    r'\brm\s+-rf\s+/',        # rm -rf /
    r'\brm\s+-rf\s+~',        # rm -rf ~
    r'\bmkfs\b',              # format disk
    r'\bdd\s+if=',            # dd disk operations
    # Credential file access (read or write)
    r'\.config/god-code',     # god-code config + oauth store
    r'\.codex/auth',          # Codex CLI credentials
    r'\.aws/credentials',     # AWS credentials file
    r'\.ssh/id_',             # SSH private keys
    r'\.ssh/authorized_keys', # SSH authorized keys (tampering)
    r'\.netrc',               # ~/.netrc credential store
    r'\.npmrc',               # npm auth tokens
    r'\.pypirc',              # PyPI credentials
    # Environment dumping (env VAR=val cmd is still allowed because
    # the `VAR=val` form is typed directly as a shell prefix, not via `env`)
    r'\bprintenv\b',                              # printenv dumps all or one var
    r'(^|[|;&`]|\|\|)\s*env\s*($|[|;&`])',        # bare `env` or `... | env`
    r'(^|[|;&`]|\|\|)\s*env\s+-',                 # `env -i`, `env -u VAR`
    r'(^|[|;&`]|\|\|)\s*set\s*($|\|)',            # bare `set` (dumps shell vars)
    r'(^|[|;&`]|\|\|)\s*export\s*($|\|)',         # bare `export` (lists exports)
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
        elif cwd != ".":
            resolved_cwd, err = _validate_path(cwd)
            if err:
                return ToolResult(error=err)
            cwd = str(resolved_cwd)

        log.info("shell: %s (cwd=%s)", input.command, cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=_build_safe_env(),
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

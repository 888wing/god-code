"""Automated error detection and fix loop for Godot projects.

Runs godot --headless, parses errors, and provides structured
error reports that the conversation engine can act on.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GodotError:
    level: str  # "ERROR" or "WARNING"
    file: str
    line: int | None
    message: str
    category: str = "unknown"  # "parse", "resource", "script", "scene"

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.level}] {loc} — {self.message}"


@dataclass
class ValidationResult:
    success: bool
    errors: list[GodotError] = field(default_factory=list)
    warnings: list[GodotError] = field(default_factory=list)
    raw_output: str = ""
    suggestion: str = ""


def _categorize_error(message: str, file_path: str) -> str:
    """Categorize an error for targeted fixing."""
    msg_lower = message.lower()
    if "parse" in msg_lower or "invalid" in msg_lower:
        return "parse"
    if "resource" in msg_lower or "failed loading" in msg_lower:
        return "resource"
    if file_path.endswith(".gd"):
        return "script"
    if file_path.endswith(".tscn") or file_path.endswith(".tres"):
        return "scene"
    return "unknown"


def _suggest_fix(error: GodotError) -> str:
    """Generate a fix suggestion based on error pattern."""
    msg = error.message.lower()

    if "sub_resource" in msg or "invalid parameter" in msg:
        return "Move [sub_resource] declarations before all [node] declarations in the .tscn file."

    if "failed loading resource" in msg:
        return f"Check that {error.file} exists and the path in the referencing scene is correct."

    if "identifier" in msg and "not declared" in msg:
        return f"Check for typos in variable/function names at {error.file}:{error.line}."

    if "invalid operands" in msg:
        return f"Type mismatch in expression at {error.file}:{error.line}. Check operand types."

    if "class_name" in msg:
        return "Ensure class_name is declared before extends, and the name is unique across the project."

    return f"Read {error.file} around line {error.line or '?'} and fix the reported issue."


def parse_godot_output(output: str) -> list[GodotError]:
    """Parse Godot's stdout/stderr into structured errors."""
    errors: list[GodotError] = []
    for line in output.splitlines():
        # Match: ERROR: res://path:line - message
        # or:    ERROR: message [Resource file res://path:line]
        m = re.match(r'(?:\[.*?\])?\s*(ERROR|WARNING):\s*(.*)', line)
        if not m:
            continue
        level = m.group(1)
        rest = m.group(2)

        # Try pattern: res://file:line - message
        fm = re.match(r'(res://[^:\s]+)(?::(\d+))?\s*[-–—]?\s*(.*)', rest)
        if fm:
            errors.append(GodotError(
                level=level,
                file=fm.group(1),
                line=int(fm.group(2)) if fm.group(2) else None,
                message=fm.group(3).strip(),
                category=_categorize_error(fm.group(3), fm.group(1)),
            ))
            continue

        # Try pattern: message [Resource file res://path:line]
        rm = re.match(r'(.*?)\s*\[Resource file (res://[^:\]]+)(?::(\d+))?\]', rest)
        if rm:
            errors.append(GodotError(
                level=level,
                file=rm.group(2),
                line=int(rm.group(3)) if rm.group(3) else None,
                message=rm.group(1).strip(),
                category=_categorize_error(rm.group(1), rm.group(2)),
            ))
            continue

        # Generic error without file reference
        if level == "ERROR":
            errors.append(GodotError(
                level=level, file="", line=None,
                message=rest.strip(), category="unknown",
            ))

    return errors


async def validate_project(
    project_path: str,
    godot_path: str = "godot",
    timeout: int = 30,
) -> ValidationResult:
    """Run godot --headless --quit and return structured validation result."""
    try:
        proc = await asyncio.create_subprocess_exec(
            godot_path, "--headless", "--quit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        raw = stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")
    except asyncio.TimeoutError:
        return ValidationResult(
            success=False, raw_output="", suggestion="Godot timed out. Check for infinite loops in _ready()."
        )
    except FileNotFoundError:
        return ValidationResult(
            success=False, raw_output="", suggestion=f"Godot not found at '{godot_path}'. Set godot_path in config."
        )

    parsed = parse_godot_output(raw)
    errors = [e for e in parsed if e.level == "ERROR"]
    warnings = [e for e in parsed if e.level == "WARNING"]

    suggestion = ""
    if errors:
        # Generate suggestion from first error
        suggestion = _suggest_fix(errors[0])

    return ValidationResult(
        success=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        raw_output=raw,
        suggestion=suggestion,
    )


def format_validation_for_llm(result: ValidationResult) -> str:
    """Format validation result as a message the LLM can understand and act on."""
    if result.success:
        warn_count = len(result.warnings)
        if warn_count > 0:
            return f"Validation PASSED with {warn_count} warnings:\n" + \
                "\n".join(f"  - {w}" for w in result.warnings[:5])
        return "Validation PASSED — zero errors, zero warnings."

    lines = [f"Validation FAILED — {len(result.errors)} error(s):"]
    for e in result.errors[:10]:
        lines.append(f"  {e}")
    if result.suggestion:
        lines.append(f"\nSuggested fix: {result.suggestion}")
    return "\n".join(lines)

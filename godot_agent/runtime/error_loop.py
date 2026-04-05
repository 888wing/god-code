"""Automated error detection and fix loop for Godot projects.

Runs godot --headless, parses errors, and provides structured
error reports that the conversation engine can act on.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.project import parse_project_godot

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


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
    smoke_checked_scenes: list[str] = field(default_factory=list)


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
        line = _ANSI_ESCAPE_RE.sub("", line).strip()
        if not line:
            continue
        # Match: ERROR: res://path:line - message
        # or:    ERROR: message [Resource file res://path:line]
        m = re.match(r'(?:\[.*?\])?\s*((?:SCRIPT )?ERROR|WARNING):\s*(.*)', line)
        if not m:
            continue
        level = "ERROR" if "ERROR" in m.group(1) else "WARNING"
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

        qm = re.match(r'(.*?)"?(res://[^":\]\s]+)"?(?::(\d+))?(.*)', rest)
        if qm:
            message = " ".join(part.strip() for part in (qm.group(1), qm.group(4)) if part.strip()) or rest.strip()
            errors.append(GodotError(
                level=level,
                file=qm.group(2),
                line=int(qm.group(3)) if qm.group(3) else None,
                message=message,
                category=_categorize_error(message, qm.group(2)),
            ))
            continue

        # Generic error without file reference
        if level == "ERROR":
            errors.append(GodotError(
                level=level, file="", line=None,
                message=rest.strip(), category="unknown",
            ))

    return errors


def _build_scene_smoke_script(scene_path: str, settle_delay_ms: int = 800) -> str:
    delay_sec = settle_delay_ms / 1000.0
    return f"""extends SceneTree

func _init():
\tcall_deferred("_run")

func _run() -> void:
\tvar packed_scene = load("{scene_path}")
\tif packed_scene == null:
\t\tpush_error("Failed loading smoke scene {scene_path}")
\t\tquit(1)
\t\treturn
\tvar scene = packed_scene.instantiate()
\tif scene == null:
\t\tpush_error("Failed instantiating smoke scene {scene_path}")
\t\tquit(2)
\t\treturn
\troot.add_child(scene)
\tawait process_frame
\tawait process_frame
\tif {delay_sec} > 0.0:
\t\tawait create_timer({delay_sec}).timeout
\tquit()
"""


async def _run_scene_smoke_check(
    project_path: Path,
    scene_path: str,
    *,
    godot_path: str,
    timeout: int,
    settle_delay_ms: int,
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "scene_smoke.gd"
        script_path.write_text(
            _build_scene_smoke_script(scene_path, settle_delay_ms=settle_delay_ms),
            encoding="utf-8",
        )
        proc = await asyncio.create_subprocess_exec(
            godot_path,
            "--headless",
            "-s",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_path),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    raw = stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")
    return proc.returncode or 0, raw


async def validate_project(
    project_path: str,
    godot_path: str = "godot",
    timeout: int = 30,
    smoke_main_scene: bool = True,
    smoke_scene_paths: list[str] | None = None,
    smoke_delay_ms: int = 800,
) -> ValidationResult:
    """Run Godot validation and optionally smoke-load key scenes."""
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
    smoke_checked_scenes: list[str] = []

    root = Path(project_path)
    smoke_targets = [scene for scene in (smoke_scene_paths or []) if scene]
    if smoke_main_scene and not smoke_targets:
        project_file = root / "project.godot"
        if project_file.exists():
            main_scene = parse_project_godot(project_file).main_scene
            if main_scene:
                smoke_targets.append(main_scene)

    if not errors:
        for scene_path in smoke_targets:
            smoke_checked_scenes.append(scene_path)
            try:
                exit_code, smoke_raw = await _run_scene_smoke_check(
                    root,
                    scene_path,
                    godot_path=godot_path,
                    timeout=timeout,
                    settle_delay_ms=smoke_delay_ms,
                )
            except asyncio.TimeoutError:
                errors.append(
                    GodotError(
                        level="ERROR",
                        file=scene_path,
                        line=None,
                        message=f"Scene smoke check timed out after {timeout}s.",
                        category="scene",
                    )
                )
                continue

            raw = f"{raw}\n# scene_smoke {scene_path}\n{smoke_raw}".strip()
            smoke_parsed = parse_godot_output(smoke_raw)
            scene_errors = [error for error in smoke_parsed if error.level == "ERROR"]
            scene_warnings = [warning for warning in smoke_parsed if warning.level == "WARNING"]
            errors.extend(scene_errors)
            warnings.extend(scene_warnings)
            if exit_code != 0 and not any(
                error.file == scene_path or scene_path in error.message for error in scene_errors
            ):
                errors.append(
                    GodotError(
                        level="ERROR",
                        file=scene_path,
                        line=None,
                        message=f"Scene smoke check failed with exit code {exit_code}.",
                        category="scene",
                    )
                )

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
        smoke_checked_scenes=smoke_checked_scenes,
    )


def format_validation_for_llm(result: ValidationResult) -> str:
    """Format validation result as a message the LLM can understand and act on."""
    if result.success:
        warn_count = len(result.warnings)
        smoke_suffix = (
            f" Scene smoke checked: {', '.join(result.smoke_checked_scenes)}."
            if result.smoke_checked_scenes
            else ""
        )
        if warn_count > 0:
            return f"Validation PASSED with {warn_count} warnings.{smoke_suffix}\n" + \
                "\n".join(f"  - {w}" for w in result.warnings[:5])
        return f"Validation PASSED — zero errors, zero warnings.{smoke_suffix}"

    lines = [f"Validation FAILED — {len(result.errors)} error(s):"]
    if result.smoke_checked_scenes:
        lines.append(f"Scene smoke checked: {', '.join(result.smoke_checked_scenes)}")
    for e in result.errors[:10]:
        lines.append(f"  {e}")
    if result.suggestion:
        lines.append(f"\nSuggested fix: {result.suggestion}")
    return "\n".join(lines)

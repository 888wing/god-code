from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.runtime.config import default_config_path, load_config
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_ISSUE_RE = re.compile(
    r"(ERROR|WARNING):\s*(res://[^:\s]+)(?::(\d+))?\s*-?\s*(.*)"
)


@dataclass
class GodotIssue:
    """A single error or warning parsed from Godot CLI output."""

    level: str
    file: str
    line: int | None
    message: str


@dataclass
class GodotOutputReport:
    """Structured report of parsed Godot engine output."""

    errors: list[GodotIssue] = field(default_factory=list)
    warnings: list[GodotIssue] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class GodotCommandResult:
    stdout: str
    stderr: str
    exit_code: int
    report: GodotOutputReport

    @property
    def raw_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


def parse_godot_output(output: str) -> GodotOutputReport:
    """Parse raw Godot CLI output into a structured report of errors and warnings."""
    report = GodotOutputReport(raw_output=output)
    for line in output.splitlines():
        line = _ANSI_ESCAPE_RE.sub("", line).strip()
        if not line:
            continue
        m = _ISSUE_RE.match(line)
        if m:
            issue = GodotIssue(
                level=m.group(1),
                file=m.group(2),
                line=int(m.group(3)) if m.group(3) else None,
                message=m.group(4).strip(),
            )
            if issue.level == "ERROR":
                report.errors.append(issue)
            else:
                report.warnings.append(issue)
    return report


def build_gut_command(
    godot_path: str = "godot", test_script: str | None = None
) -> list[str]:
    """Build the command-line arguments to run GUT tests in headless mode."""
    cmd = [godot_path, "--headless", "-s", "addons/gut/gut_cmdln.gd", "-gexit"]
    if test_script:
        cmd.append("-gtest=" + test_script)
    return cmd


def build_import_command(godot_path: str = "godot") -> list[str]:
    """Build the command-line arguments to import project resources and quit."""
    return [godot_path, "--import", "--quit"]


def resolve_godot_path(godot_path: str | None = None) -> str:
    candidate = (godot_path or "").strip()
    if candidate and candidate != "godot":
        return candidate
    try:
        config = load_config(default_config_path())
        configured = str(config.godot_path or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return candidate or "godot"


def build_screenshot_script(
    scene_path: str, output_path: str, delay_ms: int = 1000
) -> str:
    """Generate a GDScript that loads a scene, waits, and saves a screenshot."""
    delay_sec = delay_ms / 1000.0
    return f"""extends SceneTree

func _init():
\tcall_deferred("_capture")

func _capture() -> void:
\tvar packed_scene = load("{scene_path}")
\tif packed_scene == null:
\t\tpush_error("Failed to load scene: {scene_path}")
\t\tquit(1)
\t\treturn
\tvar scene = packed_scene.instantiate()
\troot.add_child(scene)
\tawait process_frame
\tawait process_frame
\tif {delay_sec} > 0.0:
\t\tawait create_timer({delay_sec}).timeout
\tvar texture = root.get_viewport().get_texture()
\tif texture == null:
\t\tpush_error("Viewport texture is unavailable. Disable headless mode for screenshot capture on this platform.")
\t\tquit(2)
\t\treturn
\tvar img = texture.get_image()
\tvar save_result = img.save_png("{output_path}")
\tif save_result != OK:
\t\tpush_error("Failed to save screenshot: {output_path}")
\t\tquit(save_result)
\t\treturn
\tquit()
"""


async def run_godot_command(
    cmd: list[str],
    *,
    project_path: str | Path,
    timeout: int = 120,
) -> GodotCommandResult:
    # v1.0.1/D2: register with the active subprocess registry so the
    # engine can SIGTERM this process on Ctrl+C instead of letting it run
    # to natural completion (30-120s for typical Godot validate calls).
    from godot_agent.runtime.engine import get_current_subprocess_registry
    registry = get_current_subprocess_registry()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_path),
    )
    if registry is not None:
        registry.register_subprocess(proc)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    finally:
        if registry is not None:
            registry.unregister_subprocess(proc)
    stdout_str = stdout.decode(errors="replace")
    stderr_str = stderr.decode(errors="replace")
    report = parse_godot_output(stdout_str + "\n" + stderr_str)
    return GodotCommandResult(
        stdout=stdout_str,
        stderr=stderr_str,
        exit_code=proc.returncode or 0,
        report=report,
    )


async def run_godot_import(
    project_path: str | Path,
    *,
    godot_path: str = "godot",
    timeout: int = 120,
) -> GodotCommandResult:
    """Run Godot's resource import pass for a project."""
    return await run_godot_command(
        build_import_command(resolve_godot_path(godot_path)),
        project_path=project_path,
        timeout=timeout,
    )


class RunGodotTool(BaseTool):
    """Run a Godot command in headless mode and return parsed output."""

    name = "run_godot"
    description = "Run a Godot command in headless mode and return parsed output."

    class Input(BaseModel):
        command: str = Field(description="Type: 'gut', 'validate', 'import'")
        godot_path: str = Field(default="godot")
        scene_path: str = Field(default="")
        test_script: str = Field(default="")
        output_path: str = Field(default="/tmp/godot_screenshot.png")
        project_path: str = Field(default=".")

    class Output(BaseModel):
        stdout: str
        stderr: str
        exit_code: int
        errors: list[dict] = []
        warnings: list[dict] = []

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        try:
            resolved_godot_path = resolve_godot_path(input.godot_path)
            if input.command == "gut":
                cmd = build_gut_command(
                    resolved_godot_path, input.test_script or None
                )
            elif input.command == "validate":
                cmd = [resolved_godot_path, "--headless", "--quit"]
            elif input.command == "import":
                cmd = build_import_command(resolved_godot_path)
            else:
                return ToolResult(error=f"Unknown command type: {input.command}")

            project_path, err = _validate_path(input.project_path)
            if err:
                return ToolResult(error=err)

            result = await run_godot_command(cmd, project_path=project_path, timeout=120)

            return ToolResult(
                output=self.Output(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    errors=[
                        {
                            "file": e.file,
                            "line": e.line,
                            "message": e.message,
                        }
                        for e in result.report.errors
                    ],
                    warnings=[
                        {
                            "file": w.file,
                            "line": w.line,
                            "message": w.message,
                        }
                        for w in result.report.warnings
                    ],
                )
            )
        except asyncio.TimeoutError:
            return ToolResult(error="Godot process timed out after 120s")
        except Exception as e:
            return ToolResult(error=str(e))

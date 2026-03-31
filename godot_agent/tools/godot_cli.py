from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult

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


def parse_godot_output(output: str) -> GodotOutputReport:
    """Parse raw Godot CLI output into a structured report of errors and warnings."""
    report = GodotOutputReport(raw_output=output)
    for line in output.splitlines():
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


def build_screenshot_script(
    scene_path: str, output_path: str, delay_ms: int = 1000
) -> str:
    """Generate a GDScript that loads a scene, waits, and saves a screenshot."""
    delay_sec = delay_ms / 1000.0
    return f"""extends SceneTree

func _init():
\tvar scene = load("{scene_path}").instantiate()
\troot.add_child(scene)
\tawait create_timer({delay_sec}).timeout
\tvar img = root.get_viewport().get_texture().get_image()
\timg.save_png("{output_path}")
\tquit()
"""


class RunGodotTool(BaseTool):
    """Run a Godot command in headless mode and return parsed output."""

    name = "run_godot"
    description = "Run a Godot command in headless mode and return parsed output."

    class Input(BaseModel):
        command: str = Field(description="Type: 'gut', 'validate'")
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

    async def execute(self, input: Input) -> ToolResult:
        try:
            if input.command == "gut":
                cmd = build_gut_command(
                    input.godot_path, input.test_script or None
                )
            elif input.command == "validate":
                cmd = [input.godot_path, "--headless", "--quit"]
            else:
                return ToolResult(error=f"Unknown command type: {input.command}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=input.project_path,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120
            )
            stdout_str = stdout.decode(errors="replace")
            stderr_str = stderr.decode(errors="replace")
            report = parse_godot_output(stdout_str + "\n" + stderr_str)

            return ToolResult(
                output=self.Output(
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=proc.returncode or 0,
                    errors=[
                        {
                            "file": e.file,
                            "line": e.line,
                            "message": e.message,
                        }
                        for e in report.errors
                    ],
                    warnings=[
                        {
                            "file": w.file,
                            "line": w.line,
                            "message": w.message,
                        }
                        for w in report.warnings
                    ],
                )
            )
        except asyncio.TimeoutError:
            return ToolResult(error="Godot process timed out after 120s")
        except Exception as e:
            return ToolResult(error=str(e))

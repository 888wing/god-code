from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.runtime.visual_regression import build_artifact_path, slugify_artifact_name
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path
from godot_agent.tools.godot_cli import build_screenshot_script, resolve_godot_path
from godot_agent.llm.vision import encode_image


class ScreenshotTool(BaseTool):
    """Take a screenshot of a Godot scene using a temporary Godot runner."""

    name = "screenshot_scene"
    description = (
        "Take a screenshot of a Godot scene using a temporary Godot runner. "
        "Defaults to windowed rendering on desktop platforms for reliable viewport capture. "
        "Returns base64 image."
    )

    class Input(BaseModel):
        scene_path: str = Field(description="res:// path to the scene")
        godot_path: str = Field(default="godot")
        project_path: str = Field(default=".")
        output_path: str = Field(default="", description="Optional absolute output path for the screenshot PNG")
        artifact_name: str = Field(default="", description="Artifact name used when output_path is omitted")
        headless: bool = Field(
            default=False,
            description="Run Godot in headless mode. Disable when you need real viewport capture on desktop platforms.",
        )
        include_base64: bool = Field(
            default=True,
            description="Include base64 image data in the response. Disable for MCP or large screenshots to reduce payload size.",
        )
        delay_ms: int = Field(
            default=1000, description="Wait time before capture (ms)"
        )

    class Output(BaseModel):
        image_path: str
        image_base64: str = ""

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        try:
            project_path, err = _validate_path(input.project_path)
            if err:
                return ToolResult(error=err)
            resolved_godot_path = resolve_godot_path(input.godot_path)
            with tempfile.TemporaryDirectory() as tmpdir:
                if input.output_path:
                    screenshot_file, out_err = _validate_path(input.output_path)
                    if out_err:
                        return ToolResult(error=out_err)
                else:
                    artifact_name = input.artifact_name or slugify_artifact_name(Path(input.scene_path).stem or "scene")
                    screenshot_file = build_artifact_path(
                        project_path,
                        category="screenshots",
                        name=artifact_name,
                    )
                screenshot_file.parent.mkdir(parents=True, exist_ok=True)
                script_path = str(Path(tmpdir) / "capture.gd")

                script = build_screenshot_script(
                    input.scene_path, str(screenshot_file), input.delay_ms
                )
                Path(script_path).write_text(script)

                proc = await asyncio.create_subprocess_exec(
                    resolved_godot_path,
                    *(["--headless"] if input.headless else []),
                    "-s",
                    script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(project_path),
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=30
                )
                if proc.returncode not in (0, None):
                    stderr_text = stderr.decode(errors="replace").strip()
                    stdout_text = stdout.decode(errors="replace").strip()
                    details = stderr_text or stdout_text or "unknown error"
                    return ToolResult(
                        error=(
                            "Screenshot capture failed with exit code "
                            f"{proc.returncode}: {details}"
                        )
                    )

                if not screenshot_file.exists():
                    return ToolResult(
                        error="Screenshot was not created. "
                        "Scene may have failed to load."
                    )

                b64 = encode_image(str(screenshot_file)) if input.include_base64 else ""
                return ToolResult(
                    output=self.Output(
                        image_path=str(screenshot_file), image_base64=b64
                    )
                )
        except asyncio.TimeoutError:
            return ToolResult(error="Screenshot timed out after 30s")
        except Exception as e:
            return ToolResult(error=str(e))

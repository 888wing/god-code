from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.godot_cli import build_screenshot_script
from godot_agent.llm.vision import encode_image


class ScreenshotTool(BaseTool):
    """Take a screenshot of a Godot scene using headless rendering."""

    name = "screenshot_scene"
    description = (
        "Take a screenshot of a Godot scene using headless rendering. "
        "Returns base64 image."
    )

    class Input(BaseModel):
        scene_path: str = Field(description="res:// path to the scene")
        godot_path: str = Field(default="godot")
        project_path: str = Field(default=".")
        delay_ms: int = Field(
            default=1000, description="Wait time before capture (ms)"
        )

    class Output(BaseModel):
        image_path: str
        image_base64: str

    async def execute(self, input: Input) -> ToolResult:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                screenshot_path = str(Path(tmpdir) / "screenshot.png")
                script_path = str(Path(tmpdir) / "capture.gd")

                script = build_screenshot_script(
                    input.scene_path, screenshot_path, input.delay_ms
                )
                Path(script_path).write_text(script)

                proc = await asyncio.create_subprocess_exec(
                    input.godot_path,
                    "--headless",
                    "-s",
                    script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=input.project_path,
                )
                await asyncio.wait_for(proc.communicate(), timeout=30)

                if not Path(screenshot_path).exists():
                    return ToolResult(
                        error="Screenshot was not created. "
                        "Scene may have failed to load."
                    )

                b64 = encode_image(screenshot_path)
                return ToolResult(
                    output=self.Output(
                        image_path=screenshot_path, image_base64=b64
                    )
                )
        except asyncio.TimeoutError:
            return ToolResult(error="Screenshot timed out after 30s")
        except Exception as e:
            return ToolResult(error=str(e))

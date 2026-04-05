"""Vision-driven screenshot analysis tool for Godot game UI/visuals."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.llm.vision import encode_image
from godot_agent.prompts.vision_templates import build_analysis_prompt
from godot_agent.tools.base import BaseTool, ToolResult


class AnalyzeScreenshotTool(BaseTool):
    """Analyze a Godot game screenshot using an LLM vision model.

    Reads the screenshot, encodes it as base64, builds an analysis prompt
    (optionally focused on a specific area like ``"ui"`` or ``"gameplay"``),
    and returns the model's structured analysis including suggestions and a
    quality score.
    """

    name = "analyze_screenshot"
    description = (
        "Analyze a Godot game screenshot for visual quality, layout issues, "
        "and UI improvements. Returns structured analysis with actionable suggestions."
    )

    class Input(BaseModel):
        screenshot_path: str = Field(
            description="Absolute path to the screenshot PNG file"
        )
        project_path: str = Field(
            description="Absolute path to the Godot project root"
        )
        focus: str = Field(
            default="general",
            description=(
                'Analysis focus area: "general", "ui", or "gameplay". '
                "Controls which additional rubric sections are included in the prompt."
            ),
        )

    def is_read_only(self) -> bool:
        # The tool produces analysis output but does not modify any files.
        return False

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        # Validate screenshot exists
        screenshot = Path(input.screenshot_path)
        if not screenshot.exists():
            return ToolResult(
                error=f"Screenshot not found: {input.screenshot_path}"
            )

        try:
            # Encode image to base64
            image_b64 = encode_image(screenshot)

            # Build focus-aware analysis prompt
            prompt = build_analysis_prompt(input.focus)

            # Call the vision model (mockable seam)
            response = await self._call_vision_model(prompt, image_b64)

            return ToolResult(output=response)

        except Exception as exc:
            return ToolResult(error=str(exc))

    async def _call_vision_model(self, prompt: str, image_b64: str) -> str:
        """Send the screenshot to a vision-capable LLM and return the response.

        This method is the integration seam: tests mock it, and real
        callers can subclass or monkey-patch to route through their
        preferred backend (OpenAI, Gemini, local model, etc.).
        """
        raise NotImplementedError(
            "AnalyzeScreenshotTool._call_vision_model must be provided by the "
            "runtime (e.g. via execution_context.client or a backend adapter)."
        )

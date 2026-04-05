"""Vision-driven screenshot scoring tool for Godot game visual quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from godot_agent.llm.vision import encode_image
from godot_agent.prompts.vision_templates import build_scoring_prompt
from godot_agent.tools.base import BaseTool, ToolResult


class ScoreScreenshotTool(BaseTool):
    """Score a Godot game screenshot on multiple quality dimensions.

    Reads the screenshot (and optionally a *before* image for comparison),
    encodes them as base64, builds a scoring prompt with the requested
    criteria rubric, and returns the model's structured JSON scores
    including per-dimension ratings, an overall score, and (when a
    before image is provided) an ``improved`` flag.
    """

    name = "score_screenshot"
    description = (
        "Score a Godot game screenshot on multiple visual quality dimensions "
        "(1-5 scale). Optionally compare against a before image to determine "
        "if quality improved. Returns structured JSON with dimension scores, "
        "overall score, and improvement flag."
    )

    class Input(BaseModel):
        screenshot_path: str = Field(
            description="Absolute path to the screenshot PNG file to score"
        )
        project_path: str = Field(
            description="Absolute path to the Godot project root"
        )
        before_path: Optional[str] = Field(
            default=None,
            description=(
                "Optional absolute path to a previous screenshot for "
                "before/after comparison. When provided, the response "
                "will include an 'improved' boolean flag."
            ),
        )
        criteria: str = Field(
            default="demo_quality",
            description=(
                'Scoring criteria rubric: "demo_quality", "visual_polish", '
                "or any custom key. Controls which dimensions are evaluated."
            ),
        )

    def is_read_only(self) -> bool:
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

        # Validate before image if provided
        if input.before_path is not None:
            before = Path(input.before_path)
            if not before.exists():
                return ToolResult(
                    error=f"Before screenshot not found: {input.before_path}"
                )

        try:
            # Build the list of images (before + after, or just the single shot)
            if input.before_path is not None:
                images = [
                    encode_image(Path(input.before_path)),
                    encode_image(screenshot),
                ]
            else:
                images = [encode_image(screenshot)]

            # Build criteria-aware scoring prompt
            prompt = build_scoring_prompt(input.criteria)

            if input.before_path is not None:
                prompt += (
                    "\n\nYou are provided two images: the BEFORE screenshot "
                    "(first) and the AFTER screenshot (second). Score the AFTER "
                    "image, and include an \"improved\": true/false field "
                    "indicating whether the AFTER is better overall than the BEFORE."
                )

            # Call the vision model (mockable seam)
            response = await self._call_vision_model(prompt, images)

            # Try to parse as JSON to validate structure; return raw if unparseable
            try:
                parsed = json.loads(response)
                return ToolResult(output=json.dumps(parsed))
            except (json.JSONDecodeError, TypeError):
                # Return raw text so the caller can still use the response
                return ToolResult(output=response)

        except Exception as exc:
            return ToolResult(error=str(exc))

    async def _call_vision_model(
        self, prompt: str, images: list[str]
    ) -> str:
        """Send screenshot(s) to a vision-capable LLM and return the response.

        This method is the integration seam: tests mock it, and real
        callers can subclass or monkey-patch to route through their
        preferred backend (OpenAI, Gemini, local model, etc.).

        Parameters
        ----------
        prompt:
            The scoring prompt including the criteria rubric.
        images:
            List of base64-encoded images. Single item for standalone
            scoring, two items for before/after comparison.
        """
        raise NotImplementedError(
            "ScoreScreenshotTool._call_vision_model must be provided by the "
            "runtime (e.g. via execution_context.client or a backend adapter)."
        )

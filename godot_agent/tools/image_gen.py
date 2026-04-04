"""AI image generation tool with pixel art post-processing pipeline.

LLM decides what to generate (subject, size, style).
Pipeline enforces quality: chroma key, crop, resize, hard edges.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from godot_agent.prompts.image_templates import build_image_prompt
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.sprite_pipeline import post_process_sprite

log = logging.getLogger(__name__)


class GenerateSpriteTool(BaseTool):
    name = "generate_sprite"
    description = (
        "Generate a pixel art sprite using AI image generation. "
        "Automatically handles green screen removal, cropping, and resizing to exact pixel dimensions. "
        "Use for: character sprites, enemies, items, icons, projectiles, UI elements."
    )

    class Input(BaseModel):
        subject: str = Field(description="What to draw (e.g., 'fire mage casting spell', 'health potion', 'slime enemy')")
        size: int = Field(default=32, description="Target size in pixels (8, 16, 24, 32, 48, 64, 128)")
        style: str = Field(default="pixel_modern", description="Style preset: pixel_8bit, pixel_16bit, pixel_modern, chibi, minimal")
        facing: str = Field(default="front", description="Direction: front, left, right, back")
        category: str = Field(default="character", description="Type: character, enemy, boss, item, projectile, ui_icon, background, effect, npc")
        output_path: str = Field(description="Where to save (e.g., assets/sprites/player.png)")
        extra: str = Field(default="", description="Additional prompt instructions")

    class Output(BaseModel):
        path: str
        width: int
        height: int
        prompt_used: str

    async def execute(self, input: Input) -> ToolResult:
        try:
            # Build prompt
            prompt = build_image_prompt(
                subject=input.subject,
                size=input.size,
                style=input.style,
                facing=input.facing,
                category=input.category,
                extra=input.extra,
            )
            log.info("Image prompt: %s", prompt[:100])

            # Call OpenAI image generation API
            from godot_agent.tools.file_ops import _project_root
            api_key = ""
            # Read API key from config
            config_path = Path.home() / ".config" / "god-code" / "config.json"
            if config_path.exists():
                import json
                cfg = json.loads(config_path.read_text())
                api_key = cfg.get("api_key", "")

            if not api_key:
                return ToolResult(error="No API key configured for image generation")

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-image-1",
                        "prompt": prompt,
                        "n": 1,
                        "size": "1024x1024",
                        "quality": "low",
                    },
                )

            if resp.status_code != 200:
                error_msg = resp.text[:200]
                return ToolResult(error=f"Image API error ({resp.status_code}): {error_msg}")

            data = resp.json()

            # Get image data
            image_data = data["data"][0]
            if "b64_json" in image_data:
                import base64
                raw_bytes = base64.b64decode(image_data["b64_json"])
            elif "url" in image_data:
                async with httpx.AsyncClient(timeout=30.0) as dl_client:
                    img_resp = await dl_client.get(image_data["url"])
                    raw_bytes = img_resp.content
            else:
                return ToolResult(error="No image data in API response")

            # Post-process
            processed = post_process_sprite(raw_bytes, target_size=input.size)

            # Save
            output = Path(input.output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            processed.save(str(output), "PNG")

            return ToolResult(output=self.Output(
                path=str(output),
                width=processed.width,
                height=processed.height,
                prompt_used=prompt[:200],
            ))

        except Exception as e:
            return ToolResult(error=f"Image generation failed: {e}")

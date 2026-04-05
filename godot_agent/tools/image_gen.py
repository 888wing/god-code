"""AI image generation tool with pixel art post-processing pipeline.

LLM decides what to generate (subject, size, style).
Pipeline enforces quality: chroma key, crop, resize, hard edges.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from godot_agent.prompts.image_templates import build_image_prompt
from godot_agent.runtime.design_memory import AssetSpec, load_design_memory
from godot_agent.runtime.visual_regression import build_artifact_path, compare_image_files, resolve_baseline_path, write_failure_bundle
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.godot_cli import run_godot_import
from godot_agent.tools.screenshot import ScreenshotTool
from godot_agent.tools.sprite_pipeline import parse_hex_color, post_process_sprite
from godot_agent.tools.sprite_qa import qa_sprite_file

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
        godot_path: str = Field(default="godot", description="Path to the Godot executable used for reimport")
        reimport_assets: bool = Field(default=True, description="Run Godot --import after writing the generated sprite into a project")
        smoke_scene_path: str = Field(default="", description="Optional scene path to screenshot after reimport for asset visibility smoke checks")
        smoke_baseline_id: str = Field(default="", description="Optional baseline id used by the smoke screenshot")
        smoke_tolerance: int = Field(default=0, description="Tolerance for smoke baseline comparison")
        create_baseline: bool = Field(default=False, description="Create the smoke baseline from the captured image if missing")

    class Output(BaseModel):
        path: str
        width: int
        height: int
        prompt_used: str
        qa_report_path: str = ""
        qa_warnings: list[str] = Field(default_factory=list)
        reimported: bool = False
        import_warnings: list[str] = Field(default_factory=list)
        smoke_capture_path: str = ""
        baseline_matched: bool | None = None
        failure_bundle: str = ""

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

            # Call image generation API via LLM client or direct fallback
            api_key = ""
            base_url = "https://api.openai.com/v1"
            ctx = getattr(self, "_execution_context", None)
            llm_client = getattr(ctx, "llm_client", None) if ctx else None
            if llm_client:
                api_key = llm_client.config.api_key
                base_url = llm_client.config.base_url or base_url
            if not api_key:
                config_path = Path.home() / ".config" / "god-code" / "config.json"
                if config_path.exists():
                    import json
                    cfg = json.loads(config_path.read_text())
                    api_key = cfg.get("api_key", "")

            if not api_key:
                return ToolResult(error="No API key configured for image generation")

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url}/images/generations",
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
                raw_bytes = base64.b64decode(image_data["b64_json"])
            elif "url" in image_data:
                async with httpx.AsyncClient(timeout=30.0) as dl_client:
                    img_resp = await dl_client.get(image_data["url"])
                    raw_bytes = img_resp.content
            else:
                return ToolResult(error="No image data in API response")

            project_root = Path(_project_root) if _project_root else None
            memory = load_design_memory(project_root) if project_root else None
            asset_spec = memory.asset_spec if memory and not memory.asset_spec.is_empty else AssetSpec(
                style="pixel_art",
                target_size=[input.size, input.size],
                background_key="#00FF00",
                alpha_required=True,
                palette_mode="restricted",
                import_filter="nearest",
                allow_resize=False,
            )
            target_size = asset_spec.target_size[0] if asset_spec.target_size else input.size

            # Post-process
            processed = post_process_sprite(
                raw_bytes,
                target_size=target_size,
                chroma_key=parse_hex_color(asset_spec.background_key) if asset_spec.background_key else (0, 255, 0),
            )

            # Save
            output = Path(input.output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            processed.save(str(output), "PNG")

            qa_report_path = ""
            qa_warnings: list[str] = []
            reimported = False
            import_warnings: list[str] = []
            smoke_capture_path = ""
            baseline_matched: bool | None = None
            failure_bundle = ""
            if project_root:
                original_path = build_artifact_path(project_root, category="sprite-source", name=output.stem)
                original_path.parent.mkdir(parents=True, exist_ok=True)
                original_path.write_bytes(raw_bytes)
                qa_report = qa_sprite_file(
                    project_root=project_root,
                    image_path=output,
                    spec=asset_spec,
                    original_path=original_path,
                    artifact_name=output.stem,
                )
                qa_report_path = qa_report.artifacts.get("qa", "")
                qa_warnings = list(qa_report.warnings)
                if not qa_report.valid:
                    issues = "; ".join(qa_report.issues)
                    return ToolResult(error=f"Generated sprite failed QA: {issues} (report: {qa_report_path})")
                if input.reimport_assets:
                    import_result = await run_godot_import(project_root, godot_path=input.godot_path)
                    reimported = True
                    import_warnings = [warning.message for warning in import_result.report.warnings]
                    if import_result.exit_code != 0 or import_result.report.errors:
                        messages = "; ".join(error.message for error in import_result.report.errors) or import_result.raw_output or "unknown Godot import error"
                        return ToolResult(error=f"Generated sprite passed QA but Godot import failed: {messages}")
                if input.smoke_scene_path:
                    screenshot_tool = ScreenshotTool()
                    smoke_output = build_artifact_path(project_root, category="screenshots", name=f"generated-{output.stem}-smoke")
                    shot = await screenshot_tool.execute(
                        screenshot_tool.Input(
                            scene_path=input.smoke_scene_path,
                            godot_path=input.godot_path,
                            project_path=str(project_root),
                            output_path=str(smoke_output),
                            artifact_name=f"generated-{output.stem}-smoke",
                            delay_ms=1000,
                        )
                    )
                    if shot.error:
                        return ToolResult(error=f"Generated sprite passed QA but smoke capture failed: {shot.error}")
                    smoke_capture_path = shot.output.image_path
                    if input.smoke_baseline_id:
                        comparison = compare_image_files(
                            project_root=project_root,
                            actual_path=Path(smoke_capture_path),
                            baseline_path=resolve_baseline_path(project_root, input.smoke_baseline_id),
                            tolerance=input.smoke_tolerance,
                            create_baseline=input.create_baseline,
                            diff_path=build_artifact_path(project_root, category="diffs", name=input.smoke_baseline_id.replace("/", "-")),
                        )
                        baseline_matched = comparison.matched
                        if not comparison.matched:
                            failure_bundle = str(
                                write_failure_bundle(
                                    project_root,
                                    test_id=f"generated-{output.stem}-smoke",
                                    payload={
                                        "test_id": input.smoke_baseline_id,
                                        "scene": input.smoke_scene_path,
                                        "step": "generated sprite smoke validation",
                                        "reason": comparison.reason or "visual_diff_exceeded",
                                        "artifacts": {
                                            "actual": comparison.actual_path,
                                            "expected": comparison.baseline_path,
                                            "diff": comparison.diff_path,
                                        },
                                        "image_assert": comparison.to_dict(),
                                    },
                                )
                            )
                            return ToolResult(
                                error=(
                                    f"Generated sprite passed pixel QA but smoke baseline failed: "
                                    f"{comparison.reason or 'visual_diff'} (bundle: {failure_bundle})"
                                )
                            )

            return ToolResult(output=self.Output(
                path=str(output),
                width=processed.width,
                height=processed.height,
                prompt_used=prompt[:200],
                qa_report_path=qa_report_path,
                qa_warnings=qa_warnings,
                reimported=reimported,
                import_warnings=import_warnings,
                smoke_capture_path=smoke_capture_path,
                baseline_matched=baseline_matched,
                failure_bundle=failure_bundle,
            ))

        except Exception as e:
            return ToolResult(error=f"Image generation failed: {e}")

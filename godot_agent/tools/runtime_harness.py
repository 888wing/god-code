"""Runtime harness tools for deterministic UI/gameplay test loops."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from godot_agent.llm.vision import encode_image
from godot_agent.runtime.runtime_bridge import (
    RuntimeSnapshot,
    add_runtime_screenshot,
    advance_runtime_ticks,
    get_runtime_snapshot,
    load_runtime_scene,
    press_runtime_action,
    record_runtime_event,
    reset_runtime_harness,
    runtime_events_since,
    runtime_snapshot_dict,
    runtime_state_dict,
    set_runtime_fixture,
    update_runtime_snapshot,
    update_runtime_state,
)
from godot_agent.runtime.visual_regression import (
    build_artifact_path,
    compare_image_files,
    copy_to_artifact,
    resolve_baseline_path,
    write_failure_bundle,
)
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path
from godot_agent.tools.godot_cli import run_godot_import
from godot_agent.tools.screenshot import ScreenshotTool


class _SafeRuntimeTool(BaseTool):
    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False


class LoadSceneTool(_SafeRuntimeTool):
    name = "load_scene"
    description = "Load or reset the runtime harness to a specific scene path."

    class Input(BaseModel):
        scene_path: str = Field(description="res:// path to the scene to make active")

    class Output(BaseModel):
        active_scene: str
        current_tick: int

    async def execute(self, input: Input) -> ToolResult:
        snapshot = load_runtime_scene(input.scene_path)
        return ToolResult(output=self.Output(active_scene=snapshot.active_scene, current_tick=snapshot.current_tick))


class SetFixtureTool(_SafeRuntimeTool):
    name = "set_fixture"
    description = "Store deterministic test fixture data in the runtime harness."

    class Input(BaseModel):
        name: str = Field(description="Fixture name, for example inventory or enemy_wave")
        payload: dict[str, Any] = Field(default_factory=dict, description="Fixture payload to attach to the harness")

    class Output(BaseModel):
        fixture_names: list[str]

    async def execute(self, input: Input) -> ToolResult:
        snapshot = set_runtime_fixture(input.name, input.payload)
        return ToolResult(output=self.Output(fixture_names=sorted(snapshot.fixtures.keys())))


class PressActionTool(_SafeRuntimeTool):
    name = "press_action"
    description = "Record a gameplay or UI input action in the runtime harness."

    class Input(BaseModel):
        action: str = Field(description="Input action name, for example ui_accept or fire")
        pressed: bool = Field(default=True, description="True to press/hold, false to release")

    class Output(BaseModel):
        active_inputs: list[str]
        recent_inputs: list[str]

    async def execute(self, input: Input) -> ToolResult:
        snapshot = press_runtime_action(input.action, pressed=input.pressed)
        return ToolResult(output=self.Output(active_inputs=snapshot.active_inputs, recent_inputs=snapshot.input_actions[-10:]))


class AdvanceTicksTool(_SafeRuntimeTool):
    name = "advance_ticks"
    description = "Advance the runtime harness by a fixed number of physics ticks and optionally inject state/events."

    class Input(BaseModel):
        count: int = Field(default=1, description="Number of physics ticks to advance")
        state_updates: dict[str, Any] = Field(default_factory=dict, description="Optional state keys to merge after advancing")
        events: list[dict[str, Any]] = Field(default_factory=list, description="Optional events to append at the resulting tick")

    class Output(BaseModel):
        current_tick: int
        state: dict[str, Any]
        events: list[dict[str, Any]]

    async def execute(self, input: Input) -> ToolResult:
        snapshot = advance_runtime_ticks(input.count, state_updates=input.state_updates, events=input.events)
        return ToolResult(
            output=self.Output(
                current_tick=snapshot.current_tick,
                state=dict(snapshot.state),
                events=[event.__dict__ for event in snapshot.events[-10:]],
            )
        )


class GetRuntimeStateTool(_SafeRuntimeTool):
    name = "get_runtime_state"
    description = "Read the current runtime harness state, fixtures, active inputs, and tick."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")

    class Output(BaseModel):
        snapshot: dict[str, Any]
        state: dict[str, Any]
        contract_state: dict[str, Any]

    async def execute(self, input: Input) -> ToolResult:
        _, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        snapshot = get_runtime_snapshot()
        state = runtime_state_dict(snapshot)
        return ToolResult(
            output=self.Output(
                snapshot=runtime_snapshot_dict(snapshot),
                state=state,
                contract_state=state.get("contract_state", {}),
            )
        )


class GetEventsSinceTool(_SafeRuntimeTool):
    name = "get_events_since"
    description = "Read runtime events emitted after a given physics tick."

    class Input(BaseModel):
        tick: int = Field(default=0, description="Only return events with tick greater than this value")

    class Output(BaseModel):
        events: list[dict[str, Any]]

    async def execute(self, input: Input) -> ToolResult:
        return ToolResult(output=self.Output(events=[event.__dict__ for event in runtime_events_since(input.tick)]))


class CaptureViewportTool(_SafeRuntimeTool):
    name = "capture_viewport"
    description = "Persist a viewport screenshot artifact, using the runtime bridge screenshot when available or headless capture as fallback."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        scene_path: str = Field(default="", description="Optional scene path for headless fallback capture")
        godot_path: str = Field(default="godot", description="Path to the Godot executable for headless fallback capture")
        output_path: str = Field(default="", description="Optional absolute path for the saved image")
        artifact_name: str = Field(default="viewport", description="Artifact name when output_path is omitted")
        delay_ms: int = Field(default=1000, description="Wait time before capture when using headless fallback")

    class Output(BaseModel):
        path: str
        image_base64: str
        source: str

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)

        if input.output_path:
            output_path, out_err = _validate_path(input.output_path)
            if out_err:
                return ToolResult(error=out_err)
        else:
            output_path = build_artifact_path(project_path, category="screenshots", name=input.artifact_name)

        snapshot = get_runtime_snapshot()
        if snapshot and snapshot.screenshot_paths:
            last_path = Path(snapshot.screenshot_paths[-1])
            if last_path.exists():
                copy_to_artifact(last_path, output_path)
                add_runtime_screenshot(str(output_path))
                return ToolResult(
                    output=self.Output(
                        path=str(output_path),
                        image_base64=encode_image(str(output_path)),
                        source="runtime",
                    )
                )

        fallback_scene = input.scene_path or (snapshot.active_scene if snapshot else "")
        if not fallback_scene:
            return ToolResult(error="No runtime screenshot available and no scene_path was provided for fallback capture.")

        screenshot_tool = ScreenshotTool()
        result = await screenshot_tool.execute(
            screenshot_tool.Input(
                scene_path=fallback_scene,
                godot_path=input.godot_path,
                project_path=str(project_path),
                output_path=str(output_path),
                artifact_name=input.artifact_name,
                delay_ms=input.delay_ms,
            )
        )
        if result.error:
            return result
        snapshot = get_runtime_snapshot() or RuntimeSnapshot(active_scene=fallback_scene)
        snapshot.active_scene = fallback_scene
        snapshot.source = "headless"
        snapshot.evidence_level = "medium"
        update_runtime_snapshot(snapshot)
        add_runtime_screenshot(result.output.image_path)
        return ToolResult(output=self.Output(path=result.output.image_path, image_base64=result.output.image_base64, source="headless"))


class CompareBaselineTool(_SafeRuntimeTool):
    name = "compare_baseline"
    description = "Compare a screenshot or sprite artifact against a stored baseline and save a diff image."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        actual_path: str = Field(description="Absolute path to the captured image")
        baseline_id: str = Field(description="Baseline id relative to tests/baselines, without the .png suffix")
        tolerance: int = Field(default=0, description="Per-pixel max channel delta allowed before counting as a mismatch")
        region: list[int] = Field(default_factory=list, description="Optional region [x, y, width, height]")
        create_baseline: bool = Field(default=False, description="When true, create the baseline from the actual image if missing")

    class Output(BaseModel):
        matched: bool
        baseline_created: bool = False
        actual_path: str
        baseline_path: str
        diff_path: str = ""
        pixel_diff_count: int = 0
        max_channel_delta: int = 0
        diff_bbox: list[int] = Field(default_factory=list)
        reason: str = ""

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        actual_path, actual_err = _validate_path(input.actual_path)
        if actual_err:
            return ToolResult(error=actual_err)
        baseline_path = resolve_baseline_path(project_path, input.baseline_id)
        diff_path = build_artifact_path(project_path, category="diffs", name=input.baseline_id.replace("/", "-"))
        comparison = compare_image_files(
            project_root=project_path,
            actual_path=actual_path,
            baseline_path=baseline_path,
            tolerance=input.tolerance,
            region=input.region,
            diff_path=diff_path,
            create_baseline=input.create_baseline,
        )
        return ToolResult(
            output=self.Output(
                matched=comparison.matched,
                baseline_created=comparison.baseline_created,
                actual_path=comparison.actual_path,
                baseline_path=comparison.baseline_path,
                diff_path=comparison.diff_path,
                pixel_diff_count=comparison.pixel_diff_count,
                max_channel_delta=comparison.max_channel_delta,
                diff_bbox=list(comparison.diff_bbox or ()),
                reason=comparison.reason,
            )
        )


class ReportFailureTool(_SafeRuntimeTool):
    name = "report_failure"
    description = "Write a structured failure bundle for a runtime or visual regression test."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        test_id: str = Field(description="Stable test or scenario id")
        scene: str = Field(default="", description="Active scene when the failure occurred")
        step: str = Field(default="", description="Human-readable step description")
        reason: str = Field(default="", description="Failure reason code")
        ui_state: dict[str, Any] = Field(default_factory=dict)
        image_assert: dict[str, Any] = Field(default_factory=dict)
        artifacts: dict[str, Any] = Field(default_factory=dict)
        details: dict[str, Any] = Field(default_factory=dict)

    class Output(BaseModel):
        bundle_path: str
        report: str

    async def execute(self, input: Input) -> ToolResult:
        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)
        payload = {
            "test_id": input.test_id,
            "scene": input.scene,
            "step": input.step,
            "reason": input.reason,
            "ui_state": input.ui_state,
            "image_assert": input.image_assert,
            "artifacts": input.artifacts,
            "details": input.details,
        }
        bundle_path = write_failure_bundle(project_path, test_id=input.test_id, payload=payload)
        report = json.dumps(payload, indent=2, ensure_ascii=False)[:2000]
        return ToolResult(output=self.Output(bundle_path=str(bundle_path), report=report))


class SliceSpriteSheetTool(BaseTool):
    name = "slice_sprite_sheet"
    description = "Slice a sprite sheet into individual PNG frames, optionally removing a chroma key background first."

    class Input(BaseModel):
        input_path: str = Field(description="Absolute path to the source PNG sprite sheet")
        output_dir: str = Field(description="Absolute directory where sliced frames will be written")
        frame_width: int = Field(description="Width of each frame in pixels")
        frame_height: int = Field(description="Height of each frame in pixels")
        columns: int = Field(default=0, description="Optional explicit column count")
        rows: int = Field(default=0, description="Optional explicit row count")
        prefix: str = Field(default="frame", description="Output filename prefix")
        chroma_key: str = Field(default="#00FF00", description="Hex chroma key to remove before slicing")
        tolerance: int = Field(default=60, description="Chroma key tolerance")
        trim: bool = Field(default=False, description="Trim transparent borders from each sliced frame")
        metadata_path: str = Field(default="", description="Optional metadata JSON output path")
        project_path: str = Field(default="", description="Optional absolute Godot project root used to reimport generated frames")
        godot_path: str = Field(default="godot", description="Path to the Godot executable used for reimport")
        reimport_assets: bool = Field(default=False, description="Run Godot --import after writing frames when project_path is provided")

    class Output(BaseModel):
        frame_count: int
        metadata_path: str
        frame_paths: list[str]
        reimported: bool = False
        import_warnings: list[str] = Field(default_factory=list)

    def is_destructive(self) -> bool:
        return False

    async def execute(self, input: Input) -> ToolResult:
        from godot_agent.tools.sprite_pipeline import parse_hex_color, save_manifest, slice_sprite_sheet

        input_path, err = _validate_path(input.input_path)
        if err:
            return ToolResult(error=err)
        output_dir, out_err = _validate_path(input.output_dir)
        if out_err:
            return ToolResult(error=out_err)
        if input.metadata_path:
            metadata_path, meta_err = _validate_path(input.metadata_path)
            if meta_err:
                return ToolResult(error=meta_err)
        else:
            metadata_path = output_dir / "spritesheet.json"

        manifest = slice_sprite_sheet(
            source_path=input_path,
            output_dir=output_dir,
            frame_width=input.frame_width,
            frame_height=input.frame_height,
            columns=input.columns,
            rows=input.rows,
            prefix=input.prefix,
            chroma_key=parse_hex_color(input.chroma_key),
            tolerance=input.tolerance,
            trim=input.trim,
        )
        save_manifest(manifest, metadata_path)
        reimported = False
        import_warnings: list[str] = []
        if input.reimport_assets:
            if not input.project_path:
                return ToolResult(error="project_path is required when reimport_assets is true")
            project_path, project_err = _validate_path(input.project_path)
            if project_err:
                return ToolResult(error=project_err)
            result = await run_godot_import(project_path, godot_path=input.godot_path)
            reimported = True
            import_warnings = [warning.message for warning in result.report.warnings]
            if result.exit_code != 0 or result.report.errors:
                messages = "; ".join(error.message for error in result.report.errors) or result.raw_output or "unknown Godot import error"
                return ToolResult(error=f"Godot import failed after slicing sprite sheet: {messages}")
        return ToolResult(
            output=self.Output(
                frame_count=manifest.frame_count,
                metadata_path=str(metadata_path),
                frame_paths=[frame.path for frame in manifest.frames[:50]],
                reimported=reimported,
                import_warnings=import_warnings,
            )
        )


class ValidateSpriteImportsTool(_SafeRuntimeTool):
    name = "validate_sprite_imports"
    description = "Validate a sliced sprite manifest or frame directory for missing files, size consistency, chroma-key cleanup, alpha, and pixel-art acceptance rules."

    class Input(BaseModel):
        project_path: str = Field(description="Absolute path to the Godot project root")
        metadata_path: str = Field(default="", description="Optional metadata JSON emitted by slice_sprite_sheet")
        sprite_dir: str = Field(default="", description="Optional directory containing PNG frames when no metadata file is provided")
        godot_path: str = Field(default="godot", description="Path to the Godot executable used for reimport")
        reimport_assets: bool = Field(default=True, description="Run Godot --import before validating sprite integrity")
        smoke_scene_path: str = Field(default="", description="Optional scene path to screenshot after reimport for asset visibility smoke checks")
        smoke_baseline_id: str = Field(default="", description="Optional baseline id for the smoke screenshot")
        smoke_tolerance: int = Field(default=0, description="Tolerance used when comparing the smoke screenshot against a baseline")
        smoke_delay_ms: int = Field(default=1000, description="Delay before screenshot capture during smoke validation")
        create_baseline: bool = Field(default=False, description="Create the smoke baseline from the captured image when it does not exist")

    class Output(BaseModel):
        valid: bool
        frame_count: int
        issues: list[str]
        warnings: list[str] = Field(default_factory=list)
        qa_reports: list[str] = Field(default_factory=list)
        reimported: bool = False
        smoke_capture_path: str = ""
        smoke_source: str = ""
        baseline_matched: bool | None = None
        baseline_path: str = ""
        diff_path: str = ""
        failure_bundle: str = ""

    async def execute(self, input: Input) -> ToolResult:
        from godot_agent.runtime.design_memory import load_design_memory, resolved_asset_spec
        from godot_agent.tools.sprite_qa import qa_sprite_file

        project_path, err = _validate_path(input.project_path)
        if err:
            return ToolResult(error=err)

        issues: list[str] = []
        warnings: list[str] = []
        qa_reports: list[str] = []
        frame_paths: list[Path] = []
        asset_spec = resolved_asset_spec(load_design_memory(project_path))
        reimported = False
        smoke_capture_path = ""
        smoke_source = ""
        baseline_matched: bool | None = None
        baseline_path = ""
        diff_path = ""
        failure_bundle = ""

        if input.reimport_assets:
            result = await run_godot_import(project_path, godot_path=input.godot_path)
            reimported = True
            warnings.extend(warning.message for warning in result.report.warnings)
            issues.extend(error.message for error in result.report.errors)
            if result.exit_code != 0:
                issues.append(f"Godot import exited with code {result.exit_code}.")

        if input.metadata_path:
            metadata_path, meta_err = _validate_path(input.metadata_path)
            if meta_err:
                return ToolResult(error=meta_err)
            if not metadata_path.exists():
                return ToolResult(error=f"Metadata file not found: {metadata_path}")
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            for frame in payload.get("frames", []):
                frame_path, frame_err = _validate_path(frame.get("path", ""))
                if frame_err:
                    issues.append(frame_err)
                    continue
                frame_paths.append(frame_path)
        else:
            sprite_dir, sprite_err = _validate_path(input.sprite_dir or str(project_path))
            if sprite_err:
                return ToolResult(error=sprite_err)
            frame_paths = sorted(sprite_dir.glob("*.png"))

        dimensions: set[tuple[int, int]] = set()
        for frame_path in frame_paths:
            if not frame_path.exists():
                issues.append(f"Missing frame: {frame_path}")
                continue
            try:
                from PIL import Image

                with Image.open(frame_path) as img:
                    dimensions.add(img.size)
                qa_report = qa_sprite_file(
                    project_root=project_path,
                    image_path=frame_path,
                    spec=asset_spec,
                    artifact_name=f"validate-{frame_path.stem}",
                )
                qa_reports.append(qa_report.artifacts.get("qa", ""))
                issues.extend(qa_report.issues)
                warnings.extend(qa_report.warnings)
            except Exception as exc:
                issues.append(f"Failed to open {frame_path}: {exc}")
        if len(dimensions) > 1:
            issues.append(f"Inconsistent frame dimensions: {sorted(dimensions)}")

        if not issues and input.smoke_scene_path:
            screenshot_tool = ScreenshotTool()
            smoke_output = build_artifact_path(project_path, category="screenshots", name=f"asset-smoke-{Path(input.smoke_scene_path).stem}")
            shot = await screenshot_tool.execute(
                screenshot_tool.Input(
                    scene_path=input.smoke_scene_path,
                    godot_path=input.godot_path,
                    project_path=str(project_path),
                    output_path=str(smoke_output),
                    artifact_name=f"asset-smoke-{Path(input.smoke_scene_path).stem}",
                    delay_ms=input.smoke_delay_ms,
                )
            )
            if shot.error:
                issues.append(f"Asset smoke capture failed: {shot.error}")
            else:
                smoke_capture_path = shot.output.image_path
                smoke_source = "headless"
                if input.smoke_baseline_id:
                    baseline = resolve_baseline_path(project_path, input.smoke_baseline_id)
                    comparison = compare_image_files(
                        project_root=project_path,
                        actual_path=Path(smoke_capture_path),
                        baseline_path=baseline,
                        tolerance=input.smoke_tolerance,
                        diff_path=build_artifact_path(project_path, category="diffs", name=input.smoke_baseline_id.replace("/", "-")),
                        create_baseline=input.create_baseline,
                    )
                    baseline_matched = comparison.matched
                    baseline_path = comparison.baseline_path
                    diff_path = comparison.diff_path
                    if not comparison.matched:
                        issues.append(
                            f"Smoke baseline mismatch for {input.smoke_baseline_id}: "
                            f"{comparison.reason or 'visual_diff'}"
                        )
                        failure_bundle = str(
                            write_failure_bundle(
                                project_path,
                                test_id=f"asset-smoke-{Path(input.smoke_scene_path).stem}",
                                payload={
                                    "test_id": input.smoke_baseline_id or "asset_smoke",
                                    "scene": input.smoke_scene_path,
                                    "step": "asset smoke validation",
                                    "reason": comparison.reason or "visual_diff_exceeded",
                                    "ui_state": runtime_state_dict(get_runtime_snapshot()),
                                    "image_assert": comparison.to_dict(),
                                    "artifacts": {
                                        "actual": comparison.actual_path,
                                        "expected": comparison.baseline_path,
                                        "diff": comparison.diff_path,
                                    },
                                },
                            )
                        )

        return ToolResult(
            output=self.Output(
                valid=not issues,
                frame_count=len(frame_paths),
                issues=list(dict.fromkeys(issues)),
                warnings=list(dict.fromkeys(warnings)),
                qa_reports=[path for path in qa_reports if path],
                reimported=reimported,
                smoke_capture_path=smoke_capture_path,
                smoke_source=smoke_source,
                baseline_matched=baseline_matched,
                baseline_path=baseline_path,
                diff_path=diff_path,
                failure_bundle=failure_bundle,
            )
        )

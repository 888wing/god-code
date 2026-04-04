import asyncio
from pathlib import Path

from PIL import Image

from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, clear_runtime_snapshot, update_runtime_snapshot
from godot_agent.tools.file_ops import clear_project_root, set_project_root
from godot_agent.tools.runtime_harness import (
    CaptureViewportTool,
    CompareBaselineTool,
    SliceSpriteSheetTool,
    ValidateSpriteImportsTool,
)


def _write_png(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), color).save(path, "PNG")


def test_capture_viewport_prefers_runtime_screenshot(tmp_path):
    set_project_root(tmp_path)
    runtime_image = tmp_path / "runtime.png"
    _write_png(runtime_image, (255, 0, 0, 255))
    update_runtime_snapshot(RuntimeSnapshot(screenshot_paths=[str(runtime_image)]))
    try:
        tool = CaptureViewportTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path), artifact_name="runtime-shot")))
        assert result.output.source == "runtime"
        assert Path(result.output.path).exists()
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_compare_baseline_tool_writes_diff_on_mismatch(tmp_path):
    set_project_root(tmp_path)
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "tests" / "baselines" / "ui" / "panel.png"
    _write_png(actual, (255, 0, 0, 255))
    _write_png(baseline, (0, 0, 255, 255))
    try:
        tool = CompareBaselineTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    actual_path=str(actual),
                    baseline_id="ui/panel",
                )
            )
        )
        assert result.output.matched is False
        assert Path(result.output.diff_path).exists()
    finally:
        clear_project_root()


def test_slice_sprite_sheet_and_validate_imports(tmp_path):
    set_project_root(tmp_path)
    sheet = tmp_path / "sheet.png"
    output_dir = tmp_path / "frames"
    manifest = tmp_path / "frames.json"
    image = Image.new("RGBA", (16, 8), (0, 255, 0, 255))
    image.paste((255, 0, 0, 255), (0, 0, 8, 8))
    image.paste((0, 0, 255, 255), (8, 0, 16, 8))
    image.save(sheet, "PNG")
    try:
        slice_tool = SliceSpriteSheetTool()
        slice_result = asyncio.run(
            slice_tool.execute(
                slice_tool.Input(
                    input_path=str(sheet),
                    output_dir=str(output_dir),
                    frame_width=8,
                    frame_height=8,
                    metadata_path=str(manifest),
                )
            )
        )
        assert slice_result.output.frame_count == 2
        assert Path(slice_result.output.metadata_path).exists()

        validate_tool = ValidateSpriteImportsTool()
        validate_result = asyncio.run(
            validate_tool.execute(
                validate_tool.Input(project_path=str(tmp_path), metadata_path=str(manifest))
            )
        )
        assert validate_result.output.valid is True
        assert validate_result.output.frame_count == 2
    finally:
        clear_project_root()

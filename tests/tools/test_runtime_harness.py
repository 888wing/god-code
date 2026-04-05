import asyncio
from pathlib import Path

from PIL import Image

from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, clear_runtime_snapshot, update_runtime_snapshot
from godot_agent.runtime.config import AgentConfig
from godot_agent.tools.file_ops import clear_project_root, set_project_root
from godot_agent.tools.runtime_harness import (
    CaptureViewportTool,
    CompareBaselineTool,
    GetRuntimeStateTool,
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
                validate_tool.Input(
                    project_path=str(tmp_path),
                    metadata_path=str(manifest),
                    reimport_assets=False,
                )
            )
        )
        assert validate_result.output.valid is True
        assert validate_result.output.frame_count == 2
    finally:
        clear_project_root()


def test_slice_sprite_sheet_reimports_when_requested(tmp_path, monkeypatch):
    set_project_root(tmp_path)
    sheet = tmp_path / "sheet.png"
    output_dir = tmp_path / "frames"
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(sheet, "PNG")

    calls = []

    class _ImportWarning:
        def __init__(self, message: str):
            self.message = message

    class _ImportResult:
        exit_code = 0
        report = type("Report", (), {"errors": [], "warnings": [_ImportWarning("reimport warning")]})()
        raw_output = ""

    async def fake_import(project_path, *, godot_path="godot", timeout=120):
        calls.append((str(project_path), godot_path, timeout))
        return _ImportResult()

    monkeypatch.setattr("godot_agent.tools.runtime_harness.run_godot_import", fake_import)

    try:
        tool = SliceSpriteSheetTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    input_path=str(sheet),
                    output_dir=str(output_dir),
                    frame_width=8,
                    frame_height=8,
                    project_path=str(tmp_path),
                    reimport_assets=True,
                    godot_path="/Applications/Godot",
                )
            )
        )
        assert result.output.reimported is True
        assert result.output.import_warnings == ["reimport warning"]
        assert calls == [(str(tmp_path), "/Applications/Godot", 120)]
    finally:
        clear_project_root()


def test_validate_sprite_imports_reimports_before_qa(tmp_path, monkeypatch):
    set_project_root(tmp_path)
    frame = tmp_path / "frame.png"
    _write_png(frame, (255, 0, 0, 255))

    calls = []

    class _ImportResult:
        exit_code = 0
        report = type("Report", (), {"errors": [], "warnings": []})()

    async def fake_import(project_path, *, godot_path="godot", timeout=120):
        calls.append((str(project_path), godot_path, timeout))
        return _ImportResult()

    monkeypatch.setattr("godot_agent.tools.runtime_harness.run_godot_import", fake_import)

    try:
        tool = ValidateSpriteImportsTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    sprite_dir=str(tmp_path),
                    godot_path="/Applications/Godot",
                )
            )
        )
        assert result.output.valid is True
        assert result.output.reimported is True
        assert calls == [(str(tmp_path), "/Applications/Godot", 120)]
    finally:
        clear_project_root()


def test_validate_sprite_imports_uses_configured_godot_path_when_not_provided(tmp_path, monkeypatch):
    set_project_root(tmp_path)
    frame = tmp_path / "frame.png"
    _write_png(frame, (255, 0, 0, 255))

    calls = []

    class _DummyProcess:
        returncode = 0

        async def communicate(self):
            return b"import ok\n", b""

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _DummyProcess()

    monkeypatch.setattr(
        "godot_agent.tools.godot_cli.load_config",
        lambda path: AgentConfig(godot_path="/Applications/Godot.app/Contents/MacOS/Godot"),
    )
    monkeypatch.setattr(
        "godot_agent.tools.godot_cli.asyncio.create_subprocess_exec",
        fake_exec,
    )

    try:
        tool = ValidateSpriteImportsTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    sprite_dir=str(tmp_path),
                )
            )
        )
        assert result.output.valid is True
        assert calls[0][0][:3] == (
            "/Applications/Godot.app/Contents/MacOS/Godot",
            "--import",
            "--quit",
        )
    finally:
        clear_project_root()


def test_get_runtime_state_tool_returns_contract_state(tmp_path):
    set_project_root(tmp_path)
    update_runtime_snapshot(RuntimeSnapshot(state={"enemy_projectiles": 9, "lives_remaining": 2}))
    try:
        tool = GetRuntimeStateTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path))))
        assert result.output.contract_state["enemy_bullets"] == 9
        assert result.output.contract_state["player_lives"] == 2
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_validate_sprite_imports_can_run_smoke_capture_and_compare(tmp_path, monkeypatch):
    set_project_root(tmp_path)
    frame = tmp_path / "frame.png"
    baseline = tmp_path / "tests" / "baselines" / "ui" / "asset-smoke.png"
    _write_png(frame, (255, 0, 0, 255))
    _write_png(baseline, (1, 2, 3, 255))

    class _ImportResult:
        exit_code = 0
        report = type("Report", (), {"errors": [], "warnings": []})()

    async def fake_import(project_path, *, godot_path="godot", timeout=120):
        return _ImportResult()

    async def fake_capture(self, input):
        _write_png(Path(input.output_path), (1, 2, 3, 255))
        return type(
            "Result",
            (),
            {"error": "", "output": type("Output", (), {"image_path": str(input.output_path)})()},
        )()

    monkeypatch.setattr("godot_agent.tools.runtime_harness.run_godot_import", fake_import)
    monkeypatch.setattr("godot_agent.tools.runtime_harness.ScreenshotTool.execute", fake_capture)

    try:
        tool = ValidateSpriteImportsTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    sprite_dir=str(tmp_path),
                    smoke_scene_path="res://scenes/game.tscn",
                    smoke_baseline_id="ui/asset-smoke",
                )
            )
        )
        assert result.output.valid is True
        assert result.output.smoke_capture_path
        assert result.output.baseline_matched is True
    finally:
        clear_project_root()

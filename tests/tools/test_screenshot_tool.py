from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from godot_agent.tools.screenshot import ScreenshotTool


class _DummyProcess:
    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(self._output_path)
        return b"", b""


@pytest.mark.asyncio
async def test_screenshot_tool_omits_headless_by_default(tmp_path, monkeypatch):
    project_path = tmp_path / "project"
    project_path.mkdir()
    output_path = project_path / "capture.png"
    calls: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return _DummyProcess(output_path)

    monkeypatch.setattr(
        "godot_agent.tools.screenshot.asyncio.create_subprocess_exec",
        fake_exec,
    )
    monkeypatch.setattr(
        "godot_agent.tools.screenshot.encode_image",
        lambda _: "encoded-image",
    )

    tool = ScreenshotTool()
    result = await tool.execute(
        ScreenshotTool.Input(
            scene_path="res://scenes/test.tscn",
            godot_path="/Applications/Godot.app/Contents/MacOS/Godot",
            project_path=str(project_path),
            output_path=str(output_path),
            delay_ms=100,
        )
    )

    assert result.error is None
    assert result.output.image_path == str(output_path)
    assert result.output.image_base64 == "encoded-image"
    assert calls
    assert "--headless" not in calls[0]


@pytest.mark.asyncio
async def test_screenshot_tool_can_disable_base64_and_use_headless(
    tmp_path, monkeypatch
):
    project_path = tmp_path / "project"
    project_path.mkdir()
    output_path = project_path / "capture.png"
    calls: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return _DummyProcess(output_path)

    def fail_encode(_: str) -> str:
        raise AssertionError("encode_image should not be called")

    monkeypatch.setattr(
        "godot_agent.tools.screenshot.asyncio.create_subprocess_exec",
        fake_exec,
    )
    monkeypatch.setattr("godot_agent.tools.screenshot.encode_image", fail_encode)

    tool = ScreenshotTool()
    result = await tool.execute(
        ScreenshotTool.Input(
            scene_path="res://scenes/test.tscn",
            godot_path="/Applications/Godot.app/Contents/MacOS/Godot",
            project_path=str(project_path),
            output_path=str(output_path),
            headless=True,
            include_base64=False,
            delay_ms=100,
        )
    )

    assert result.error is None
    assert result.output.image_path == str(output_path)
    assert result.output.image_base64 == ""
    assert calls
    assert "--headless" in calls[0]

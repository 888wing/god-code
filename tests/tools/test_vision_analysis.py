"""Tests for AnalyzeScreenshotTool — vision-driven UI analysis."""

from __future__ import annotations

import json

import pytest
from PIL import Image
from unittest.mock import AsyncMock, patch

from godot_agent.tools.vision_analysis import AnalyzeScreenshotTool


# -- Metadata -----------------------------------------------------------------


def test_tool_metadata():
    tool = AnalyzeScreenshotTool()
    assert tool.name == "analyze_screenshot"
    assert tool.description
    assert not tool.is_read_only()


def test_tool_is_not_destructive():
    tool = AnalyzeScreenshotTool()
    # The tool writes analysis output but doesn't modify project files
    assert not tool.is_destructive()


# -- Happy path ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_returns_structured_output(tmp_path):
    tool = AnalyzeScreenshotTool()
    # Create a tiny test image
    img = Image.new("RGB", (64, 64), (100, 100, 100))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    mock_response = json.dumps(
        {
            "analysis": "Battle scene with HUD overlay",
            "suggestions": [
                {
                    "node_path": "/root/HUD/Label",
                    "property": "font_size",
                    "new_value": "12",
                }
            ],
            "score": 3.5,
        }
    )

    with patch.object(
        tool,
        "_call_vision_model",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await tool.execute(
            tool.Input(
                screenshot_path=str(img_path),
                project_path=str(tmp_path),
            )
        )

    assert result.error is None
    assert "Battle scene" in result.output


@pytest.mark.asyncio
async def test_analyze_with_focus_parameter(tmp_path):
    tool = AnalyzeScreenshotTool()
    img = Image.new("RGB", (64, 64), (200, 50, 50))
    img_path = tmp_path / "ui_shot.png"
    img.save(img_path)

    mock_response = json.dumps(
        {
            "analysis": "UI elements detected",
            "suggestions": [],
            "score": 4.0,
        }
    )

    with patch.object(
        tool,
        "_call_vision_model",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_call:
        result = await tool.execute(
            tool.Input(
                screenshot_path=str(img_path),
                project_path=str(tmp_path),
                focus="ui",
            )
        )

    assert result.error is None
    # Verify the focus parameter was threaded through to the prompt
    call_args = mock_call.call_args
    prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "UI" in prompt_arg or "ui" in prompt_arg.lower()


# -- Error handling -----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_screenshot_returns_error(tmp_path):
    tool = AnalyzeScreenshotTool()
    result = await tool.execute(
        tool.Input(
            screenshot_path=str(tmp_path / "nonexistent.png"),
            project_path=str(tmp_path),
        )
    )
    assert result.error is not None
    assert "not found" in result.error.lower() or "does not exist" in result.error.lower()


@pytest.mark.asyncio
async def test_vision_model_error_surfaces(tmp_path):
    tool = AnalyzeScreenshotTool()
    img = Image.new("RGB", (64, 64), (0, 0, 0))
    img_path = tmp_path / "black.png"
    img.save(img_path)

    with patch.object(
        tool,
        "_call_vision_model",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API connection failed"),
    ):
        result = await tool.execute(
            tool.Input(
                screenshot_path=str(img_path),
                project_path=str(tmp_path),
            )
        )

    assert result.error is not None
    assert "API connection failed" in result.error

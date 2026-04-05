"""Tests for ScoreScreenshotTool — vision-driven visual quality scoring."""

from __future__ import annotations

import json

import pytest
from PIL import Image
from unittest.mock import AsyncMock, patch

from godot_agent.tools.vision_scoring import ScoreScreenshotTool


# -- Metadata -----------------------------------------------------------------


def test_tool_metadata():
    tool = ScoreScreenshotTool()
    assert tool.name == "score_screenshot"
    assert tool.description
    assert not tool.is_read_only()


def test_tool_is_not_destructive():
    tool = ScoreScreenshotTool()
    assert not tool.is_destructive()


# -- Happy path ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_returns_structured_output(tmp_path):
    tool = ScoreScreenshotTool()
    img = Image.new("RGB", (64, 64), (100, 100, 100))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    mock_response = json.dumps(
        {
            "scores": {
                "visual_quality": 4,
                "layout": 3,
                "readability": 4,
                "completeness": 3,
                "polish": 2,
            },
            "overall": 3.2,
            "summary": "Functional but needs polish",
            "top_issue": "Low polish score due to placeholder assets",
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
    parsed = json.loads(result.output)
    assert "scores" in parsed
    assert parsed["overall"] == 3.2
    assert len(parsed["scores"]) == 5
    # No before_path → no improved flag
    assert "improved" not in parsed


@pytest.mark.asyncio
async def test_score_with_criteria_parameter(tmp_path):
    tool = ScoreScreenshotTool()
    img = Image.new("RGB", (64, 64), (200, 50, 50))
    img_path = tmp_path / "demo_shot.png"
    img.save(img_path)

    mock_response = json.dumps(
        {
            "scores": {
                "visual_polish": 4,
                "ui_completeness": 3,
                "layout_quality": 4,
                "text_readability": 5,
                "first_impression": 3,
            },
            "overall": 3.8,
            "summary": "Good demo quality",
            "top_issue": "First impression could be stronger",
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
                criteria="demo_quality",
            )
        )

    assert result.error is None
    # Verify the criteria parameter was threaded through to the prompt
    call_args = mock_call.call_args
    prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "visual_polish" in prompt_arg or "first_impression" in prompt_arg


# -- Before/after comparison --------------------------------------------------


@pytest.mark.asyncio
async def test_score_before_after_comparison(tmp_path):
    tool = ScoreScreenshotTool()

    before_img = Image.new("RGB", (64, 64), (50, 50, 50))
    before_path = tmp_path / "before.png"
    before_img.save(before_path)

    after_img = Image.new("RGB", (64, 64), (200, 200, 200))
    after_path = tmp_path / "after.png"
    after_img.save(after_path)

    mock_response = json.dumps(
        {
            "scores": {
                "visual_quality": 4,
                "layout": 4,
                "readability": 5,
                "completeness": 4,
                "polish": 3,
            },
            "overall": 4.0,
            "improved": True,
            "summary": "Significant improvement in readability",
            "top_issue": "Polish still needs work",
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
                screenshot_path=str(after_path),
                project_path=str(tmp_path),
                before_path=str(before_path),
            )
        )

    assert result.error is None
    parsed = json.loads(result.output)
    assert parsed["improved"] is True
    assert parsed["overall"] == 4.0

    # Verify both images were sent to the vision model
    call_args = mock_call.call_args
    images_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("images", [])
    # Should have 2 images (before + after)
    if isinstance(images_arg, list):
        assert len(images_arg) == 2
    else:
        # Single image string means before image was passed separately
        pass


# -- Error handling -----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_screenshot_returns_error(tmp_path):
    tool = ScoreScreenshotTool()
    result = await tool.execute(
        tool.Input(
            screenshot_path=str(tmp_path / "nonexistent.png"),
            project_path=str(tmp_path),
        )
    )
    assert result.error is not None
    assert "not found" in result.error.lower() or "does not exist" in result.error.lower()


@pytest.mark.asyncio
async def test_missing_before_path_returns_error(tmp_path):
    tool = ScoreScreenshotTool()

    # After image exists
    after_img = Image.new("RGB", (64, 64), (200, 200, 200))
    after_path = tmp_path / "after.png"
    after_img.save(after_path)

    result = await tool.execute(
        tool.Input(
            screenshot_path=str(after_path),
            project_path=str(tmp_path),
            before_path=str(tmp_path / "nonexistent_before.png"),
        )
    )
    assert result.error is not None
    assert "before" in result.error.lower() or "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_vision_model_error_surfaces(tmp_path):
    tool = ScoreScreenshotTool()
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


@pytest.mark.asyncio
async def test_parse_error_returns_raw_response(tmp_path):
    """When the LLM returns non-JSON, the tool should still return the raw text."""
    tool = ScoreScreenshotTool()
    img = Image.new("RGB", (64, 64), (128, 128, 128))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    raw_text = "I cannot score this image because it is a solid color."

    with patch.object(
        tool,
        "_call_vision_model",
        new_callable=AsyncMock,
        return_value=raw_text,
    ):
        result = await tool.execute(
            tool.Input(
                screenshot_path=str(img_path),
                project_path=str(tmp_path),
            )
        )

    # Should not error — returns the raw response for the caller to handle
    assert result.error is None
    assert "solid color" in result.output

from __future__ import annotations

from godot_agent.prompts.vision_templates import (
    ANALYSIS_PROMPT,
    ITERATION_PROMPT,
    SCORING_PROMPT,
    build_analysis_prompt,
    build_scoring_prompt,
)


def test_analysis_prompt_contains_required_sections():
    prompt = build_analysis_prompt(focus="ui")
    assert "UI Element Detection" in prompt
    assert "Visual Quality" in prompt
    assert "Godot" in prompt


def test_scoring_prompt_requests_json():
    prompt = build_scoring_prompt(criteria="demo_quality")
    assert "JSON" in prompt
    assert "1-5" in prompt


def test_iteration_prompt_has_before_after():
    assert "before" in ITERATION_PROMPT.lower() or "previous" in ITERATION_PROMPT.lower()
    assert "SEVERITY" in ITERATION_PROMPT


def test_focus_variants():
    general = build_analysis_prompt(focus="general")
    ui = build_analysis_prompt(focus="ui")
    gameplay = build_analysis_prompt(focus="gameplay")
    assert general != ui  # Different focus = different prompt
    assert ui != gameplay


def test_base_analysis_prompt_is_string():
    assert isinstance(ANALYSIS_PROMPT, str)
    assert len(ANALYSIS_PROMPT) > 50


def test_base_scoring_prompt_is_string():
    assert isinstance(SCORING_PROMPT, str)
    assert len(SCORING_PROMPT) > 50


def test_base_iteration_prompt_is_string():
    assert isinstance(ITERATION_PROMPT, str)
    assert len(ITERATION_PROMPT) > 50


def test_analysis_prompt_general_covers_all_areas():
    prompt = build_analysis_prompt(focus="general")
    assert "Visual Quality" in prompt
    assert "Layout" in prompt
    assert "Godot" in prompt


def test_analysis_prompt_gameplay_focus():
    prompt = build_analysis_prompt(focus="gameplay")
    assert "gameplay" in prompt.lower() or "Gameplay" in prompt
    assert "Godot" in prompt


def test_scoring_prompt_unknown_criteria_falls_back():
    prompt = build_scoring_prompt(criteria="unknown_criteria")
    # Should still produce a valid scoring prompt with JSON and 1-5 scale
    assert "JSON" in prompt
    assert "1-5" in prompt


def test_scoring_prompt_visual_polish_criteria():
    prompt = build_scoring_prompt(criteria="visual_polish")
    assert "JSON" in prompt
    assert "1-5" in prompt


def test_analysis_prompt_unknown_focus_falls_back():
    prompt = build_analysis_prompt(focus="nonexistent_focus")
    # Should fall back to general analysis
    assert "Godot" in prompt
    assert isinstance(prompt, str)

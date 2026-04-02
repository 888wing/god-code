import random
import string

import pytest

from godot_agent.cli import (
    _apply_provider_preset,
    _cd_argument,
    _command_argument,
    _effort_menu_options,
    _format_setting_display_value,
    _is_multiline_terminator,
    _main_menu_options,
    _mode_menu_options,
    _model_menu_options,
    _multiline_initial_fragment,
    _normalize_reasoning_effort,
    _provider_menu_options,
    _settings_menu_options,
    _setting_value_menu_options,
    _set_arguments,
    _starts_multiline_input,
    _sync_provider_from_model,
)
from godot_agent.runtime.config import AgentConfig

_RANDOM = random.Random(2026)
_FUZZ_CASES = [
    "".join(_RANDOM.choice(string.ascii_letters + string.digits + " /_\t\x7f-\"") for _ in range(length))
    for length in range(0, 32)
]


def test_apply_provider_preset_updates_provider_defaults():
    cfg = AgentConfig(provider="openai", base_url="https://api.openai.com/v1", model="gpt-5.4")
    provider = _apply_provider_preset(cfg, "anthropic")
    assert provider == "anthropic"
    assert cfg.provider == "anthropic"
    assert cfg.base_url == "https://api.anthropic.com/v1"
    assert cfg.model == "claude-sonnet-4.6"


def test_main_menu_exposes_interactive_secondary_commands():
    values = {option.value for option in _main_menu_options()}
    assert {"mode", "provider", "model", "effort", "resume", "cd", "set"}.issubset(values)


def test_settings_menu_covers_all_interactive_config_fields():
    values = {option.value for option in _settings_menu_options()}
    assert {
        "api_key",
        "provider",
        "base_url",
        "model",
        "reasoning_effort",
        "oauth_token",
        "max_turns",
        "max_tokens",
        "temperature",
        "godot_path",
        "language",
        "verbosity",
        "mode",
        "auto_validate",
        "auto_commit",
        "screenshot_max_iterations",
        "token_budget",
        "safety",
        "streaming",
        "autosave_session",
        "extra_prompt",
        "session_dir",
    }.issubset(values)


def test_mode_provider_and_effort_menu_options_are_populated():
    assert {option.value for option in _mode_menu_options()} == {"apply", "plan", "explain", "review", "fix"}
    assert "openai" in {option.value for option in _provider_menu_options()}
    assert "high" in {option.value for option in _effort_menu_options()}


def test_model_menu_includes_custom_entry():
    cfg = AgentConfig(provider="openai", base_url="https://api.openai.com/v1", model="gpt-5.4")
    values = {option.value for option in _model_menu_options(cfg)}
    assert "__custom__" in values
    assert "gpt-5.4" in values


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("mode", {"apply", "plan", "explain", "review", "fix"}),
        ("language", {"en", "zh-TW", "ja"}),
        ("verbosity", {"concise", "normal", "detailed"}),
        ("safety", {"strict", "normal", "permissive"}),
        ("streaming", {"true", "false"}),
    ],
)
def test_setting_value_menu_options_cover_fixed_choice_settings(key: str, expected: set[str]):
    options = _setting_value_menu_options(key)
    assert options is not None
    assert expected.issubset({option.value for option in options})


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("api_key", "sk-1234567890", "sk-1...7890"),
        ("oauth_token", "abcd1234", "********"),
        ("model", "gpt-5.4", "gpt-5.4"),
    ],
)
def test_format_setting_display_value_masks_secrets(key: str, value: str, expected: str):
    assert _format_setting_display_value(key, value) == expected


def test_sync_provider_from_model_updates_base_url_when_switching_family():
    cfg = AgentConfig(provider="openai", base_url="https://api.openai.com/v1", model="claude-opus-4.6")
    provider = _sync_provider_from_model(cfg, previous_provider="openai", previous_base_url="https://api.openai.com/v1")
    assert provider == "anthropic"
    assert cfg.provider == "anthropic"
    assert cfg.base_url == "https://api.anthropic.com/v1"


def test_normalize_reasoning_effort_rejects_unknown_value():
    with pytest.raises(ValueError):
        _normalize_reasoning_effort("turbo")


@pytest.mark.parametrize(
    ("value", "command", "expected"),
    [
        ("/mode", "/mode", ""),
        ("/mode   ", "/mode", ""),
        ("/mode apply", "/mode", "apply"),
        ("  /mode apply  ", "/mode", "apply"),
        ("/provider anthropic", "/provider", "anthropic"),
        ("/provider   anthropic  ", "/provider", "anthropic"),
        ("/provider", "/provider", ""),
        ("hello", "/provider", None),
    ],
)
def test_command_argument_handles_partial_and_trailing_space(value: str, command: str, expected: str | None):
    assert _command_argument(value, command) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/set mode apply", ("mode", "apply")),
        ("/set extra_prompt keep movement readable", ("extra_prompt", "keep movement readable")),
        ("/set", None),
        ("/set ", None),
        ("/set mode", None),
    ],
)
def test_set_arguments_are_parsed_safely(value: str, expected):
    assert _set_arguments(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cd /tmp/game", "/tmp/game"),
        ("cd   /tmp/game  ", "/tmp/game"),
        ("/cd /tmp/game", "/tmp/game"),
        ("cd", ""),
        ("cd ", ""),
        ("/cd", ""),
        ("/cd ", ""),
        ("hello", None),
    ],
)
def test_cd_argument_is_safe_for_empty_and_partial_input(value: str, expected: str | None):
    assert _cd_argument(value) == expected


@pytest.mark.parametrize(
    ("value", "starts", "fragment"),
    [
        ('"""', True, ""),
        ('"""hello', True, "hello"),
        ('  """hello', True, "hello"),
        ('""" hello', True, " hello"),
        ('hello', False, ""),
        (' "" ', False, ""),
    ],
)
def test_multiline_helpers_parse_start_and_fragment(value: str, starts: bool, fragment: str):
    assert _starts_multiline_input(value) is starts
    assert _multiline_initial_fragment(value) == fragment


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ('"""', True),
        ('  """  ', True),
        ("", False),
        ("text", False),
    ],
)
def test_multiline_terminator_detection(value: str | None, expected: bool):
    assert _is_multiline_terminator(value) is expected


@pytest.mark.parametrize("value", _FUZZ_CASES)
def test_command_parsing_helpers_do_not_crash_on_fuzz_input(value: str):
    for command in ("/mode", "/provider", "/model", "/effort", "/resume", "/cd", "cd"):
        result = _command_argument(value, command)
        assert result is None or isinstance(result, str)

    set_result = _set_arguments(value)
    assert set_result is None or (isinstance(set_result, tuple) and len(set_result) == 2)

    cd_result = _cd_argument(value)
    assert cd_result is None or isinstance(cd_result, str)

    assert isinstance(_starts_multiline_input(value), bool)
    assert isinstance(_multiline_initial_fragment(value), str)
    assert isinstance(_is_multiline_terminator(value), bool)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/resume", ""),
        ("/resume ", ""),
        ("/resume latest", "latest"),
        (" /resume latest ", "latest"),
    ],
)
def test_resume_argument_parsing_is_safe(value: str, expected: str):
    assert _command_argument(value, "/resume") == expected

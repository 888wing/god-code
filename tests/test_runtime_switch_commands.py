import pytest

from godot_agent.cli import _apply_provider_preset, _normalize_reasoning_effort, _sync_provider_from_model
from godot_agent.runtime.config import AgentConfig


def test_apply_provider_preset_updates_provider_defaults():
    cfg = AgentConfig(provider="openai", base_url="https://api.openai.com/v1", model="gpt-5.4")
    provider = _apply_provider_preset(cfg, "anthropic")
    assert provider == "anthropic"
    assert cfg.provider == "anthropic"
    assert cfg.base_url == "https://api.anthropic.com/v1"
    assert cfg.model == "claude-sonnet-4.6"


def test_sync_provider_from_model_updates_base_url_when_switching_family():
    cfg = AgentConfig(provider="openai", base_url="https://api.openai.com/v1", model="claude-opus-4.6")
    provider = _sync_provider_from_model(cfg, previous_provider="openai", previous_base_url="https://api.openai.com/v1")
    assert provider == "anthropic"
    assert cfg.provider == "anthropic"
    assert cfg.base_url == "https://api.anthropic.com/v1"


def test_normalize_reasoning_effort_rejects_unknown_value():
    with pytest.raises(ValueError):
        _normalize_reasoning_effort("turbo")

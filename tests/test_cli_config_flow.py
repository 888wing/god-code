from pathlib import Path
from unittest.mock import Mock

import pytest
from click import ClickException

from godot_agent.cli import (
    _has_usable_provider_auth,
    _load_or_setup_config,
    _persist_config_updates,
    _provider_auth_issue,
)
from godot_agent.runtime.config import AgentConfig


def test_provider_auth_issue_accepts_openai_oauth() -> None:
    assert _provider_auth_issue("openai", api_key="", oauth_token="oauth-token") is None


def test_custom_provider_can_run_without_auth() -> None:
    cfg = AgentConfig(provider="custom", base_url="http://localhost:11434/v1", model="llama3")
    assert _provider_auth_issue(cfg.provider, cfg.api_key, cfg.oauth_token) is None
    assert _has_usable_provider_auth(cfg) is True


def test_provider_auth_issue_flags_missing_non_openai_key() -> None:
    issue = _provider_auth_issue("anthropic", api_key="", oauth_token=None)
    assert issue is not None
    assert "requires an API key" in issue


def test_provider_auth_issue_flags_known_prefix_mismatch() -> None:
    issue = _provider_auth_issue("openrouter", api_key="sk-ant-test", oauth_token=None)
    assert issue is not None
    assert "expected prefix sk-or-" in issue


def test_persist_config_updates_merges_existing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _persist_config_updates(config_path, {"provider": "openai", "model": "gpt-5.4"})
    _persist_config_updates(config_path, {"api_key": "sk-test", "reasoning_effort": "high"})

    content = config_path.read_text(encoding="utf-8")
    assert '"provider": "openai"' in content
    assert '"model": "gpt-5.4"' in content
    assert '"api_key": "sk-test"' in content
    assert '"reasoning_effort": "high"' in content


def test_load_or_setup_config_runs_setup_when_interactive(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    setup = Mock()
    load_results = [
        AgentConfig(),
        AgentConfig(api_key="sk-test"),
    ]

    monkeypatch.setattr("godot_agent.cli._is_interactive_terminal", lambda: True)
    monkeypatch.setattr("godot_agent.cli._run_setup_wizard", setup)
    monkeypatch.setattr("godot_agent.cli.load_config", lambda path: load_results.pop(0))

    cfg = _load_or_setup_config(config_path)

    assert cfg.api_key == "sk-test"
    setup.assert_called_once_with(config_path)


def test_load_or_setup_config_accepts_custom_provider_without_auth(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "godot_agent.cli.load_config",
        lambda path: AgentConfig(provider="custom", base_url="http://localhost:11434/v1", model="llama3"),
    )

    cfg = _load_or_setup_config(config_path)
    assert cfg.provider == "custom"


def test_load_or_setup_config_raises_when_noninteractive(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("godot_agent.cli._is_interactive_terminal", lambda: False)
    monkeypatch.setattr("godot_agent.cli.load_config", lambda path: AgentConfig())

    with pytest.raises(ClickException, match="Not configured"):
        _load_or_setup_config(config_path)

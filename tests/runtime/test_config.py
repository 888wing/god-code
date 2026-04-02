import pytest
import json
from pathlib import Path
from godot_agent.runtime.config import AgentConfig, load_config


class TestAgentConfig:
    def test_default_values(self):
        config = AgentConfig()
        assert config.model == "gpt-5.4"
        assert config.max_turns == 20
        assert config.screenshot_max_iterations == 5

    def test_from_dict(self):
        data = {"model": "gpt-4o-mini", "max_turns": 10}
        config = AgentConfig.model_validate(data)
        assert config.model == "gpt-4o-mini"
        assert config.max_turns == 10


class TestLoadConfig:
    def test_load_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"api_key": "sk-test", "model": "gpt-4o-mini"}))
        config = load_config(config_file)
        assert config.api_key == "sk-test"
        assert config.model == "gpt-4o-mini"

    def test_load_missing_file_returns_default(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.json")
        assert config.model == "gpt-5.4"
        assert config.api_key == ""

    def test_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GODOT_AGENT_API_KEY", "sk-from-env")
        monkeypatch.setenv("GODOT_AGENT_MODEL", "claude-sonnet-4-6")
        config = load_config(tmp_path / "nonexistent.json")
        assert config.api_key == "sk-from-env"
        assert config.model == "claude-sonnet-4-6"

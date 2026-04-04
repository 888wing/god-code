import json
from godot_agent.runtime.config import AgentConfig, load_config


class TestAgentConfig:
    def test_default_values(self):
        config = AgentConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-5.4"
        assert config.reasoning_effort == "high"
        assert config.computer_use is False
        assert config.skill_mode == "auto"
        assert config.enabled_skills == []
        assert config.disabled_skills == []
        assert config.max_turns == 20
        assert config.screenshot_max_iterations == 5
        assert config.mode == "apply"
        assert config.autosave_session is True

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
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"

    def test_load_missing_file_returns_default(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.json")
        assert config.provider == "openai"
        assert config.model == "gpt-5.4"
        assert config.api_key == ""

    def test_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GODOT_AGENT_API_KEY", "sk-from-env")
        monkeypatch.setenv("GODOT_AGENT_MODEL", "claude-sonnet-4.6")
        config = load_config(tmp_path / "nonexistent.json")
        assert config.api_key == "sk-from-env"
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4.6"

    def test_env_provider_and_effort_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GODOT_AGENT_PROVIDER", "gemini")
        monkeypatch.setenv("GODOT_AGENT_REASONING_EFFORT", "medium")
        config = load_config(tmp_path / "nonexistent.json")
        assert config.provider == "gemini"
        assert config.reasoning_effort == "medium"

    def test_infer_provider_from_base_url(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_key": "test",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-3.1-pro",
        }))
        config = load_config(config_file)
        assert config.provider == "gemini"

    def test_load_skill_settings_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "skill_mode": "hybrid",
            "enabled_skills": ["collision"],
            "disabled_skills": ["physics"],
            "computer_use": True,
            "computer_use_environment": "browser",
            "computer_use_display_width": 1440,
            "computer_use_display_height": 900,
        }))
        config = load_config(config_file)
        assert config.skill_mode == "hybrid"
        assert config.enabled_skills == ["collision"]
        assert config.disabled_skills == ["physics"]
        assert config.computer_use is True
        assert config.computer_use_display_width == 1440
        assert config.computer_use_display_height == 900

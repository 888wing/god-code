# godot_agent/runtime/config.py
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.runtime.providers import infer_provider


class AgentConfig(BaseModel):
    # API
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    provider: str = "openai"
    model: str = "gpt-5.4"
    reasoning_effort: str = "high"
    oauth_token: str | None = None
    max_turns: int = 20
    max_tokens: int = 16384  # gpt-5.4 supports up to 128K output
    temperature: float = 0.0

    # Godot
    godot_path: str = "godot"
    auto_validate: bool = True
    auto_commit: bool = False
    screenshot_max_iterations: int = 5
    max_visual_iterations: int = 3

    # UX
    language: str = "en"  # en, zh-TW, ja
    verbosity: str = "normal"  # concise, normal, detailed
    mode: str = "apply"  # apply, plan, explain, review, fix
    safety: str = "normal"  # strict, normal, permissive
    token_budget: int = 0  # 0 = unlimited
    extra_prompt: str = ""  # Custom user instructions appended to system prompt
    streaming: bool = True
    autosave_session: bool = True
    computer_use: bool = False
    computer_use_environment: str = "browser"
    computer_use_display_width: int = 1024
    computer_use_display_height: int = 768
    skill_mode: str = "auto"
    enabled_skills: list[str] = Field(default_factory=list)
    disabled_skills: list[str] = Field(default_factory=list)

    # Backend orchestration
    backend_url: str = ""                    # Empty = direct provider (current behavior)
    backend_cost_preference: str = "balanced"  # economy | balanced | quality
    backend_force_provider: str = ""
    backend_force_model: str = ""
    backend_provider_keys: dict[str, str] = Field(default_factory=dict)

    # Paths
    session_dir: str = ".agent_sessions"


def load_config(path: Path | None = None, use_codex: bool = False) -> AgentConfig:
    data: dict = {}
    if path and path.exists():
        data = json.loads(path.read_text())
    config = AgentConfig.model_validate(data)
    env_map = {
        "GODOT_AGENT_API_KEY": "api_key",
        "GODOT_AGENT_BASE_URL": "base_url",
        "GODOT_AGENT_PROVIDER": "provider",
        "GODOT_AGENT_MODEL": "model",
        "GODOT_AGENT_REASONING_EFFORT": "reasoning_effort",
        "GODOT_AGENT_OAUTH_TOKEN": "oauth_token",
        "GODOT_AGENT_GODOT_PATH": "godot_path",
        "GODOT_AGENT_LANGUAGE": "language",
        "GODOT_AGENT_COMPUTER_USE": "computer_use",
        "GODOT_AGENT_COMPUTER_USE_ENVIRONMENT": "computer_use_environment",
        "GODOT_AGENT_COMPUTER_USE_WIDTH": "computer_use_display_width",
        "GODOT_AGENT_COMPUTER_USE_HEIGHT": "computer_use_display_height",
    }
    for env_key, field_name in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            current = getattr(config, field_name)
            if isinstance(current, bool):
                setattr(config, field_name, val.lower() in {"1", "true", "yes", "on"})
            elif isinstance(current, int):
                setattr(config, field_name, int(val))
            else:
                setattr(config, field_name, val)

    config.provider = infer_provider(
        base_url=config.base_url,
        model=config.model,
        provider=config.provider,
    )

    if not config.api_key and not config.oauth_token:
        from godot_agent.runtime.oauth import load_stored_token, load_codex_auth
        token = load_stored_token() or load_codex_auth()
        if token:
            config.oauth_token = token

    return config


def default_config_path() -> Path:
    return Path.home() / ".config" / "god-code" / "config.json"

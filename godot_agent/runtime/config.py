# godot_agent/runtime/config.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class AgentConfig(BaseModel):
    # API
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4"
    oauth_token: str | None = None
    max_turns: int = 20
    max_tokens: int = 4096
    temperature: float = 0.0

    # Godot
    godot_path: str = "godot"
    auto_validate: bool = True
    auto_commit: bool = False
    screenshot_max_iterations: int = 5

    # UX
    language: str = "en"  # en, zh-TW, ja
    verbosity: str = "normal"  # concise, normal, detailed
    safety: str = "normal"  # strict, normal, permissive
    token_budget: int = 0  # 0 = unlimited
    extra_prompt: str = ""  # Custom user instructions appended to system prompt
    streaming: bool = True

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
        "GODOT_AGENT_MODEL": "model",
        "GODOT_AGENT_OAUTH_TOKEN": "oauth_token",
        "GODOT_AGENT_GODOT_PATH": "godot_path",
        "GODOT_AGENT_LANGUAGE": "language",
    }
    for env_key, field_name in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            setattr(config, field_name, val)

    if not config.api_key and not config.oauth_token:
        from godot_agent.runtime.oauth import load_stored_token, load_codex_auth
        token = load_stored_token() or load_codex_auth()
        if token:
            config.oauth_token = token

    return config


def default_config_path() -> Path:
    return Path.home() / ".config" / "god-code" / "config.json"

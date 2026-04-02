from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from godot_agent.llm.types import LLMConfig, Message
from godot_agent.runtime.providers import chat_completions_url, normalize_provider


class ProviderAdapter(ABC):
    def __init__(self, provider: str):
        self.provider = normalize_provider(provider)

    def build_headers(self, config: LLMConfig) -> dict[str, str]:
        token = config.oauth_token or config.api_key
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def build_url(self, config: LLMConfig) -> str:
        return chat_completions_url(config.base_url)

    @abstractmethod
    def build_request_body(
        self,
        config: LLMConfig,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

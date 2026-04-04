from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from godot_agent.llm.types import ComputerUseResponse, LLMConfig, Message
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

    def build_responses_url(self, config: LLMConfig) -> str:
        return f"{config.base_url.rstrip('/')}/responses"

    @abstractmethod
    def build_request_body(
        self,
        config: LLMConfig,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def build_computer_use_request(
        self,
        config: LLMConfig,
        *,
        prompt: str,
        screenshot_b64: str | None = None,
        previous_response_id: str | None = None,
        call_id: str | None = None,
        detail: str = "original",
    ) -> dict[str, Any]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support computer use")

    def parse_computer_use_response(self, data: dict[str, Any]) -> ComputerUseResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support computer use")

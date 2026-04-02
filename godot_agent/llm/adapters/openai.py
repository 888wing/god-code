from __future__ import annotations

from typing import Any

from godot_agent.llm.adapters.base import ProviderAdapter
from godot_agent.llm.types import LLMConfig, Message
from godot_agent.runtime.providers import should_send_reasoning_effort, uses_max_completion_tokens


class OpenAICompatibleAdapter(ProviderAdapter):
    def build_request_body(
        self,
        config: LLMConfig,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        token_key = (
            "max_completion_tokens"
            if uses_max_completion_tokens(self.provider, config.model)
            else "max_tokens"
        )
        body: dict[str, Any] = {
            "model": config.model,
            "messages": [message.to_dict() for message in messages],
            token_key: config.max_tokens,
            "temperature": config.temperature,
        }
        if tools:
            body["tools"] = tools
        if should_send_reasoning_effort(self.provider, config.model, config.reasoning_effort):
            body["reasoning_effort"] = config.reasoning_effort
        return body

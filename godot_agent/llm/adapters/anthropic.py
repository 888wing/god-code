from __future__ import annotations

from typing import Any

from godot_agent.llm.adapters.openai import OpenAICompatibleAdapter
from godot_agent.llm.types import LLMConfig, Message
from godot_agent.runtime.providers import anthropic_thinking_budget


class AnthropicCompatibilityAdapter(OpenAICompatibleAdapter):
    def build_request_body(
        self,
        config: LLMConfig,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body = super().build_request_body(config, messages, tools)
        body.pop("reasoning_effort", None)
        budget = anthropic_thinking_budget(config.reasoning_effort)
        if budget:
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return body

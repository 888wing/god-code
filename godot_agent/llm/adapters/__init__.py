from __future__ import annotations

from godot_agent.llm.adapters.anthropic import AnthropicCompatibilityAdapter
from godot_agent.llm.adapters.base import ProviderAdapter
from godot_agent.llm.adapters.openai import OpenAICompatibleAdapter
from godot_agent.runtime.providers import normalize_provider


def get_provider_adapter(provider: str) -> ProviderAdapter:
    normalized = normalize_provider(provider)
    if normalized == "anthropic":
        return AnthropicCompatibilityAdapter(normalized)
    return OpenAICompatibleAdapter(normalized)


__all__ = [
    "AnthropicCompatibilityAdapter",
    "OpenAICompatibleAdapter",
    "ProviderAdapter",
    "get_provider_adapter",
]

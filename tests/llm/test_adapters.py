from godot_agent.llm.adapters import get_provider_adapter
from godot_agent.llm.adapters.anthropic import AnthropicCompatibilityAdapter
from godot_agent.llm.adapters.openai import OpenAICompatibleAdapter
from godot_agent.llm.types import LLMConfig, Message


def test_get_provider_adapter_returns_anthropic_adapter():
    adapter = get_provider_adapter("anthropic")
    assert isinstance(adapter, AnthropicCompatibilityAdapter)


def test_get_provider_adapter_returns_openai_compatible_for_gemini():
    adapter = get_provider_adapter("gemini")
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert not isinstance(adapter, AnthropicCompatibilityAdapter)


def test_openai_adapter_builds_chat_completions_url():
    adapter = get_provider_adapter("openai")
    url = adapter.build_url(LLMConfig(api_key="key", base_url="https://api.openai.com/v1"))
    assert url == "https://api.openai.com/v1/chat/completions"


def test_anthropic_adapter_adds_thinking_without_reasoning_effort():
    adapter = get_provider_adapter("anthropic")
    body = adapter.build_request_body(
        LLMConfig(
            api_key="key",
            provider="anthropic",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4.6",
            reasoning_effort="high",
        ),
        [Message.user("hi")],
    )
    assert body["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert "reasoning_effort" not in body

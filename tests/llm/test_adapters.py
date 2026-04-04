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


def test_openai_adapter_builds_computer_use_request():
    adapter = get_provider_adapter("openai")
    body = adapter.build_computer_use_request(
        LLMConfig(api_key="key", provider="openai", model="gpt-5.4", computer_use=True),
        prompt="Open the inventory.",
    )
    assert body["tools"][0]["type"] == "computer"
    assert body["input"] == "Open the inventory."


def test_openai_adapter_parses_computer_use_response():
    adapter = get_provider_adapter("openai")
    parsed = adapter.parse_computer_use_response({
        "id": "resp_123",
        "output": [
            {
                "type": "computer_call",
                "call_id": "call_1",
                "actions": [{"type": "click", "x": 10, "y": 20}],
                "status": "completed",
            }
        ],
    })
    assert parsed.response_id == "resp_123"
    assert parsed.computer_calls[0].call_id == "call_1"
    assert parsed.computer_calls[0].actions[0]["type"] == "click"

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from godot_agent.llm.client import LLMClient, LLMConfig, Message, ToolCall, TokenUsage


class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig(api_key="test-key")
        assert config.base_url == "https://api.openai.com/v1"
        assert config.provider == "openai"
        assert config.model == "gpt-5.4"
        assert config.computer_use is False

    def test_custom_base_url(self):
        config = LLMConfig(api_key="key", base_url="http://localhost:11434/v1")
        assert config.base_url == "http://localhost:11434/v1"

    def test_provider_inferred_from_model(self):
        config = LLMConfig(api_key="key", model="claude-sonnet-4.6")
        client = LLMClient(config)
        assert client.provider == "anthropic"


class TestMessage:
    def test_user_message(self):
        msg = Message.user("hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_user_message_with_image(self):
        msg = Message.user_with_images("describe this", ["base64data"])
        assert msg.role == "user"
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2

    def test_assistant_message_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="read_file", arguments='{"path": "/tmp/test.gd"}')
        msg = Message.assistant(tool_calls=[tc])
        assert msg.role == "assistant"
        assert len(msg.tool_calls) == 1

    def test_tool_result_message(self):
        msg = Message.tool_result(tool_call_id="call_1", content="file contents here")
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_1"

    def test_to_dict_user(self):
        msg = Message.user("hello")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "hello"}

    def test_to_dict_tool_calls(self):
        tc = ToolCall(id="c1", name="test", arguments='{}')
        msg = Message.assistant(tool_calls=[tc])
        d = msg.to_dict()
        assert d["tool_calls"][0]["function"]["name"] == "test"

    def test_to_dict_tool_result(self):
        msg = Message.tool_result(tool_call_id="c1", content="result")
        d = msg.to_dict()
        assert d["role"] == "tool"
        assert d["tool_call_id"] == "c1"

    def test_from_dict_roundtrip_with_tool_calls(self):
        tc = ToolCall(id="c1", name="read_file", arguments='{"path": "/tmp/foo.gd"}')
        msg = Message.assistant(content="Checking", tool_calls=[tc])
        parsed = Message.from_dict(msg.to_dict())
        assert parsed.role == "assistant"
        assert parsed.content == "Checking"
        assert parsed.tool_calls is not None
        assert parsed.tool_calls[0].name == "read_file"


class TestLLMClient:
    def test_build_headers_api_key(self):
        config = LLMConfig(api_key="sk-test123")
        client = LLMClient(config)
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer sk-test123"

    def test_build_headers_oauth(self):
        config = LLMConfig(api_key="", oauth_token="oauth-token-123")
        client = LLMClient(config)
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer oauth-token-123"

    def test_build_request_body(self):
        config = LLMConfig(api_key="key", model="gpt-4o-mini")
        client = LLMClient(config)
        messages = [Message.user("hello")]
        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]
        body = client._build_request_body(messages, tools)
        assert body["model"] == "gpt-4o-mini"
        assert len(body["messages"]) == 1
        assert len(body["tools"]) == 1
        assert body["max_tokens"] == 4096

    def test_build_request_body_no_tools(self):
        config = LLMConfig(api_key="key")
        client = LLMClient(config)
        body = client._build_request_body([Message.user("hi")])
        assert "tools" not in body

    def test_gpt5_uses_max_completion_tokens(self):
        client = LLMClient(LLMConfig(api_key="key", model="gpt-5.4"))
        body = client._build_request_body([Message.user("hi")])
        assert body["max_completion_tokens"] == 4096
        assert "max_tokens" not in body

    def test_gemini_sends_reasoning_effort(self):
        client = LLMClient(
            LLMConfig(
                api_key="key",
                provider="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-3.1-pro",
                reasoning_effort="medium",
            )
        )
        body = client._build_request_body([Message.user("hi")])
        assert body["reasoning_effort"] == "medium"

    def test_xai_grok4_does_not_send_reasoning_effort(self):
        client = LLMClient(
            LLMConfig(
                api_key="key",
                provider="xai",
                base_url="https://api.x.ai/v1",
                model="grok-4.20-reasoning",
                reasoning_effort="high",
            )
        )
        body = client._build_request_body([Message.user("hi")])
        assert "reasoning_effort" not in body

    def test_anthropic_uses_thinking_budget(self):
        client = LLMClient(
            LLMConfig(
                api_key="key",
                provider="anthropic",
                base_url="https://api.anthropic.com/v1",
                model="claude-sonnet-4.6",
                reasoning_effort="high",
            )
        )
        body = client._build_request_body([Message.user("hi")])
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 4096}
        assert "reasoning_effort" not in body

    def test_cost_estimate_supports_prefixed_models(self):
        usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert usage.cost_estimate("openai/gpt-5.4") == 17.5

    def test_use_backend_false_by_default(self):
        config = LLMConfig(api_key="sk-test", base_url="https://api.openai.com/v1", provider="openai", model="gpt-5.4")
        client = LLMClient(config)
        assert client._use_backend is False

    def test_use_backend_true_when_url_set(self):
        config = LLMConfig(api_key="sk-test", base_url="https://api.openai.com/v1", provider="openai", model="gpt-5.4", backend_url="https://api.god-code.dev")
        client = LLMClient(config)
        assert client._use_backend is True
        assert client._backend_url == "https://api.god-code.dev"

    def test_backend_url_trailing_slash_stripped(self):
        config = LLMConfig(api_key="sk-test", backend_url="https://api.god-code.dev/")
        client = LLMClient(config)
        assert client._backend_url == "https://api.god-code.dev"

    def test_backend_api_key_default_empty(self):
        config = LLMConfig(api_key="sk-test", backend_url="https://api.god-code.dev")
        assert config.backend_api_key == ""

    @pytest.mark.asyncio
    async def test_backend_sends_bearer_when_api_key_set(self):
        """When backend_api_key is set, _chat_via_backend sends it as Bearer token."""
        config = LLMConfig(
            api_key="sk-test",
            backend_url="https://api.god-code.dev",
            backend_api_key="gc-platform-key-789",
        )
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        client._http.post = AsyncMock(return_value=mock_response)

        resp = await client._chat_via_backend(
            [Message.user("hello")],
            None,
            {"intent": "test"},
        )
        assert resp.message.content == "OK"

        call_kwargs = client._http.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers["Authorization"] == "Bearer gc-platform-key-789"
        await client.close()

    @pytest.mark.asyncio
    async def test_backend_no_auth_header_when_api_key_empty(self):
        """When backend_api_key is empty, no Authorization header is sent."""
        config = LLMConfig(
            api_key="sk-test",
            backend_url="https://api.god-code.dev",
            backend_api_key="",
        )
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        client._http.post = AsyncMock(return_value=mock_response)

        await client._chat_via_backend(
            [Message.user("hello")],
            None,
            {"intent": "test"},
        )

        call_kwargs = client._http.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "Authorization" not in headers
        await client.close()

    @pytest.mark.asyncio
    async def test_backend_response_warnings_attached_to_chat_response(self):
        """Regression v1.0.1/D3-routing: backend OrchestrateResponse may
        include `warnings` (e.g. quality_gate_retry, cheap_routing_disabled,
        cheap_routing_blacklist_triggered). The CLI must capture them on
        ChatResponse so display.handle_event can surface them to the user.
        """
        config = LLMConfig(
            api_key="sk-test",
            backend_url="https://api.god-code.dev",
            backend_api_key="gc-platform-key",
        )
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"role": "assistant", "content": "Plan ready"}}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
            "warnings": [
                {
                    "code": "quality_gate_retry",
                    "message": "Cheap model output failed validation; retried with gpt-5.4-mini",
                    "data": {
                        "reason": "missing '## Plan' header",
                        "retried_with": "openai/gpt-5.4-mini",
                    },
                },
            ],
        }
        client._http.post = AsyncMock(return_value=mock_response)

        resp = await client._chat_via_backend(
            [Message.user("plan it")],
            None,
            {"intent": "test"},
        )

        assert resp.warnings is not None
        assert len(resp.warnings) == 1
        assert resp.warnings[0]["code"] == "quality_gate_retry"
        assert "gpt-5.4-mini" in resp.warnings[0]["message"]
        await client.close()

    @pytest.mark.asyncio
    async def test_backend_response_no_warnings_field_yields_none(self):
        """When backend doesn't include warnings (legacy backend or no
        warnings to surface), ChatResponse.warnings is None — not an
        empty list — so callers can do `if response.warnings:` cleanly.
        """
        config = LLMConfig(
            api_key="sk-test",
            backend_url="https://api.god-code.dev",
            backend_api_key="gc-platform-key",
        )
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        client._http.post = AsyncMock(return_value=mock_response)

        resp = await client._chat_via_backend(
            [Message.user("hi")],
            None,
            {"intent": "test"},
        )
        assert resp.warnings is None
        await client.close()

    def test_build_computer_use_request(self):
        client = LLMClient(
            LLMConfig(
                api_key="key",
                provider="openai",
                model="gpt-5.4",
                computer_use=True,
            )
        )
        body = client.adapter.build_computer_use_request(client.config, prompt="Click Start")
        assert body["tools"][0]["type"] == "computer"
        assert body["input"] == "Click Start"

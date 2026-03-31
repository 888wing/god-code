import pytest
from godot_agent.llm.client import LLMClient, LLMConfig, Message, ToolCall


class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig(api_key="test-key")
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o"

    def test_custom_base_url(self):
        config = LLMConfig(api_key="key", base_url="http://localhost:11434/v1")
        assert config.base_url == "http://localhost:11434/v1"


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

    def test_build_request_body_no_tools(self):
        config = LLMConfig(api_key="key")
        client = LLMClient(config)
        body = client._build_request_body([Message.user("hi")])
        assert "tools" not in body

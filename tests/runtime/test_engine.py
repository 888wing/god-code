import pytest
import json
from unittest.mock import AsyncMock
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.llm.client import Message, ToolCall, LLMClient
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.base import BaseTool, ToolResult
from pydantic import BaseModel


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    reply: str


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back"
    Input = EchoInput
    Output = EchoOutput

    async def execute(self, input):
        return ToolResult(output=EchoOutput(reply=f"echo: {input.text}"))


class TestConversationEngine:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=Message.assistant(content="Hello!"))
        registry = ToolRegistry()
        engine = ConversationEngine(
            client=mock_client, registry=registry, system_prompt="You are helpful."
        )
        response = await engine.submit("Hi")
        assert response == "Hello!"
        assert len(engine.messages) == 3  # system + user + assistant

    @pytest.mark.asyncio
    async def test_tool_call_and_response(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = Message.assistant(
            tool_calls=[
                ToolCall(id="call_1", name="echo", arguments='{"text": "test"}')
            ]
        )
        final_msg = Message.assistant(content="The echo said: echo: test")
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[call_msg, final_msg])
        engine = ConversationEngine(
            client=mock_client, registry=registry, system_prompt="test"
        )
        response = await engine.submit("Echo something")
        assert "echo: test" in response
        # system + user + assistant(tool) + tool_result + assistant(final)
        assert len(engine.messages) == 5

    @pytest.mark.asyncio
    async def test_max_turns_limit(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = Message.assistant(
            tool_calls=[
                ToolCall(id="call_1", name="echo", arguments='{"text": "loop"}')
            ]
        )
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=call_msg)
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt="test",
            max_tool_rounds=3,
        )
        response = await engine.submit("Loop forever")
        # Should stop after max_tool_rounds + 1 iterations
        assert mock_client.chat.call_count == 4

    @pytest.mark.asyncio
    async def test_tool_error_forwarded(self):
        """Tool execution errors are serialised as JSON error messages."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        # Malformed arguments will cause Input validation to fail
        call_msg = Message.assistant(
            tool_calls=[
                ToolCall(id="call_err", name="echo", arguments='{"bad_key": 1}')
            ]
        )
        final_msg = Message.assistant(content="Got an error from the tool.")
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[call_msg, final_msg])
        engine = ConversationEngine(
            client=mock_client, registry=registry, system_prompt="test"
        )
        response = await engine.submit("Break the tool")
        assert response == "Got an error from the tool."
        # Verify the tool_result message contains an error key
        tool_result_msg = engine.messages[3]
        assert tool_result_msg.role == "tool"
        parsed = json.loads(tool_result_msg.content)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_submit_with_images(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(
            return_value=Message.assistant(content="I see an image.")
        )
        registry = ToolRegistry()
        engine = ConversationEngine(
            client=mock_client, registry=registry, system_prompt="Vision agent."
        )
        response = await engine.submit_with_images("What is this?", ["base64data"])
        assert response == "I see an image."
        assert len(engine.messages) == 3
        # The user message should contain image content blocks
        user_msg = engine.messages[1]
        assert isinstance(user_msg.content, list)

    @pytest.mark.asyncio
    async def test_empty_registry_passes_no_tools(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(
            return_value=Message.assistant(content="No tools here.")
        )
        registry = ToolRegistry()
        engine = ConversationEngine(
            client=mock_client, registry=registry, system_prompt="test"
        )
        await engine.submit("Hello")
        # When registry is empty, tools param should be None
        call_args = mock_client.chat.call_args
        assert call_args[0][1] is None or call_args[1].get("tools") is None

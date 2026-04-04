import pytest
import json
from unittest.mock import AsyncMock
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.llm.client import Message, ToolCall, LLMClient, ChatResponse, TokenUsage
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.base import BaseTool, ToolResult
from pydantic import BaseModel


def _resp(msg: Message) -> ChatResponse:
    """Wrap a Message in a ChatResponse with dummy usage."""
    return ChatResponse(message=msg, usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15))


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


class NoopInput(BaseModel):
    pass


class NoopOutput(BaseModel):
    ok: bool = True


class NamedTool(BaseTool):
    description = "Named tool for schema filtering tests"
    Input = NoopInput
    Output = NoopOutput

    def __init__(self, name: str):
        self.name = name

    async def execute(self, input):
        return ToolResult(output=NoopOutput())


class TestConversationEngine:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="Hello!")))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="You are helpful.")
        response = await engine.submit("Hi")
        assert response == "Hello!"
        assert len(engine.messages) == 3

    @pytest.mark.asyncio
    async def test_tool_call_and_response(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = _resp(Message.assistant(tool_calls=[ToolCall(id="call_1", name="echo", arguments='{"text": "test"}')]))
        final_msg = _resp(Message.assistant(content="The echo said: echo: test"))
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[call_msg, final_msg])
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        response = await engine.submit("Echo something")
        assert "echo: test" in response
        assert len(engine.messages) == 5

    @pytest.mark.asyncio
    async def test_max_turns_limit(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = _resp(Message.assistant(tool_calls=[ToolCall(id="call_1", name="echo", arguments='{"text": "loop"}')]))
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=call_msg)
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test", max_tool_rounds=3)
        response = await engine.submit("Loop forever")
        assert mock_client.chat.call_count == 4

    @pytest.mark.asyncio
    async def test_tool_error_forwarded(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = _resp(Message.assistant(tool_calls=[ToolCall(id="call_err", name="echo", arguments='{"bad_key": 1}')]))
        final_msg = _resp(Message.assistant(content="Got an error from the tool."))
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[call_msg, final_msg])
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        response = await engine.submit("Break the tool")
        assert response == "Got an error from the tool."
        tool_result_msg = engine.messages[3]
        assert tool_result_msg.role == "tool"
        parsed = json.loads(tool_result_msg.content)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_submit_with_images(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="I see an image.")))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="Vision agent.")
        response = await engine.submit_with_images("What is this?", ["base64data"])
        assert response == "I see an image."
        assert len(engine.messages) == 3
        assert isinstance(engine.messages[1].content, list)

    @pytest.mark.asyncio
    async def test_empty_registry_passes_no_tools(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="No tools.")))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        await engine.submit("Hello")
        call_args = mock_client.chat.call_args
        assert call_args[0][1] is None or call_args[1].get("tools") is None

    @pytest.mark.asyncio
    async def test_usage_tracking(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=ChatResponse(
            message=Message.assistant(content="Done"),
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        ))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        await engine.submit("Test")
        assert engine.session_usage.total_tokens == 150
        assert engine.last_turn is not None
        assert engine.last_turn.usage.total_tokens == 150
        assert engine.session_api_calls == 1

    @pytest.mark.asyncio
    async def test_allowed_tools_filter(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="No tools.")))
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        engine.allowed_tools = set()
        await engine.submit("Hello")
        call_args = mock_client.chat.call_args
        assert call_args[0][1] is None or call_args[1].get("tools") is None

    @pytest.mark.asyncio
    async def test_collision_prompt_narrows_tools_before_model_call(self, tmp_path):
        (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="SkillTest"\n')
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="Done")))
        registry = ToolRegistry()
        for name in ("read_scene", "write_scene_property", "edit_script", "run_shell"):
            registry.register(NamedTool(name))
        prompt_assembler = PromptAssembler(PromptContext(project_root=tmp_path, mode="apply"))
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt=prompt_assembler.build(),
            project_path=str(tmp_path),
            prompt_assembler=prompt_assembler,
            auto_validate=False,
            mode="apply",
        )
        engine.base_allowed_tools = {"read_scene", "write_scene_property", "edit_script", "run_shell"}
        engine.allowed_tools = set(engine.base_allowed_tools)

        await engine.submit("Fix collision masks for enemy bullets")

        tool_schemas = mock_client.chat.call_args.args[1]
        tool_names = {schema["function"]["name"] for schema in tool_schemas}
        assert "read_scene" in tool_names
        assert "write_scene_property" in tool_names
        assert "edit_script" in tool_names
        assert "run_shell" not in tool_names

    @pytest.mark.asyncio
    async def test_emits_runtime_events_for_tool_turn(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        call_msg = _resp(Message.assistant(tool_calls=[ToolCall(id="call_1", name="echo", arguments='{"text": "test"}')]))
        final_msg = _resp(Message.assistant(content="The echo said: echo: test"))
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[call_msg, final_msg])
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        events = []
        engine.on_event = events.append

        await engine.submit("Echo something")

        kinds = [event.kind for event in events]
        assert "turn_started" in kinds
        assert "tool_started" in kinds
        assert "tool_finished" in kinds
        assert "turn_finished" in kinds

    @pytest.mark.asyncio
    async def test_blank_input_does_not_call_model(self):
        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        response = await engine.submit("\x7f")

        assert response == ""
        mock_client.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_metadata_passed_to_chat(self):
        """Engine builds route_metadata and passes it to client.chat()."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="Done")))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test", mode="apply")
        await engine.submit("Hello")
        call_kwargs = mock_client.chat.call_args
        # route_metadata should be passed as keyword arg
        metadata = call_kwargs.kwargs.get("route_metadata")
        assert metadata is not None
        assert metadata["mode"] == "apply"
        assert metadata["round_number"] == 1
        assert metadata["agent_role"] == "worker"
        assert metadata["changeset_size"] == 0

    @pytest.mark.asyncio
    async def test_manual_skill_override_narrows_tools_without_keyword_match(self, tmp_path):
        (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="SkillOverride"\n')
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="Done")))
        registry = ToolRegistry()
        for name in ("read_scene", "write_scene_property", "edit_script", "run_shell"):
            registry.register(NamedTool(name))
        prompt_assembler = PromptAssembler(PromptContext(project_root=tmp_path, mode="apply"))
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt=prompt_assembler.build(),
            project_path=str(tmp_path),
            prompt_assembler=prompt_assembler,
            auto_validate=False,
            mode="apply",
        )
        engine.base_allowed_tools = {"read_scene", "write_scene_property", "edit_script", "run_shell"}
        engine.allowed_tools = set(engine.base_allowed_tools)
        engine.skill_mode = "manual"
        engine.enabled_skills = ["collision"]

        await engine.submit("Inspect the player scene")

        tool_schemas = mock_client.chat.call_args.args[1]
        tool_names = {schema["function"]["name"] for schema in tool_schemas}
        assert "read_scene" in tool_names
        assert "write_scene_property" in tool_names
        assert "run_shell" not in tool_names

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
    async def test_rollback_current_turn_drops_appended_messages(self):
        """Regression v1.0.0/C2: rollback_current_turn must remove every
        message appended since the most recent submit() began, so a
        cancelled turn doesn't pollute the next turn's context.
        """
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="reply")))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="t")
        baseline = len(engine.messages)
        await engine.submit("hello")
        # submit() appended a user message + assistant reply
        assert len(engine.messages) > baseline
        # Simulate cancellation: pretend submit failed mid-way
        engine._turn_start_message_count = baseline
        removed = engine.rollback_current_turn()
        assert removed > 0
        assert len(engine.messages) == baseline

    def test_rollback_current_turn_is_idempotent_when_no_active_turn(self):
        """rollback_current_turn called outside an active turn should
        be a no-op (no exception, returns 0)."""
        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="t")
        # No submit() called yet — _turn_start_message_count is None
        removed = engine.rollback_current_turn()
        assert removed == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_content", ["", "   ", "\n\n\t", None])
    async def test_empty_assistant_response_does_not_crash(self, empty_content):
        """Regression: planner/assistant returning empty or whitespace-only content
        with no tool_calls must not raise IndexError on assistant_preview extraction.

        Previously engine._run_loop did `(content or "").strip().splitlines()[0][:120]`
        which crashed when splitlines() produced an empty list, aborting the turn
        mid-planner-pass.
        """
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content=empty_content)))
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")
        # Must not raise IndexError
        await engine.submit("Hi")
        # Preview degrades gracefully to empty string instead of crashing
        assert engine.last_turn is not None
        assert engine.last_turn.assistant_preview == ""

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


def test_loop_phase_includes_visual_iteration():
    from godot_agent.runtime.engine import LoopPhase
    assert hasattr(LoopPhase, "RUN_VISUAL_ITERATION")


def test_visual_iteration_config_defaults():
    """max_visual_iterations defaults to 3."""
    from godot_agent.runtime.config import AgentConfig
    cfg = AgentConfig()
    assert cfg.max_visual_iterations == 3


def test_vision_tools_not_in_apply_mode():
    """Vision tools removed from apply mode until vision model wiring is done."""
    from godot_agent.runtime.modes import allowed_tools_for_mode
    tools = allowed_tools_for_mode("apply")
    assert "analyze_screenshot" not in tools
    assert "score_screenshot" not in tools


def test_vision_tools_not_in_fix_mode():
    """Vision tools removed from fix mode until vision model wiring is done."""
    from godot_agent.runtime.modes import allowed_tools_for_mode
    tools = allowed_tools_for_mode("fix")
    assert "analyze_screenshot" not in tools
    assert "score_screenshot" not in tools


def test_generate_sprite_and_web_search_in_apply_mode():
    """generate_sprite and web_search are in the apply mode allowlist."""
    from godot_agent.runtime.modes import allowed_tools_for_mode
    tools = allowed_tools_for_mode("apply")
    assert "generate_sprite" in tools
    assert "web_search" in tools


def test_generate_sprite_and_web_search_in_fix_mode():
    """generate_sprite and web_search are in the fix mode allowlist."""
    from godot_agent.runtime.modes import allowed_tools_for_mode
    tools = allowed_tools_for_mode("fix")
    assert "generate_sprite" in tools
    assert "web_search" in tools


def test_vision_tools_in_registry():
    """Vision tools are registered in the tool registry."""
    from godot_agent.cli.engine_wiring import build_registry
    registry = build_registry()
    tool_names = {t.name for t in registry.list_tools()}
    assert "analyze_screenshot" in tool_names
    assert "score_screenshot" in tool_names


def test_engine_has_try_live_bridge():
    from godot_agent.runtime.engine import ConversationEngine
    assert hasattr(ConversationEngine, "_try_live_bridge")


class TestTryLiveBridge:
    @pytest.mark.asyncio
    async def test_try_live_bridge_updates_snapshot_on_success(self):
        """When Godot is reachable, _try_live_bridge updates the global snapshot."""
        from unittest.mock import patch, AsyncMock as AM
        from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, get_runtime_snapshot, clear_runtime_snapshot

        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        fake_snapshot = RuntimeSnapshot(
            source="live_editor",
            evidence_level="high",
            bridge_connected=True,
            captured_at="2026-01-01T00:00:00Z",
            nodes=[],
        )

        with patch("godot_agent.runtime.engine.LiveRuntimeClient") as MockLRC:
            mock_instance = AM()
            mock_instance.connect = AM(return_value=True)
            mock_instance.build_snapshot = AM(return_value=fake_snapshot)
            mock_instance.disconnect = AM()
            MockLRC.return_value = mock_instance

            await engine._try_live_bridge()

            mock_instance.connect.assert_awaited_once()
            mock_instance.build_snapshot.assert_awaited_once()
            mock_instance.disconnect.assert_awaited_once()

        snap = get_runtime_snapshot()
        assert snap is not None
        assert snap.bridge_connected is True
        assert snap.source == "live_editor"
        clear_runtime_snapshot()

    @pytest.mark.asyncio
    async def test_try_live_bridge_silent_on_failure(self):
        """When Godot is unreachable, _try_live_bridge silently continues."""
        from unittest.mock import patch, AsyncMock as AM
        from godot_agent.runtime.runtime_bridge import get_runtime_snapshot, clear_runtime_snapshot

        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        with patch("godot_agent.runtime.engine.LiveRuntimeClient") as MockLRC:
            mock_instance = AM()
            mock_instance.connect = AM(return_value=False)
            MockLRC.return_value = mock_instance

            # Should not raise
            await engine._try_live_bridge()

            mock_instance.connect.assert_awaited_once()
            mock_instance.build_snapshot.assert_not_awaited()

        clear_runtime_snapshot()

    @pytest.mark.asyncio
    async def test_try_live_bridge_silent_on_exception(self):
        """Even if the bridge throws, the engine never crashes."""
        from unittest.mock import patch, AsyncMock as AM
        from godot_agent.runtime.runtime_bridge import clear_runtime_snapshot

        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        with patch("godot_agent.runtime.engine.LiveRuntimeClient") as MockLRC:
            mock_instance = AM()
            mock_instance.connect = AM(side_effect=OSError("boom"))
            MockLRC.return_value = mock_instance

            # Should not raise
            await engine._try_live_bridge()

        clear_runtime_snapshot()

    @pytest.mark.asyncio
    async def test_try_live_bridge_reuses_client(self):
        """Subsequent calls reuse the same LiveRuntimeClient instance."""
        from unittest.mock import patch, AsyncMock as AM
        from godot_agent.runtime.runtime_bridge import clear_runtime_snapshot

        mock_client = AsyncMock(spec=LLMClient)
        registry = ToolRegistry()
        engine = ConversationEngine(client=mock_client, registry=registry, system_prompt="test")

        with patch("godot_agent.runtime.engine.LiveRuntimeClient") as MockLRC:
            mock_instance = AM()
            mock_instance.connect = AM(return_value=False)
            MockLRC.return_value = mock_instance

            await engine._try_live_bridge()
            await engine._try_live_bridge()

            # Constructor called once, connect called twice
            assert MockLRC.call_count == 1
            assert mock_instance.connect.await_count == 2

        clear_runtime_snapshot()


def test_engine_has_current_plan():
    assert hasattr(ConversationEngine, '_run_auto_step')


def test_engine_current_plan_init():
    """Verify current_plan is initialized as None."""
    from pathlib import Path
    from godot_agent.prompts.assembler import PromptAssembler, PromptContext
    mock_client = AsyncMock(spec=LLMClient)
    registry = ToolRegistry()
    engine = ConversationEngine(
        client=mock_client,
        registry=registry,
        system_prompt="test",
    )
    assert engine.current_plan is None


def test_engine_has_check_health():
    assert hasattr(ConversationEngine, '_check_auto_health')


class TestSubprocessRegistry:
    """Regression v1.0.1/D2: subprocess registry lets the engine terminate
    any tool-spawned subprocess (godot validate, screenshot capture,
    etc.) on Ctrl+C instead of leaving it running until natural
    completion, wasting wall clock and API quota.
    """

    def _make_engine(self):
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="done")))
        return ConversationEngine(
            client=mock_client,
            registry=ToolRegistry(),
            system_prompt="t",
        )

    def test_engine_has_empty_subprocess_registry_initially(self):
        engine = self._make_engine()
        assert hasattr(engine, "_active_subprocesses")
        assert len(engine._active_subprocesses) == 0

    def test_register_and_unregister_subprocess(self):
        """Registration adds the process to the active set; unregister
        removes it. Idempotent: unregistering an already-removed process
        is a no-op."""
        engine = self._make_engine()

        class FakeProc:
            def __init__(self):
                self.returncode = None
                self.terminated = False
                self.killed = False

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.killed = True
                self.returncode = -9

            async def wait(self):
                return self.returncode

        proc = FakeProc()
        engine.register_subprocess(proc)
        assert proc in engine._active_subprocesses

        engine.unregister_subprocess(proc)
        assert proc not in engine._active_subprocesses

        # Idempotent
        engine.unregister_subprocess(proc)

    @pytest.mark.asyncio
    async def test_terminate_active_subprocesses_kills_running_procs(self):
        """terminate_active_subprocesses calls .terminate() on every
        registered process that's still running, waits up to timeout,
        then clears the registry."""
        engine = self._make_engine()

        class FakeProc:
            def __init__(self, name):
                self.name = name
                self.returncode = None
                self.terminated = False

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.returncode = -9

            async def wait(self):
                return self.returncode

        proc1 = FakeProc("godot1")
        proc2 = FakeProc("screenshot1")
        engine.register_subprocess(proc1)
        engine.register_subprocess(proc2)

        killed = await engine.terminate_active_subprocesses()
        assert killed == 2
        assert proc1.terminated is True
        assert proc2.terminated is True
        assert len(engine._active_subprocesses) == 0

    @pytest.mark.asyncio
    async def test_terminate_skips_already_finished_procs(self):
        """A subprocess that has already finished (returncode set) must
        not be terminated — it's already done."""
        engine = self._make_engine()

        class FakeProc:
            def __init__(self):
                self.returncode = 0  # already done
                self.terminated = False

            def terminate(self):
                self.terminated = True

            async def wait(self):
                return self.returncode

        proc = FakeProc()
        engine.register_subprocess(proc)

        killed = await engine.terminate_active_subprocesses()
        assert killed == 0
        assert proc.terminated is False

    @pytest.mark.asyncio
    async def test_terminate_kills_stubborn_procs_after_timeout(self):
        """If a subprocess doesn't respond to terminate() within timeout,
        the engine escalates to kill()."""
        engine = self._make_engine()

        class StubbornProc:
            def __init__(self):
                self.returncode = None
                self.terminate_called = False
                self.kill_called = False

            def terminate(self):
                self.terminate_called = True
                # doesn't actually set returncode — subprocess is ignoring SIGTERM

            def kill(self):
                self.kill_called = True
                self.returncode = -9

            async def wait(self):
                if self.returncode is not None:
                    return self.returncode
                # Simulate a subprocess that never exits on terminate — raises
                # asyncio.TimeoutError when wrapped in wait_for.
                import asyncio
                await asyncio.sleep(10)  # longer than the engine's timeout
                return self.returncode

        proc = StubbornProc()
        engine.register_subprocess(proc)

        killed = await engine.terminate_active_subprocesses(timeout=0.1)
        assert killed == 1
        assert proc.terminate_called is True
        assert proc.kill_called is True

    def test_subprocess_registry_accessible_via_contextvar(self):
        """Tools should be able to access the active engine's subprocess
        registry via a context variable, so they can register subprocesses
        without the engine being explicitly threaded through every call."""
        from godot_agent.runtime.engine import get_current_subprocess_registry
        engine = self._make_engine()

        # Outside the activation scope, registry is None
        assert get_current_subprocess_registry() is None

        # Inside, the current engine is accessible
        token = engine._activate_subprocess_registry()
        try:
            assert get_current_subprocess_registry() is engine
        finally:
            engine._deactivate_subprocess_registry(token)

        # After deactivation, registry is None again
        assert get_current_subprocess_registry() is None

    @pytest.mark.asyncio
    async def test_registry_active_during_submit(self):
        """During engine.submit(), the engine is the current registry.
        After submit returns, registry is cleared back to None."""
        from godot_agent.runtime.engine import get_current_subprocess_registry
        engine = self._make_engine()

        # Spy: check registry state during submit via a tool that captures it
        registry_seen = {"value": None}

        class SpyInput(BaseModel):
            pass

        class SpyOutput(BaseModel):
            ok: bool = True

        class SpyTool(BaseTool):
            name = "spy"
            description = "capture the registry"
            Input = SpyInput
            Output = SpyOutput

            async def execute(self, input):
                registry_seen["value"] = get_current_subprocess_registry()
                return ToolResult(output=SpyOutput())

        engine.registry.register(SpyTool())
        engine.client.chat = AsyncMock(
            side_effect=[
                _resp(Message.assistant(
                    tool_calls=[ToolCall(id="1", name="spy", arguments="{}")]
                )),
                _resp(Message.assistant(content="done")),
            ]
        )
        await engine.submit("check registry")

        assert registry_seen["value"] is engine, (
            "tool should see the engine as the active subprocess registry"
        )
        assert get_current_subprocess_registry() is None, (
            "registry should be cleared after submit returns"
        )


class TestLazyPlannerTriggering:
    """Regression v1.0.1/T2: planner must not run on trivial read-only
    requests. Skipping those turns saves the full planner cost (LLM call +
    impact report + plan injection + rebill) on inputs that gain nothing
    from a plan pass.
    """

    @pytest.mark.parametrize(
        "user_input,expected_run",
        [
            # Action verbs → run planner
            ("implement combat logger in res://src/combat/logger.gd", True),
            ("add HP bar to player scene", True),
            ("fix the null reference in enemy.gd", True),
            ("refactor the movement code", True),
            ("rewrite the AI using behavior trees", True),
            ("create a new enemy type with ranged attack", True),
            # 繁中 action verbs
            ("實作攻擊系統 in boss.gd", True),
            ("修 player.gd 的碰撞 bug", True),
            ("新增一個 HUD scene", True),
            ("改 enemy 的血量顯示", True),
            ("重寫 combat loop", True),
            # Read-only / explain → skip planner
            ("what is in player.gd?", False),
            ("explain the combat loop", False),
            ("show me the scene tree", False),
            ("how does the spawner work?", False),
            ("list all scripts in res://src", False),
            ("describe the movement logic", False),
            # 繁中 read-only
            ("player.gd 裡面有什麼?", False),
            ("解釋一下 combat loop", False),
            ("顯示 scene tree", False),
            ("如何實作碰撞?", False),
            # Ambiguous / default-run (safe direction)
            ("make sure the boss scene works correctly with the new layer scheme", True),
            ("the animation is broken, need to check what's wrong and update it", True),
        ],
    )
    def test_should_run_planner_heuristic(self, user_input: str, expected_run: bool):
        from godot_agent.runtime.engine import should_run_planner
        run, reason = should_run_planner(user_input)
        assert run == expected_run, (
            f"input: {user_input!r} expected run={expected_run}, got run={run} reason={reason!r}"
        )

    @pytest.mark.asyncio
    async def test_planner_skipped_emits_event_for_trivial_input(self):
        """When the heuristic returns False, planner is not called and a
        planner_skipped event fires with the reason."""
        from godot_agent.agents.results import AgentTaskResult

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="done")))
        registry = ToolRegistry()

        class MockDispatcher:
            def __init__(self):
                self.called = False

            async def run_planner(self, task):
                self.called = True
                return AgentTaskResult(role="planner", content="plan")

        dispatcher = MockDispatcher()
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt="t",
            mode="apply",
            dispatcher=dispatcher,
        )
        events_seen: list[tuple[str, dict]] = []
        engine.on_event = lambda e: events_seen.append((e.kind, e.data))

        await engine._maybe_run_planner("what is in player.gd?")

        assert dispatcher.called is False, "planner must not run on trivial input"
        skipped_events = [e for e in events_seen if e[0] == "planner_skipped"]
        assert len(skipped_events) == 1
        # Event carries a reason for dogfood observability
        assert "reason" in skipped_events[0][1]

    @pytest.mark.asyncio
    async def test_planner_lazy_false_preserves_v1_0_0_behavior(self):
        """Setting planner_lazy=False on the engine restores unconditional
        planner runs (the v1.0.0 behavior) for users who opt out."""
        from godot_agent.agents.results import AgentTaskResult

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="done")))
        registry = ToolRegistry()

        class MockDispatcher:
            def __init__(self):
                self.called = False

            async def run_planner(self, task):
                self.called = True
                return AgentTaskResult(role="planner", content="plan")

        dispatcher = MockDispatcher()
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt="t",
            mode="apply",
            dispatcher=dispatcher,
        )
        engine.planner_lazy = False  # opt-out

        await engine._maybe_run_planner("what is in player.gd?")
        # With lazy disabled, the planner runs even for read-only inputs
        assert dispatcher.called is True


class TestPlannerHistoryPruning:
    """Regression v1.0.1/T1: planner blocks must be pruned from history so
    they don't accumulate across every apply/fix turn and inflate every
    subsequent LLM call's input token count via rebill.
    """

    def _make_engine_with_mock_dispatcher(self, plan_contents: list[str]) -> tuple:
        """Build an engine with a mocked dispatcher that returns the given
        plan strings one after another."""
        from godot_agent.agents.results import AgentTaskResult

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(return_value=_resp(Message.assistant(content="done")))
        registry = ToolRegistry()

        class MockDispatcher:
            def __init__(self, plans):
                self.plans = list(plans)
                self.calls = 0

            async def run_planner(self, task):
                plan = self.plans[self.calls] if self.calls < len(self.plans) else "fallback plan"
                self.calls += 1
                return AgentTaskResult(role="planner", content=plan)

        dispatcher = MockDispatcher(plan_contents)
        engine = ConversationEngine(
            client=mock_client,
            registry=registry,
            system_prompt="t",
            mode="apply",
            dispatcher=dispatcher,
        )
        return engine, dispatcher

    @pytest.mark.asyncio
    async def test_planner_block_pruned_after_third_run(self):
        """After 3 planner runs, only the latest 2 plan blocks should
        remain in engine.messages (plan_history_keep=2)."""
        plans = [
            "## Plan\n**Goal**: first\n**Steps**: 1. do A",
            "## Plan\n**Goal**: second\n**Steps**: 1. do B",
            "## Plan\n**Goal**: third\n**Steps**: 1. do C",
        ]
        engine, dispatcher = self._make_engine_with_mock_dispatcher(plans)

        await engine._maybe_run_planner("task 1")
        await engine._maybe_run_planner("task 2")
        await engine._maybe_run_planner("task 3")

        planner_blocks = [
            m for m in engine.messages
            if isinstance(m.content, str) and "[SYSTEM] Planner pass" in m.content
        ]
        assert len(planner_blocks) == 2, (
            f"expected 2 blocks after pruning, got {len(planner_blocks)}: "
            f"{[m.content[:80] for m in planner_blocks]}"
        )
        # The oldest plan ("first") should be gone; second and third remain
        contents = " ".join(m.content for m in planner_blocks if isinstance(m.content, str))
        assert "first" not in contents
        assert "second" in contents
        assert "third" in contents

    @pytest.mark.asyncio
    async def test_planner_prune_does_not_touch_quality_gate_reports(self):
        """Regression T1 safety: pruning planner blocks must not remove
        adjacent [SYSTEM] Quality gate or Reviewer reports."""
        plans = [
            "## Plan\n**Goal**: first\n**Steps**: 1. do A",
            "## Plan\n**Goal**: second\n**Steps**: 1. do B",
            "## Plan\n**Goal**: third\n**Steps**: 1. do C",
        ]
        engine, _ = self._make_engine_with_mock_dispatcher(plans)

        await engine._maybe_run_planner("task 1")
        # Inject a quality gate report between planner runs (simulates the
        # normal engine flow where the quality gate report follows an
        # apply-mode turn)
        engine.messages.append(
            Message.user("[SYSTEM] Quality gate: passed after task 1")
        )
        await engine._maybe_run_planner("task 2")
        engine.messages.append(
            Message.user("[SYSTEM] Reviewer: PASS for task 2")
        )
        await engine._maybe_run_planner("task 3")

        quality_gate_msgs = [
            m for m in engine.messages
            if isinstance(m.content, str) and "Quality gate" in m.content
        ]
        reviewer_msgs = [
            m for m in engine.messages
            if isinstance(m.content, str) and "Reviewer" in m.content
        ]
        # Both non-planner [SYSTEM] reports must still be present
        assert len(quality_gate_msgs) == 1
        assert len(reviewer_msgs) == 1

    @pytest.mark.asyncio
    async def test_planner_prune_emits_plan_pruned_event(self):
        """Regression T1: plan_pruned event fires with the drop count so
        dogfood can verify savings."""
        plans = ["plan A", "plan B", "plan C"]
        engine, _ = self._make_engine_with_mock_dispatcher(plans)
        events_seen: list[str] = []
        engine.on_event = lambda event: events_seen.append(event.kind)

        await engine._maybe_run_planner("t1")
        await engine._maybe_run_planner("t2")
        # After the third call a prune must happen (3 blocks → keep 2)
        await engine._maybe_run_planner("t3")

        assert "plan_pruned" in events_seen, (
            f"expected plan_pruned event, saw: {events_seen}"
        )

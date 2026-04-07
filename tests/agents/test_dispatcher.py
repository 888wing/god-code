from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.agents.configs import AGENT_CONFIGS
from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.llm.client import ChatResponse, LLMClient, Message, TokenUsage
from godot_agent.prompts.assembler import PromptContext
from godot_agent.tools.file_ops import ReadFileTool
from godot_agent.tools.registry import ToolRegistry


def _resp(content: str) -> ChatResponse:
    return ChatResponse(message=Message.assistant(content=content), usage=TokenUsage())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    return tmp_path


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    return registry


class TestAgentDispatcher:
    @pytest.mark.asyncio
    async def test_planner_runs_with_role_scoped_engine(self, project_root: Path) -> None:
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(return_value=_resp("Plan: inspect scripts, patch one file, validate."))
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )

        result = await dispatcher.run_planner("Fix the player controller")

        assert result.role == "planner"
        assert "Plan:" in result.content
        assert dispatcher.resolve_allowed_tools("planner") == {"read_file"}

    @pytest.mark.asyncio
    async def test_worker_inherits_apply_tooling(self, project_root: Path) -> None:
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(return_value=_resp("Implemented the requested fix."))
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )

        result = await dispatcher.run_worker("Create a save file loader", plan="1. Inspect project\n2. Add loader")

        assert result.role == "worker"
        assert result.verdict == "PASS"
        assert "Implemented" in result.content
        assert dispatcher.resolve_allowed_tools("worker") == {"read_file", "write_file"}

    def test_sub_engine_defaults_without_stream_wiring(self, project_root: Path) -> None:
        """A dispatcher with no stream wiring produces sub-engines with streaming off.

        Documents the baseline so the next test clearly shows the new wiring propagates.
        """
        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )
        sub_engine = dispatcher._build_engine(AGENT_CONFIGS["planner"], user_hint="anything")
        assert sub_engine.use_streaming is False
        assert sub_engine.on_stream_start is None
        assert sub_engine.on_stream_chunk is None
        assert sub_engine.on_stream_end is None
        assert sub_engine.on_event is None

    def test_sub_engine_inherits_stream_wiring_from_dispatcher(self, project_root: Path) -> None:
        """Regression: when the dispatcher has stream callbacks set (by the CLI),
        sub-engines created for planner/worker/reviewer passes MUST inherit them,
        so the planner pass streams text to the TUI instead of blocking silently.

        Before v0.9.2, dispatcher._build_engine created fresh engines without ever
        wiring on_stream_*, leaving the user with a stuck spinner during planner
        passes (especially painful with reasoning_effort=high on gpt-5.4, where
        the planner call could take 60-120s with zero visible feedback).
        """
        stream_starts: list[int] = []
        stream_chunks: list[str] = []
        stream_ends: list[bool] = []
        events_seen: list[str] = []

        def on_start() -> None:
            stream_starts.append(1)

        def on_chunk(text: str) -> None:
            stream_chunks.append(text)

        def on_end(finalize: bool) -> None:
            stream_ends.append(finalize)

        def on_event(event) -> None:
            events_seen.append(event.kind)

        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )
        dispatcher.use_streaming = True
        dispatcher.on_stream_start = on_start
        dispatcher.on_stream_chunk = on_chunk
        dispatcher.on_stream_end = on_end
        dispatcher.on_event = on_event

        sub_engine = dispatcher._build_engine(AGENT_CONFIGS["planner"], user_hint="anything")
        assert sub_engine.use_streaming is True
        assert sub_engine.on_stream_start is on_start
        assert sub_engine.on_stream_chunk is on_chunk
        assert sub_engine.on_stream_end is on_end
        assert sub_engine.on_event is on_event

    @pytest.mark.asyncio
    async def test_reviewer_wraps_deterministic_review(self, project_root: Path, monkeypatch) -> None:
        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
        )

        async def fake_review_changes(*, project_root, changed_files, godot_path, quality_report, runtime_snapshot=None):
            from godot_agent.runtime.reviewer import ReviewCheck, ReviewReport

            return ReviewReport(
                checks=[
                    ReviewCheck(
                        description="Run validation",
                        command=f"{godot_path} --headless --quit",
                        observed_output="No issues found.",
                        status="PASS",
                    )
                ]
            )

        monkeypatch.setattr("godot_agent.agents.dispatcher.review_changes", fake_review_changes)

        result = await dispatcher.run_reviewer(changed_files={str(project_root / "player.gd")})

        assert result.role == "reviewer"
        assert result.verdict == "PASS"
        assert "Run validation" in result.content

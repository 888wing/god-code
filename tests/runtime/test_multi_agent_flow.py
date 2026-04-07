import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.agents.results import AgentTaskResult
from godot_agent.llm.client import ChatResponse, LLMClient, Message, ToolCall, TokenUsage
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.reviewer import ReviewCheck, ReviewReport
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool, clear_project_root, set_project_root
from godot_agent.tools.registry import ToolRegistry


def _resp(msg: Message) -> ChatResponse:
    return ChatResponse(message=msg, usage=TokenUsage())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    (tmp_path / "player.gd").write_text("extends Node\nvar speed: int = 100\n")
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    return registry


class TestMultiAgentFlow:
    @pytest.mark.asyncio
    async def test_engine_runs_planner_before_worker(self, project_root: Path) -> None:
        registry = _make_registry()
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(
            side_effect=[
                _resp(Message.assistant(content="Plan: inspect player.gd, then summarize it.")),
                _resp(
                    Message.assistant(
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                name="read_file",
                                arguments=json.dumps({"path": str(project_root / "player.gd")}),
                            )
                        ]
                    )
                ),
                _resp(Message.assistant(content="Player speed is defined in player.gd.")),
            ]
        )
        dispatcher = AgentDispatcher(
            client=client,
            registry=registry,
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file"},
        )
        engine = ConversationEngine(
            client=client,
            registry=registry,
            system_prompt=PromptAssembler(PromptContext(project_root=project_root, mode="apply")).build(),
            project_path=str(project_root),
            prompt_assembler=PromptAssembler(PromptContext(project_root=project_root, mode="apply")),
            auto_validate=False,
            dispatcher=dispatcher,
        )
        engine.allowed_tools = {"read_file"}
        # v1.0.1/T2: this test verifies the planner flow itself, not the
        # lazy heuristic — disable lazy so "Inspect the player script"
        # always triggers a planner pass regardless of the heuristic's
        # read-only classification.
        engine.planner_lazy = False

        result = await engine.submit("Inspect the player script")

        assert result == "Player speed is defined in player.gd."
        assert engine.last_plan.startswith("Plan:")
        assert any(
            isinstance(message.content, str) and "Planner pass before implementation" in message.content
            for message in engine.messages
        )
        assert client.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_engine_uses_dispatcher_reviewer_after_mutation(self, project_root: Path, monkeypatch) -> None:
        registry = _make_registry()
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(
            side_effect=[
                _resp(Message.assistant(content="Plan: create a new note file.")),
                _resp(
                    Message.assistant(
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                name="write_file",
                                arguments=json.dumps(
                                    {
                                        "path": str(project_root / "notes.txt"),
                                        "content": "todo\n",
                                    }
                                ),
                            )
                        ]
                    )
                ),
                _resp(Message.assistant(content="Created the note file.")),
            ]
        )
        dispatcher = AgentDispatcher(
            client=client,
            registry=registry,
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"write_file"},
        )

        async def fake_run_reviewer(*, changed_files, quality_report=None):
            report = ReviewReport(
                checks=[
                    ReviewCheck(
                        description="Check new note file",
                        command="stat notes.txt",
                        observed_output="notes.txt exists.",
                        status="PASS",
                    )
                ]
            )
            return AgentTaskResult(role="reviewer", verdict="PASS", content="ok", raw=report)

        monkeypatch.setattr(dispatcher, "run_reviewer", fake_run_reviewer)

        engine = ConversationEngine(
            client=client,
            registry=registry,
            system_prompt=PromptAssembler(PromptContext(project_root=project_root, mode="apply")).build(),
            project_path=str(project_root),
            prompt_assembler=PromptAssembler(PromptContext(project_root=project_root, mode="apply")),
            auto_validate=False,
            dispatcher=dispatcher,
        )
        engine.allowed_tools = {"write_file"}

        result = await engine.submit("Create a note file")

        assert result == "Created the note file."
        assert engine.last_review_report is not None
        assert engine.last_review_report.verdict == "PASS"
        assert (project_root / "notes.txt").exists()

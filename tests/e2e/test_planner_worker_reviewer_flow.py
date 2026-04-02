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
from godot_agent.tools.file_ops import EditFileTool, WriteFileTool, clear_project_root, set_project_root
from godot_agent.tools.registry import ToolRegistry


def _resp(msg: Message) -> ChatResponse:
    return ChatResponse(message=msg, usage=TokenUsage())


@pytest.fixture
def godot_project(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="FlowTest"\n')
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


def _make_engine(godot_project: Path, client: AsyncMock, dispatcher: AgentDispatcher) -> ConversationEngine:
    registry = ToolRegistry()
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    prompt_assembler = PromptAssembler(PromptContext(project_root=godot_project, mode="apply"))
    engine = ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=prompt_assembler.build(),
        project_path=str(godot_project),
        prompt_assembler=prompt_assembler,
        auto_validate=False,
        mode="apply",
        dispatcher=dispatcher,
    )
    engine.allowed_tools = {"write_file", "edit_file"}
    return engine


@pytest.mark.asyncio
async def test_planner_worker_reviewer_recovers_before_finishing(godot_project: Path, monkeypatch) -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(
        side_effect=[
            _resp(Message.assistant(content="Plan: create the file, then fix reviewer feedback.")),
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            name="write_file",
                            arguments=json.dumps(
                                {"path": str(godot_project / "notes.txt"), "content": "bad\n"}
                            ),
                        )
                    ]
                )
            ),
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-2",
                            name="edit_file",
                            arguments=json.dumps(
                                {
                                    "path": str(godot_project / "notes.txt"),
                                    "old_string": "bad",
                                    "new_string": "good",
                                }
                            ),
                        )
                    ]
                )
            ),
            _resp(Message.assistant(content="Finished after reviewer feedback.")),
        ]
    )
    dispatcher = AgentDispatcher(
        client=client,
        registry=registry,
        prompt_context=PromptContext(project_root=godot_project, mode="apply"),
        project_path=str(godot_project),
        base_allowed_tools={"write_file", "edit_file"},
    )

    reviewer_calls = {"count": 0}

    async def fake_run_reviewer(*, changed_files, quality_report=None):
        reviewer_calls["count"] += 1
        if reviewer_calls["count"] == 1:
            report = ReviewReport(
                checks=[
                    ReviewCheck(
                        description="Check note quality",
                        command="cat notes.txt",
                        observed_output="Content was bad.",
                        status="FAIL",
                    )
                ]
            )
            return AgentTaskResult(role="reviewer", verdict="FAIL", content="bad", raw=report)
        report = ReviewReport(
            checks=[
                ReviewCheck(
                    description="Check note quality",
                    command="cat notes.txt",
                    observed_output="Content is good.",
                    status="PASS",
                )
            ]
        )
        return AgentTaskResult(role="reviewer", verdict="PASS", content="good", raw=report)

    monkeypatch.setattr(dispatcher, "run_reviewer", fake_run_reviewer)

    engine = _make_engine(godot_project, client, dispatcher)
    result = await engine.submit("Create a note file")

    assert result == "Finished after reviewer feedback."
    assert engine.last_plan.startswith("Plan:")
    assert reviewer_calls["count"] == 2
    assert engine.last_review_report is not None
    assert engine.last_review_report.verdict == "PASS"
    assert (godot_project / "notes.txt").read_text() == "good\n"

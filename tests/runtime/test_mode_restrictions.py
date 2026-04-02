import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.llm.client import ChatResponse, LLMClient, Message, ToolCall, TokenUsage
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.modes import allowed_tools_for_mode
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool, clear_project_root, set_project_root
from godot_agent.tools.registry import ToolRegistry


def _resp(msg: Message) -> ChatResponse:
    return ChatResponse(message=msg, usage=TokenUsage())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    (tmp_path / "player.gd").write_text("extends Node\n")
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


def _engine_for_mode(project_root: Path, mode: str, client: AsyncMock) -> ConversationEngine:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    prompt_assembler = PromptAssembler(PromptContext(project_root=project_root, mode=mode))
    engine = ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=prompt_assembler.build(),
        project_path=str(project_root),
        prompt_assembler=prompt_assembler,
        auto_validate=False,
        mode=mode,
    )
    engine.allowed_tools = allowed_tools_for_mode(mode)
    return engine


@pytest.mark.parametrize("mode", ["plan", "review", "explain"])
@pytest.mark.asyncio
async def test_read_only_modes_block_write_tool_calls(project_root: Path, mode: str) -> None:
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(
        side_effect=[
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            name="write_file",
                            arguments=json.dumps(
                                {"path": str(project_root / "notes.txt"), "content": "hello\n"}
                            ),
                        )
                    ]
                )
            ),
            _resp(Message.assistant(content="Write blocked as expected.")),
        ]
    )
    engine = _engine_for_mode(project_root, mode, client)

    result = await engine.submit("Try to write a file")

    assert result == "Write blocked as expected."
    tool_result_message = next(message for message in engine.messages if message.role == "tool")
    assert "not allowed" in tool_result_message.content
    assert not (project_root / "notes.txt").exists()


@pytest.mark.parametrize("mode", ["apply", "fix"])
@pytest.mark.asyncio
async def test_apply_like_modes_allow_write_tool_calls(project_root: Path, mode: str) -> None:
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(
        side_effect=[
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            name="write_file",
                            arguments=json.dumps(
                                {"path": str(project_root / "notes.txt"), "content": "hello\n"}
                            ),
                        )
                    ]
                )
            ),
            _resp(Message.assistant(content="Write succeeded.")),
        ]
    )
    engine = _engine_for_mode(project_root, mode, client)

    result = await engine.submit("Write a file")

    assert result == "Write succeeded."
    assert (project_root / "notes.txt").read_text() == "hello\n"

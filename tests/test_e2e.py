"""End-to-end integration tests exercising the full agent loop.

Each test simulates a realistic workflow: the mock LLM client returns a
pre-scripted sequence of tool-call messages, the real tool registry executes
them against a temporary Godot project on disk, and the engine drives the
conversation to a final text reply.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.llm.client import LLMClient, Message, ToolCall, ChatResponse, TokenUsage


def _resp(msg: Message) -> ChatResponse:
    return ChatResponse(message=msg, usage=TokenUsage())
from godot_agent.prompts.system import build_system_prompt
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.tools.file_ops import set_project_root
from godot_agent.tools.file_ops import EditFileTool, ReadFileTool, WriteFileTool
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.search import GlobTool, GrepTool


@pytest.fixture
def godot_project(tmp_path: Path) -> Path:
    """Scaffold a minimal Godot 4 project on disk."""
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="TestGame"\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "player.gd").write_text(
        "extends CharacterBody2D\n\nvar speed = 100\n"
    )
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "main.tscn").write_text(
        '[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n'
    )
    return tmp_path


def _make_engine(
    godot_project: Path, mock_client: AsyncMock
) -> ConversationEngine:
    """Build a ConversationEngine wired to real tools and a mock LLM."""
    set_project_root(godot_project)
    registry = ToolRegistry()
    for tool_cls in [ReadFileTool, WriteFileTool, EditFileTool, GrepTool, GlobTool]:
        registry.register(tool_cls())
    prompt = build_system_prompt(godot_project)
    return ConversationEngine(
        client=mock_client, registry=registry, system_prompt=prompt
    )


class TestE2EReadAndEdit:
    """Simulate LLM reading a file, then editing it in a multi-turn loop."""

    @pytest.mark.asyncio
    async def test_read_then_edit_workflow(self, godot_project: Path) -> None:
        player_path = str(godot_project / "src" / "player.gd")

        read_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="read_file",
                    arguments=json.dumps({"path": player_path}),
                )
            ]
        )
        edit_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c2",
                    name="edit_file",
                    arguments=json.dumps(
                        {
                            "path": player_path,
                            "old_string": "var speed = 100",
                            "new_string": "var speed = 200",
                        }
                    ),
                )
            ]
        )
        final = Message.assistant(content="Done! Changed speed from 100 to 200.")

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[_resp(read_call), _resp(edit_call), _resp(final)])

        engine = _make_engine(godot_project, mock_client)
        result = await engine.submit("Change player speed to 200")

        assert "200" in result
        assert "var speed = 200" in (godot_project / "src" / "player.gd").read_text()


class TestE2ESearch:
    """Simulate LLM searching for a regex pattern across project files."""

    @pytest.mark.asyncio
    async def test_grep_workflow(self, godot_project: Path) -> None:
        search_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="grep",
                    arguments=json.dumps(
                        {
                            "pattern": "speed",
                            "path": str(godot_project),
                            "glob": "*.gd",
                        }
                    ),
                )
            ]
        )
        final = Message.assistant(
            content="Found speed variable in player.gd line 3."
        )

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[_resp(search_call), _resp(final)])

        engine = _make_engine(godot_project, mock_client)
        result = await engine.submit("Find where speed is defined")
        assert "speed" in result.lower() or "player" in result.lower()


class TestE2EWriteNewFile:
    """Simulate LLM creating a brand-new GDScript file on disk."""

    @pytest.mark.asyncio
    async def test_create_new_script(self, godot_project: Path) -> None:
        new_path = str(godot_project / "src" / "enemy.gd")
        write_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="write_file",
                    arguments=json.dumps(
                        {
                            "path": new_path,
                            "content": "extends CharacterBody2D\n\nvar hp = 50\n",
                        }
                    ),
                )
            ]
        )
        final = Message.assistant(content="Created enemy.gd with 50 HP.")

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[_resp(write_call), _resp(final)])

        engine = _make_engine(godot_project, mock_client)
        result = await engine.submit("Create an enemy script")

        assert Path(new_path).exists()
        assert "hp = 50" in Path(new_path).read_text()


class TestE2EMultiToolChain:
    """Simulate a multi-step chain: glob to find files, then read one."""

    @pytest.mark.asyncio
    async def test_glob_then_read(self, godot_project: Path) -> None:
        glob_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="glob",
                    arguments=json.dumps(
                        {"pattern": "**/*.gd", "path": str(godot_project)}
                    ),
                )
            ]
        )
        read_call = Message.assistant(
            tool_calls=[
                ToolCall(
                    id="c2",
                    name="read_file",
                    arguments=json.dumps(
                        {"path": str(godot_project / "src" / "player.gd")}
                    ),
                )
            ]
        )
        final = Message.assistant(
            content="Found 1 GDScript file. Player has speed=100."
        )

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=[_resp(glob_call), _resp(read_call), _resp(final)])

        engine = _make_engine(godot_project, mock_client)
        result = await engine.submit("List all scripts and show me the player")
        assert "100" in result or "speed" in result.lower()


class TestE2ESystemPromptIntegrity:
    """Verify the system prompt includes project context and tool names."""

    def test_system_prompt_has_project_context(self, godot_project: Path) -> None:
        prompt = build_system_prompt(godot_project)
        assert "TestGame" in prompt
        assert "read_file" in prompt
        assert ".tscn" in prompt

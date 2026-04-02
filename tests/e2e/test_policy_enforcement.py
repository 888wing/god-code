import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.llm.client import ChatResponse, LLMClient, Message, ToolCall, TokenUsage
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.tools.file_ops import EditFileTool, clear_project_root, set_project_root
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.scene_tools import AddSceneNodeTool, ReadSceneTool


def _resp(msg: Message) -> ChatResponse:
    return ChatResponse(message=msg, usage=TokenUsage())


@pytest.fixture
def godot_project(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="PolicyTest"\nrun/main_scene="res://main.tscn"\n'
    )
    (tmp_path / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
    (tmp_path / "side_scene.tscn").write_text('[gd_scene format=3]\n\n[node name="Side" type="Node2D"]\n')
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


def _make_engine(godot_project: Path, client: AsyncMock) -> ConversationEngine:
    registry = ToolRegistry()
    registry.register(EditFileTool())
    registry.register(ReadSceneTool())
    registry.register(AddSceneNodeTool())
    prompt_assembler = PromptAssembler(PromptContext(project_root=godot_project, mode="apply"))
    engine = ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=prompt_assembler.build(),
        project_path=str(godot_project),
        prompt_assembler=prompt_assembler,
        auto_validate=False,
        mode="apply",
    )
    engine.allowed_tools = {"edit_file", "read_scene", "add_scene_node"}
    return engine


@pytest.mark.asyncio
async def test_raw_scene_edit_is_blocked_then_structured_edit_succeeds(godot_project: Path) -> None:
    scene_path = godot_project / "side_scene.tscn"
    client = AsyncMock(spec=LLMClient)
    client.chat = AsyncMock(
        side_effect=[
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            name="read_scene",
                            arguments=json.dumps({"path": str(scene_path)}),
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
                                    "path": str(scene_path),
                                    "old_string": 'type="Node2D"',
                                    "new_string": 'type="CanvasLayer"',
                                }
                            ),
                        )
                    ]
                )
            ),
            _resp(
                Message.assistant(
                    tool_calls=[
                        ToolCall(
                            id="tool-3",
                            name="add_scene_node",
                            arguments=json.dumps(
                                {
                                    "path": str(scene_path),
                                    "parent": ".",
                                    "name": "Hud",
                                    "type": "CanvasLayer",
                                }
                            ),
                        )
                    ]
                )
            ),
            _resp(Message.assistant(content="Added Hud using the structured scene tool.")),
        ]
    )

    engine = _make_engine(godot_project, client)
    result = await engine.submit("Add a HUD node to the side scene")

    tool_messages = [message for message in engine.messages if message.role == "tool"]
    assert "structured scene tools" in tool_messages[1].content
    assert "Hud" in scene_path.read_text()
    assert result == "Added Hud using the structured scene tool."

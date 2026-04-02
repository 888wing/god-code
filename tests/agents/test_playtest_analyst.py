from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.llm.client import LLMClient
from godot_agent.prompts.assembler import PromptContext
from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot, clear_runtime_snapshot, update_runtime_snapshot
from godot_agent.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_dispatcher_runs_playtest_analyst(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="PlaytestGame"\n')
    update_runtime_snapshot(
        RuntimeSnapshot(
            nodes=[RuntimeNodeState(path="Main/Player", type="CharacterBody2D")],
            events=[RuntimeEvent(name="player_moved")],
            input_actions=["move_left", "move_right"],
        )
    )
    try:
        dispatcher = AgentDispatcher(
            client=AsyncMock(spec=LLMClient),
            registry=ToolRegistry(),
            prompt_context=PromptContext(project_root=tmp_path, mode="apply"),
            project_path=str(tmp_path),
        )

        result = await dispatcher.run_playtest_analyst(changed_files={str(tmp_path / "player_controller.gd")})

        assert result.role == "playtest_analyst"
        assert result.verdict == "PASS"
        assert "Playtest VERDICT: PASS" in result.content
    finally:
        clear_runtime_snapshot()

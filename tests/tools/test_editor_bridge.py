import asyncio

from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot, clear_runtime_snapshot, update_runtime_snapshot
from godot_agent.tools.editor_bridge import GetRuntimeSnapshotTool, RunPlaytestTool
from godot_agent.tools.file_ops import clear_project_root, set_project_root


def test_get_runtime_snapshot_tool_reads_current_snapshot(tmp_path):
    set_project_root(tmp_path)
    update_runtime_snapshot(
        RuntimeSnapshot(
            active_scene="res://scenes/main.tscn",
            nodes=[RuntimeNodeState(path="Main/Hud", type="CanvasLayer")],
            events=[RuntimeEvent(name="player_moved")],
        )
    )
    try:
        tool = GetRuntimeSnapshotTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path))))
        assert "Runtime Snapshot" in result.output.report
        assert result.output.snapshot["active_scene"] == "res://scenes/main.tscn"
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_playtest_tool_uses_runtime_snapshot(tmp_path):
    set_project_root(tmp_path)
    update_runtime_snapshot(
        RuntimeSnapshot(
            nodes=[RuntimeNodeState(path="Main/Player", type="CharacterBody2D")],
            events=[RuntimeEvent(name="player_moved")],
            input_actions=["move_left", "move_right"],
        )
    )
    try:
        tool = RunPlaytestTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(project_path=str(tmp_path), changed_files=[str(tmp_path / "player_controller.gd")])
            )
        )
        assert result.output.verdict == "PASS"
    finally:
        clear_runtime_snapshot()
        clear_project_root()

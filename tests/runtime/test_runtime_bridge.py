from godot_agent.runtime.runtime_bridge import (
    RuntimeEvent,
    RuntimeNodeState,
    RuntimeSnapshot,
    clear_runtime_snapshot,
    format_runtime_snapshot,
    get_runtime_snapshot,
    update_runtime_snapshot,
)


def test_runtime_bridge_round_trip():
    snapshot = RuntimeSnapshot(
        active_scene="res://scenes/main.tscn",
        nodes=[RuntimeNodeState(path="Main/Hud", type="CanvasLayer")],
        events=[RuntimeEvent(name="player_moved")],
        input_actions=["move_left"],
    )
    update_runtime_snapshot(snapshot)
    try:
        loaded = get_runtime_snapshot()
        assert loaded is not None
        assert loaded.active_scene == "res://scenes/main.tscn"
        assert "player_moved" in format_runtime_snapshot(loaded)
    finally:
        clear_runtime_snapshot()


def test_format_runtime_snapshot_handles_missing_snapshot():
    assert format_runtime_snapshot(None) == "No runtime snapshot available."

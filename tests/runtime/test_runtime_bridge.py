from godot_agent.runtime.runtime_bridge import (
    RuntimeEvent,
    RuntimeNodeState,
    RuntimeSnapshot,
    advance_runtime_ticks,
    clear_runtime_snapshot,
    format_runtime_snapshot,
    get_runtime_snapshot,
    load_runtime_scene,
    press_runtime_action,
    runtime_events_since,
    runtime_state_dict,
    set_runtime_fixture,
    update_runtime_snapshot,
)


def test_runtime_bridge_round_trip():
    snapshot = RuntimeSnapshot(
        active_scene="res://scenes/main.tscn",
        nodes=[RuntimeNodeState(path="Main/Hud", type="CanvasLayer")],
        events=[RuntimeEvent(name="player_moved")],
        input_actions=["move_left"],
        source="live_editor",
    )
    update_runtime_snapshot(snapshot)
    try:
        loaded = get_runtime_snapshot()
        assert loaded is not None
        assert loaded.active_scene == "res://scenes/main.tscn"
        assert loaded.source == "live_editor"
        assert loaded.evidence_level == "high"
        assert loaded.bridge_connected is True
        assert "player_moved" in format_runtime_snapshot(loaded)
    finally:
        clear_runtime_snapshot()


def test_format_runtime_snapshot_handles_missing_snapshot():
    assert format_runtime_snapshot(None) == "No runtime snapshot available."


def test_runtime_harness_controls_track_tick_state_and_events():
    try:
        load_runtime_scene("res://scenes/battle.tscn")
        set_runtime_fixture("inventory", {"coins": 3})
        press_runtime_action("fire", pressed=True)
        advance_runtime_ticks(
            5,
            state_updates={"player_hp": 7},
            events=[{"name": "enemy_hit", "payload": "enemy_1"}],
        )

        snapshot = get_runtime_snapshot()

        assert snapshot is not None
        assert snapshot.active_scene == "res://scenes/battle.tscn"
        assert snapshot.current_tick == 5
        assert snapshot.fixtures["inventory"]["coins"] == 3
        assert snapshot.active_inputs == ["fire"]
        assert runtime_state_dict(snapshot)["state"]["player_hp"] == 7
        assert runtime_events_since(0)[0].name == "enemy_hit"
        assert snapshot.source == "synthetic"
        assert "Tick: 5" in format_runtime_snapshot(snapshot)
    finally:
        clear_runtime_snapshot()

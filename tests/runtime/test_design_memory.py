from godot_agent.runtime.design_memory import (
    DesignMemory,
    design_memory_path,
    format_design_memory,
    load_design_memory,
    save_design_memory,
    update_design_memory,
)


def test_load_empty_design_memory(tmp_path):
    memory = load_design_memory(tmp_path)
    assert memory.is_empty


def test_save_and_load_design_memory(tmp_path):
    memory = DesignMemory(
        game_title="Sky Ruins",
        pillars=["Aerial mobility", "Short combat loops"],
        control_rules=["move_left and move_right always available"],
    )
    save_design_memory(tmp_path, memory)

    loaded = load_design_memory(tmp_path)
    assert loaded.game_title == "Sky Ruins"
    assert loaded.pillars == ["Aerial mobility", "Short combat loops"]
    assert design_memory_path(tmp_path).exists()


def test_update_design_memory_list_and_mapping(tmp_path):
    update_design_memory(tmp_path, section="pillars", items=["Tight controls"])
    update_design_memory(tmp_path, section="scene_ownership", mapping={"res://scenes/main.tscn": "Main gameplay loop"})
    update_design_memory(tmp_path, section="mechanic_notes:combat", items=["Damage windows are short"], append=True)

    memory = load_design_memory(tmp_path)
    assert memory.pillars == ["Tight controls"]
    assert memory.scene_ownership["res://scenes/main.tscn"] == "Main gameplay loop"
    assert memory.mechanic_notes["combat"] == ["Damage windows are short"]


def test_format_design_memory_includes_sections(tmp_path):
    memory = DesignMemory(game_title="Ruin Runner", ui_principles=["Readable HUD"], non_goals=["No inventory grind"])
    save_design_memory(tmp_path, memory)

    report = format_design_memory(load_design_memory(tmp_path))
    assert "Ruin Runner" in report
    assert "Readable HUD" in report
    assert "No inventory grind" in report

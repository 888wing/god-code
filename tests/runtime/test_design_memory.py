from godot_agent.runtime.design_memory import (
    AssetSpec,
    CombatProfile,
    DesignMemory,
    GameplayIntentProfile,
    PolishProfile,
    design_memory_path,
    format_design_memory,
    load_design_memory,
    resolved_asset_spec,
    resolved_polish_profile,
    resolved_quality_target,
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


def test_save_and_load_gameplay_intent_profile(tmp_path):
    memory = DesignMemory(
        game_title="Starfall",
        gameplay_intent=GameplayIntentProfile(
            genre="bullet_hell",
            enemy_model="scripted_patterns",
            combat_profile=CombatProfile(
                player_space_model="free_2d_dodge",
                density_curve="ramp_up",
            ),
            confirmed=True,
            confidence=1.0,
        ),
        quality_target="demo",
        asset_spec=AssetSpec(
            style="pixel_art",
            target_size=[64, 64],
            background_key="#00FF00",
            alpha_required=True,
        ),
        polish_profile=PolishProfile(combat_feedback="required", wave_pacing="required"),
    )
    save_design_memory(tmp_path, memory)

    loaded = load_design_memory(tmp_path)
    assert loaded.gameplay_intent.genre == "bullet_hell"
    assert loaded.gameplay_intent.enemy_model == "scripted_patterns"
    assert loaded.gameplay_intent.combat_profile.player_space_model == "free_2d_dodge"
    assert loaded.gameplay_intent.confirmed is True
    assert loaded.quality_target == "demo"
    assert loaded.asset_spec.target_size == [64, 64]
    assert loaded.polish_profile.combat_feedback == "required"


def test_update_design_memory_gameplay_intent_mapping(tmp_path):
    update_design_memory(
        tmp_path,
        section="gameplay_intent",
        mapping={
            "genre": "tower_defense",
            "enemy_model": "path_followers",
            "confirmed": True,
            "combat_profile": {"density_curve": "wave_escalation"},
        },
    )

    memory = load_design_memory(tmp_path)
    assert memory.gameplay_intent.genre == "tower_defense"
    assert memory.gameplay_intent.enemy_model == "path_followers"
    assert memory.gameplay_intent.confirmed is True
    assert memory.gameplay_intent.combat_profile.density_curve == "wave_escalation"


def test_update_design_memory_quality_and_asset_contracts(tmp_path):
    update_design_memory(tmp_path, section="quality_target", text="demo")
    update_design_memory(
        tmp_path,
        section="asset_spec",
        mapping={"style": "pixel_art", "target_size": [64, 64], "background_key": "#00FF00", "alpha_required": True},
    )
    update_design_memory(
        tmp_path,
        section="polish_profile",
        mapping={"combat_feedback": "required", "boss_transition": "required"},
    )

    memory = load_design_memory(tmp_path)
    assert resolved_quality_target(memory) == "demo"
    assert resolved_asset_spec(memory).style == "pixel_art"
    assert resolved_polish_profile(memory, quality_target="demo").combat_feedback == "required"
    report = format_design_memory(memory)
    assert "Asset Spec" in report
    assert "Quality Target" in report

from godot_agent.runtime.design_memory import DesignMemory, GameplayIntentProfile
from godot_agent.runtime.intent_resolver import (
    apply_intent_answers,
    gameplay_profile_to_skill_keys,
    resolve_gameplay_intent,
    should_prompt_for_intent,
)


def _write_project(path, *, actions: list[str], width: int = 480, height: int = 800):
    input_lines = "\n".join(f'{action}={{"deadzone":0.5,"events":[]}}' for action in actions)
    (path / "project.godot").write_text(
        f"""
[application]
config/name="Demo"
run/main_scene="res://scenes/game.tscn"

[display]
window/size/viewport_width={width}
window/size/viewport_height={height}

[input]
{input_lines}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_resolve_gameplay_intent_infers_bullet_hell_from_project_signals(tmp_path):
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scripts").mkdir()
    _write_project(tmp_path, actions=["shoot", "move_up", "move_down"])
    (tmp_path / "scenes" / "boss_room.tscn").write_text("", encoding="utf-8")
    (tmp_path / "scripts" / "enemy_bullet.gd").write_text("", encoding="utf-8")

    profile = resolve_gameplay_intent(tmp_path, user_hint="add boss bullet patterns for wave 2")

    assert profile.genre == "bullet_hell"
    assert profile.enemy_model == "scripted_patterns"
    assert "wave_timing" in profile.testing_focus


def test_resolve_gameplay_intent_detects_conflicting_shooter_and_tower_defense_signals(tmp_path):
    (tmp_path / "assets").mkdir()
    _write_project(tmp_path, actions=["shoot", "place_turret"])
    (tmp_path / "assets" / "turret.png").write_text("", encoding="utf-8")
    (tmp_path / "enemy_bullet.gd").write_text("", encoding="utf-8")

    profile = resolve_gameplay_intent(tmp_path, user_hint="improve the enemy waves")

    assert profile.conflicts
    assert should_prompt_for_intent(profile, user_hint="rewrite the enemy AI")


def test_confirmed_design_memory_profile_takes_precedence(tmp_path):
    _write_project(tmp_path, actions=["jump"], width=1280, height=720)
    memory = DesignMemory(
        gameplay_intent=GameplayIntentProfile(
            genre="tower_defense",
            enemy_model="path_followers",
            confirmed=True,
            confidence=1.0,
        )
    )

    profile = resolve_gameplay_intent(tmp_path, user_hint="add more patrol enemies", design_memory=memory)

    assert profile.genre == "tower_defense"
    assert profile.confirmed is True


def test_apply_intent_answers_marks_profile_confirmed():
    updated = apply_intent_answers(
        GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
        {
            "genre": "topdown_shooter",
            "player_control_model": "free_2d_shooting",
            "enemy_model": "reactive_ranged",
        },
    )

    assert updated.genre == "topdown_shooter"
    assert updated.confirmed is True
    assert updated.confidence == 1.0


def test_gameplay_profile_maps_to_genre_skill():
    assert gameplay_profile_to_skill_keys(GameplayIntentProfile(genre="stealth_guard")) == ["stealth_guard"]

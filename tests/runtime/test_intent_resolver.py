from godot_agent.runtime.design_memory import CombatProfile, DesignMemory, GameplayIntentProfile
from godot_agent.runtime.intent_resolver import (
    _project_signal_tokens,
    apply_intent_answers,
    clear_token_cache,
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
    assert profile.combat_profile.density_curve == "ramp_up"
    assert profile.combat_profile.bullet_cleanup_policy == "phase_transition_and_timeout"


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
    assert updated.combat_profile.player_space_model == "free_2d_shooting"


def test_apply_intent_answers_preserves_confirmed_profile_shape_when_genre_is_unchanged():
    base = GameplayIntentProfile(
        genre="bullet_hell",
        camera_model="vertical_scroller",
        player_control_model="free_2d_dodge",
        combat_model="pattern_survival",
        enemy_model="scripted_patterns",
        boss_model="phase_based",
        testing_focus=["wave_timing", "pattern_readability", "boss_phase_clear"],
        combat_profile=CombatProfile(
            player_space_model="free_2d_dodge",
            density_curve="ramp_up",
            readability_target="clear_dense",
            bullet_cleanup_policy="phase_transition_and_timeout",
            phase_style="telegraphed",
        ),
        confirmed=True,
        confidence=1.0,
        reasons=["Using confirmed gameplay intent from design memory."],
    )

    updated = apply_intent_answers(
        base,
        {
            "genre": "bullet_hell",
            "player_control_model": "free_2d_dodge",
            "enemy_model": "scripted_patterns",
        },
    )

    assert updated.camera_model == "vertical_scroller"
    assert updated.combat_model == "pattern_survival"
    assert updated.testing_focus == ["wave_timing", "pattern_readability", "boss_phase_clear"]
    assert updated.combat_profile.bullet_cleanup_policy == "phase_transition_and_timeout"
    assert updated.confirmed is True


def test_token_cache_avoids_rescan(tmp_path):
    """Second call to _project_signal_tokens returns cached result without re-scanning."""
    clear_token_cache()
    _write_project(tmp_path, actions=["shoot"])
    # First call scans
    tokens1 = _project_signal_tokens(tmp_path)
    # Second call hits cache
    tokens2 = _project_signal_tokens(tmp_path)
    assert tokens1 is tokens2  # Same object = cached
    clear_token_cache()


def test_token_cache_invalidates_on_different_root(tmp_path):
    """Cache is invalidated when project_root changes."""
    clear_token_cache()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _write_project(dir_a, actions=["shoot"])
    _write_project(dir_b, actions=["jump"])

    tokens_a = _project_signal_tokens(dir_a)
    tokens_b = _project_signal_tokens(dir_b)
    assert tokens_a is not tokens_b  # Different roots = different results
    clear_token_cache()


def test_gameplay_profile_maps_to_genre_skill():
    assert gameplay_profile_to_skill_keys(GameplayIntentProfile(genre="stealth_guard")) == ["stealth_guard"]

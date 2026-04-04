from godot_agent.runtime.design_memory import GameplayIntentProfile
from godot_agent.prompts.skill_selector import (
    format_skill_injection,
    narrow_tools_for_skills,
    normalize_skill_name,
    resolve_skills,
    select_skills,
)


def test_collision_prompt_activates_collision_skill():
    skills = select_skills("fix collision layers for player bullets")
    names = [skill.name for skill in skills]
    assert "Collision Architecture" in names


def test_movement_prompt_activates_physics_skill():
    skills = select_skills("fix player movement and jump physics")
    names = [skill.name for skill in skills]
    assert "Physics Gameplay" in names


def test_file_extension_bonus_can_activate_skill():
    skills = select_skills("edit this scene", file_paths=["scenes/player.tscn"])
    names = [skill.name for skill in skills]
    assert "Collision Architecture" in names


def test_format_skill_injection_renders_heading():
    text = format_skill_injection(select_skills("tune gravity and movement"))
    assert "Active Skills" in text


def test_narrow_tools_for_collision_skill_filters_base_scope():
    skills = select_skills("fix collision masks for bullets")
    narrowed = narrow_tools_for_skills(skills, {"read_scene", "write_scene_property", "run_shell"})
    assert narrowed == {"read_scene", "write_scene_property"}


def test_resolve_skills_manual_override_activates_skill_without_prompt_match():
    skills = resolve_skills(
        "inspect the player scene",
        skill_mode="manual",
        enabled_skills=["collision"],
    )
    assert [skill.key for skill in skills] == ["collision"]


def test_resolve_skills_hybrid_disable_removes_auto_selected_skill():
    skills = resolve_skills(
        "fix collision layers for enemy bullets",
        skill_mode="hybrid",
        disabled_skills=["collision"],
    )
    assert all(skill.key != "collision" for skill in skills)


def test_normalize_skill_name_accepts_aliases():
    assert normalize_skill_name("Collision Architecture") == "collision"
    assert normalize_skill_name("movement") == "physics"


def test_intent_profile_can_activate_genre_skill():
    skills = resolve_skills(
        "tune enemy behavior",
        intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
    )
    assert any(skill.key == "bullet_hell" for skill in skills)

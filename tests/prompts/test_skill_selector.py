from godot_agent.prompts.skill_selector import format_skill_injection, narrow_tools_for_skills, select_skills


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

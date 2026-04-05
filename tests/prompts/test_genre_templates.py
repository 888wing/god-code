from godot_agent.prompts.genre_templates import format_genre_template, template_for_profile
from godot_agent.runtime.design_memory import CombatProfile, GameplayIntentProfile


def test_bullet_hell_profile_resolves_template():
    profile = GameplayIntentProfile(
        genre="bullet_hell",
        enemy_model="scripted_patterns",
        combat_profile=CombatProfile(
            player_space_model="free_2d_dodge",
            density_curve="ramp_up",
            readability_target="clear_dense",
        ),
    )

    template = template_for_profile(profile)
    assert template is not None
    assert template.genre == "bullet_hell"

    rendered = format_genre_template(profile)
    assert "Bullet Hell Template Library" in rendered
    assert "straight_drop" in rendered
    assert "fan_burst" in rendered

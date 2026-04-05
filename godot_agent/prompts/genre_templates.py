"""Genre template guidance injected alongside gameplay-intent profiles."""

from __future__ import annotations

from dataclasses import dataclass

from godot_agent.runtime.design_memory import GameplayIntentProfile


@dataclass(frozen=True)
class GenreTemplate:
    genre: str
    title: str
    architecture: tuple[str, ...]
    archetypes: tuple[str, ...]
    validation: tuple[str, ...]
    non_goals: tuple[str, ...] = ()


GENRE_TEMPLATES: dict[str, GenreTemplate] = {
    "bullet_hell": GenreTemplate(
        genre="bullet_hell",
        title="Bullet Hell Template Library",
        architecture=(
            "Separate enemy_core, movement_pattern, fire_pattern, encounter_director, and boss_phase_controller.",
            "Treat wave timing and phase transitions as authored combat assets, not side effects of enemy scripts.",
            "Prefer telegraphed phase transitions with explicit bullet cleanup policies.",
        ),
        archetypes=(
            "Movement: straight_drop, sine_drift, sweep_horizontal, arc_entry, enter_hold_exit, waypoint_path.",
            "Fire: single_shot, aimed_burst, fan_burst, ring_burst, spiral_stream, sweeping_fan.",
            "Waves: staggered_line, left_right_pincer, escort_wave, miniboss_intro, boss_phase_sequence.",
        ),
        validation=(
            "Validate wave progression, pattern readability, bullet cleanup, and boss phase transitions.",
            "Reject reactive chase AI as the default unless the confirmed profile explicitly asks for it.",
        ),
        non_goals=(
            "Do not collapse bullet-hell combat into generic chase-and-shoot enemy AI.",
        ),
    ),
    "topdown_shooter": GenreTemplate(
        genre="topdown_shooter",
        title="Top-Down Shooter Template",
        architecture=(
            "Split enemy_core from targeting, movement_state, pressure_role, and spawn pacing.",
            "Use small state transitions such as kite, flank, hold, rush instead of one large reactive script.",
        ),
        archetypes=(
            "Enemies: chaser, standoff_shooter, flanker, spawner.",
        ),
        validation=(
            "Validate spawn pressure, targeting quality, and combat readability under movement.",
        ),
    ),
    "platformer_enemy": GenreTemplate(
        genre="platformer_enemy",
        title="Platformer Enemy Template",
        architecture=(
            "Build state-machine enemies with explicit patrol, chase, attack, recover, and ledge-awareness logic.",
        ),
        archetypes=(
            "Enemies: walker, edge_guard, turret, jumper.",
        ),
        validation=(
            "Validate patrol edges, jump collisions, and attack windows.",
        ),
    ),
    "tower_defense": GenreTemplate(
        genre="tower_defense",
        title="Tower Defense Template",
        architecture=(
            "Split lane/path following from wave composition, target priority, and support interactions.",
        ),
        archetypes=(
            "Enemies: runner, tank, flyer, shield_support.",
        ),
        validation=(
            "Validate path following, target priority, and wave balance.",
        ),
    ),
}


def template_for_profile(profile: GameplayIntentProfile | None) -> GenreTemplate | None:
    if profile is None or not profile.genre:
        return None
    return GENRE_TEMPLATES.get(profile.genre)


def format_genre_template(profile: GameplayIntentProfile | None) -> str:
    template = template_for_profile(profile)
    if template is None:
        return ""

    lines = [f"## {template.title}"]
    if profile is not None and not profile.combat_profile.is_empty:
        lines.append("")
        lines.append(
            "Resolved combat profile: "
            f"player_space={profile.combat_profile.player_space_model or '-'}, "
            f"density={profile.combat_profile.density_curve or '-'}, "
            f"readability={profile.combat_profile.readability_target or '-'}, "
            f"cleanup={profile.combat_profile.bullet_cleanup_policy or '-'}, "
            f"phase={profile.combat_profile.phase_style or '-'}."
        )
    lines.append("")
    lines.append("Architecture:")
    lines.extend(f"- {item}" for item in template.architecture)
    lines.append("")
    lines.append("Archetypes:")
    lines.extend(f"- {item}" for item in template.archetypes)
    lines.append("")
    lines.append("Validation:")
    lines.extend(f"- {item}" for item in template.validation)
    if template.non_goals:
        lines.append("")
        lines.append("Non-goals:")
        lines.extend(f"- {item}" for item in template.non_goals)
    return "\n".join(lines)

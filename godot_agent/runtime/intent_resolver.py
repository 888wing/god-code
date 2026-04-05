"""Gameplay intent inference and confirmation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.project import parse_project_godot
from godot_agent.runtime.design_memory import (
    CombatProfile,
    DesignMemory,
    GameplayIntentProfile,
    gameplay_intent_from_data,
)


@dataclass(frozen=True)
class IntentOption:
    value: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class IntentQuestion:
    key: str
    prompt: str
    options: list[IntentOption] = field(default_factory=list)


_GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bullet_hell": ("bullet", "projectile", "boss", "wave", "danmaku", "barrage", "graze", "shmup"),
    "topdown_shooter": ("shooter", "enemy", "arena", "fire", "shoot", "weapon"),
    "platformer_enemy": ("jump", "platform", "ledge", "floor", "gravity", "patrol"),
    "tower_defense": ("tower", "turret", "lane", "defense", "defend", "base", "path"),
    "stealth_guard": ("stealth", "guard", "alert", "vision", "patrol", "search", "suspicious"),
}

_GAMEPLAY_TASK_KEYWORDS = (
    "enemy",
    "boss",
    "combat",
    "weapon",
    "shoot",
    "bullet",
    "wave",
    "pattern",
    "ai",
    "patrol",
    "chase",
    "tower",
    "turret",
    "stealth",
    "platform",
)

_GENRE_TO_SKILLS: dict[str, tuple[str, ...]] = {
    "bullet_hell": ("bullet_hell",),
    "topdown_shooter": ("topdown_shooter",),
    "platformer_enemy": ("platformer_enemy",),
    "tower_defense": ("tower_defense",),
    "stealth_guard": ("stealth_guard",),
}


_cached_tokens: tuple[set[str], set[str], tuple[int, int]] | None = None
_cache_project_root: Path | None = None


def clear_token_cache() -> None:
    """Reset the token cache. Useful for tests and when the project changes."""
    global _cached_tokens, _cache_project_root
    _cached_tokens = None
    _cache_project_root = None


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9_]+", value.lower()) if token}


def _project_signal_tokens(project_root: Path) -> tuple[set[str], set[str], tuple[int, int]]:
    global _cached_tokens, _cache_project_root
    if _cached_tokens is not None and _cache_project_root == project_root:
        return _cached_tokens

    tokens: set[str] = set()
    input_actions: set[str] = set()
    viewport = (1920, 1080)

    project_file = project_root / "project.godot"
    if project_file.exists():
        project = parse_project_godot(project_file)
        viewport = (project.viewport_width, project.viewport_height)
        tokens.update(_tokenize(project.name))
        tokens.update(_tokenize(project.main_scene))
        input_section = project.raw_sections.get("input", {})
        input_actions.update(input_section.keys())
        tokens.update(_tokenize(" ".join(input_section.keys())))

    file_tokens: set[str] = set()
    for path in project_root.rglob("*"):
        if ".godot" in path.parts:
            continue
        if path.is_file():
            relative = path.relative_to(project_root).as_posix()
            file_tokens.update(_tokenize(relative))
            if len(file_tokens) > 2000:
                break
    tokens.update(file_tokens)
    result = tokens, input_actions, viewport
    _cached_tokens = result
    _cache_project_root = project_root
    return result


def _score_genres(user_hint: str, tokens: set[str], input_actions: set[str], viewport: tuple[int, int]) -> dict[str, float]:
    hint_tokens = _tokenize(user_hint)
    combined = set(tokens) | hint_tokens
    scores: dict[str, float] = {genre: 0.0 for genre in _GENRE_KEYWORDS}

    for genre, keywords in _GENRE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                scores[genre] += 2.0
            if keyword in hint_tokens:
                scores[genre] += 3.0

    if {"shoot", "fire"} & input_actions:
        scores["bullet_hell"] += 2.0
        scores["topdown_shooter"] += 2.0
    if {"move_up", "move_down", "up", "down"} & input_actions:
        scores["bullet_hell"] += 2.0
        scores["topdown_shooter"] += 1.0
    if {"jump"} & input_actions:
        scores["platformer_enemy"] += 4.0
    if {"place_turret", "build_tower"} & input_actions:
        scores["tower_defense"] += 5.0
    if viewport[1] > viewport[0]:
        scores["bullet_hell"] += 1.5

    if {"boss", "wave"} <= combined:
        scores["bullet_hell"] += 2.0
    if {"tower", "turret"} & combined and {"shoot", "bullet"} & combined:
        scores["tower_defense"] += 2.0
        scores["bullet_hell"] += 1.0

    return scores


def _profile_for_genre(genre: str, viewport: tuple[int, int], input_actions: set[str]) -> GameplayIntentProfile:
    if genre == "bullet_hell":
        free_dodge = bool({"move_up", "move_down", "up", "down"} & input_actions)
        return GameplayIntentProfile(
            genre=genre,
            camera_model="vertical_scroller" if viewport[1] > viewport[0] else "single_screen_shooter",
            player_control_model="free_2d_dodge" if free_dodge else "horizontal_lane_dodge",
            combat_model="pattern_survival",
            enemy_model="scripted_patterns",
            boss_model="phase_based",
            testing_focus=["wave_timing", "pattern_readability", "boss_phase_clear"],
            combat_profile=CombatProfile(
                player_space_model="free_2d_dodge" if free_dodge else "horizontal_lane_dodge",
                density_curve="ramp_up",
                readability_target="clear_dense",
                bullet_cleanup_policy="phase_transition_and_timeout",
                phase_style="telegraphed",
            ),
        )
    if genre == "topdown_shooter":
        return GameplayIntentProfile(
            genre=genre,
            camera_model="topdown_arena",
            player_control_model="free_2d_shooting",
            combat_model="pressure_and_targeting",
            enemy_model="reactive_ranged",
            boss_model="attack_cycles",
            testing_focus=["spawn_pressure", "targeting", "combat_clarity"],
            combat_profile=CombatProfile(
                player_space_model="free_2d_shooting",
                density_curve="steady_pressure",
                readability_target="reactive_clear",
                bullet_cleanup_policy="lifetime_timeout",
                phase_style="attack_cycles",
            ),
        )
    if genre == "platformer_enemy":
        return GameplayIntentProfile(
            genre=genre,
            camera_model="side_scroller",
            player_control_model="run_jump",
            combat_model="spacing_and_timing",
            enemy_model="state_machine",
            boss_model="arena_states",
            testing_focus=["patrol_edges", "jump_collisions", "attack_windows"],
            combat_profile=CombatProfile(
                player_space_model="lane_and_height_control",
                density_curve="encounter_spikes",
                readability_target="timing_windows",
                bullet_cleanup_policy="despawn_on_range",
                phase_style="arena_state_swaps",
            ),
        )
    if genre == "tower_defense":
        return GameplayIntentProfile(
            genre=genre,
            camera_model="lane_overview",
            player_control_model="placement_and_support",
            combat_model="lane_control",
            enemy_model="path_followers",
            boss_model="lane_pressure_spikes",
            testing_focus=["path_following", "target_priority", "wave_balance"],
            combat_profile=CombatProfile(
                player_space_model="lane_management",
                density_curve="wave_escalation",
                readability_target="lane_clarity",
                bullet_cleanup_policy="despawn_on_goal_or_death",
                phase_style="wave_spikes",
            ),
        )
    if genre == "stealth_guard":
        return GameplayIntentProfile(
            genre=genre,
            camera_model="room_navigation",
            player_control_model="stealth_navigation",
            combat_model="avoidance_and_exposure",
            enemy_model="perception_state_machine",
            boss_model="alert_phases",
            testing_focus=["line_of_sight", "alert_decay", "search_loops"],
            combat_profile=CombatProfile(
                player_space_model="cover_and_sightlines",
                density_curve="low_visible_pressure",
                readability_target="alert_signals",
                bullet_cleanup_policy="n/a",
                phase_style="alert_escalation",
            ),
        )
    return GameplayIntentProfile()


def _detect_conflicts(scores: dict[str, float], tokens: set[str], memory: DesignMemory | None) -> list[str]:
    conflicts: list[str] = []
    ranked = sorted(((score, genre) for genre, score in scores.items()), reverse=True)
    if len(ranked) >= 2 and ranked[0][0] > 0 and ranked[1][0] > 0 and abs(ranked[0][0] - ranked[1][0]) <= 2.0:
        conflicts.append(f"mixed genre signals: {ranked[0][1]} vs {ranked[1][1]}")
    if {"tower", "turret"} & tokens and {"bullet", "boss", "wave"} & tokens:
        conflicts.append("project mixes turret-defense and shooter signals")
    confirmed = memory.gameplay_intent if memory else GameplayIntentProfile()
    if confirmed.confirmed and confirmed.genre and ranked and ranked[0][1] != confirmed.genre and ranked[0][0] >= 4.0:
        conflicts.append(f"confirmed genre {confirmed.genre} differs from current signals ({ranked[0][1]})")
    return conflicts


def resolve_gameplay_intent(
    project_root: Path,
    *,
    user_hint: str = "",
    design_memory: DesignMemory | None = None,
    recent_files: list[str] | None = None,
) -> GameplayIntentProfile:
    memory = design_memory or DesignMemory()
    tokens, input_actions, viewport = _project_signal_tokens(project_root)
    if recent_files:
        tokens.update(_tokenize(" ".join(recent_files)))
    scores = _score_genres(user_hint, tokens, input_actions, viewport)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_genre, top_score = ranked[0]

    if memory.gameplay_intent.confirmed and memory.gameplay_intent.genre:
        profile = gameplay_intent_from_data(memory.gameplay_intent.to_dict())
        profile.reasons = [*profile.reasons, "Using confirmed gameplay intent from design memory."]
        profile.conflicts = _detect_conflicts(scores, tokens, memory)
        profile.confidence = max(profile.confidence, 1.0 if not profile.conflicts else 0.7)
        return profile

    if top_score <= 0:
        return GameplayIntentProfile()

    profile = _profile_for_genre(top_genre, viewport, input_actions)
    if profile.is_empty:
        return profile

    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    evidence = max(top_score, 0.0)
    confidence = 0.0
    if evidence > 0:
        confidence = min(0.95, 0.45 + evidence * 0.08 - max(0.0, (second_score - 1.0)) * 0.03)
    profile.confidence = round(max(0.0, confidence), 2)
    profile.reasons = [
        f"Top genre signal: {top_genre} ({top_score:.1f})",
        f"Viewport: {viewport[0]}x{viewport[1]}",
    ]
    if input_actions:
        profile.reasons.append("Input actions: " + ", ".join(sorted(input_actions)[:8]))
    profile.conflicts = _detect_conflicts(scores, tokens, memory)
    return profile


def format_gameplay_intent(profile: GameplayIntentProfile) -> str:
    if profile.is_empty:
        return "No gameplay intent inferred yet."
    lines = ["## Gameplay Intent"]
    if profile.genre:
        lines.append(f"- Genre: {profile.genre}")
    if profile.camera_model:
        lines.append(f"- Camera: {profile.camera_model}")
    if profile.player_control_model:
        lines.append(f"- Player Control: {profile.player_control_model}")
    if profile.combat_model:
        lines.append(f"- Combat: {profile.combat_model}")
    if profile.enemy_model:
        lines.append(f"- Enemy Model: {profile.enemy_model}")
    if profile.boss_model:
        lines.append(f"- Boss Model: {profile.boss_model}")
    if profile.testing_focus:
        lines.append(f"- Testing Focus: {', '.join(profile.testing_focus)}")
    if not profile.combat_profile.is_empty:
        lines.append("- Combat Profile:")
        if profile.combat_profile.player_space_model:
            lines.append(f"  - Player Space: {profile.combat_profile.player_space_model}")
        if profile.combat_profile.density_curve:
            lines.append(f"  - Density Curve: {profile.combat_profile.density_curve}")
        if profile.combat_profile.readability_target:
            lines.append(f"  - Readability: {profile.combat_profile.readability_target}")
        if profile.combat_profile.bullet_cleanup_policy:
            lines.append(f"  - Bullet Cleanup: {profile.combat_profile.bullet_cleanup_policy}")
        if profile.combat_profile.phase_style:
            lines.append(f"  - Phase Style: {profile.combat_profile.phase_style}")
    lines.append(f"- Confirmed: {'yes' if profile.confirmed else 'no'}")
    lines.append(f"- Confidence: {profile.confidence:.2f}")
    if profile.conflicts:
        lines.append(f"- Conflicts: {', '.join(profile.conflicts)}")
    if profile.reasons:
        lines.append("- Reasons: " + " | ".join(profile.reasons[:4]))
    return "\n".join(lines)


def gameplay_profile_to_skill_keys(profile: GameplayIntentProfile | None) -> list[str]:
    if profile is None or not profile.genre:
        return []
    return list(_GENRE_TO_SKILLS.get(profile.genre, ()))


def is_gameplay_architecture_task(user_hint: str) -> bool:
    hint_lower = user_hint.lower()
    return any(keyword in hint_lower for keyword in _GAMEPLAY_TASK_KEYWORDS)


def should_prompt_for_intent(profile: GameplayIntentProfile | None, *, user_hint: str = "") -> bool:
    if profile is None or profile.is_empty or profile.confirmed:
        return False if profile and profile.confirmed else bool(user_hint and is_gameplay_architecture_task(user_hint))
    if profile.conflicts:
        return True
    if not user_hint:
        return profile.confidence < 0.65
    if is_gameplay_architecture_task(user_hint):
        return profile.confidence < 0.8
    return False


def intent_questions_for_profile(profile: GameplayIntentProfile) -> list[IntentQuestion]:
    genre_options = [
        IntentOption("bullet_hell", "Bullet Hell", "Scripted waves, readable patterns, boss phases."),
        IntentOption("topdown_shooter", "Top-Down Shooter", "Reactive combat and pressure-based enemies."),
        IntentOption("platformer_enemy", "Platformer", "Patrol/chase/attack state-machine enemies."),
        IntentOption("tower_defense", "Tower Defense", "Lane control, path-following, and wave pressure."),
        IntentOption("stealth_guard", "Stealth", "Vision, alert, search, and patrol loops."),
    ]
    control_options = [
        IntentOption("free_2d_dodge", "Free 2D Dodge", "Full dodge movement in two dimensions."),
        IntentOption("horizontal_lane_dodge", "Left/Right Dodge", "Horizontal evasion only."),
        IntentOption("run_jump", "Run and Jump", "Platforming movement with jumps and ledges."),
        IntentOption("placement_and_support", "Placement", "Build or support focused controls."),
        IntentOption("stealth_navigation", "Stealth Movement", "Slow movement with exposure management."),
    ]
    enemy_options = [
        IntentOption("scripted_patterns", "Scripted Patterns", "Enemy behavior comes from wave choreography and patterns."),
        IntentOption("reactive_ranged", "Reactive Shooter AI", "Enemies react to player position and pressure."),
        IntentOption("state_machine", "State Machine", "Patrol/chase/attack behavior states."),
        IntentOption("path_followers", "Path Followers", "Enemies follow lanes or authored paths."),
        IntentOption("perception_state_machine", "Perception AI", "Guards react to line-of-sight and alert states."),
    ]

    questions = [
        IntentQuestion(
            key="genre",
            prompt="Which gameplay direction should God Code follow for this project?",
            options=genre_options,
        ),
        IntentQuestion(
            key="player_control_model",
            prompt="Which player control model should drive gameplay assumptions?",
            options=control_options,
        ),
        IntentQuestion(
            key="enemy_model",
            prompt="What enemy behavior model should the agent optimize for?",
            options=enemy_options,
        ),
    ]

    if profile.genre:
        preferred = profile.genre
        questions[0] = IntentQuestion(
            key="genre",
            prompt=f"I currently infer `{preferred}`. Keep this direction?",
            options=genre_options,
        )
    return questions


def apply_intent_answers(
    base_profile: GameplayIntentProfile,
    answers: dict[str, str],
) -> GameplayIntentProfile:
    genre = answers.get("genre", base_profile.genre)
    profile_defaults = _profile_for_genre(
        genre,
        viewport=(480, 800) if base_profile.camera_model == "vertical_scroller" else (1920, 1080),
        input_actions=set(),
    )
    same_genre = not genre or genre == base_profile.genre
    resolved = GameplayIntentProfile(
        genre=genre or profile_defaults.genre or base_profile.genre,
        camera_model=answers.get(
            "camera_model",
            base_profile.camera_model if same_genre and base_profile.camera_model else profile_defaults.camera_model or base_profile.camera_model,
        ),
        player_control_model=answers.get(
            "player_control_model",
            base_profile.player_control_model if same_genre and base_profile.player_control_model else profile_defaults.player_control_model or base_profile.player_control_model,
        ),
        combat_model=answers.get(
            "combat_model",
            base_profile.combat_model if same_genre and base_profile.combat_model else profile_defaults.combat_model or base_profile.combat_model,
        ),
        enemy_model=answers.get(
            "enemy_model",
            base_profile.enemy_model if same_genre and base_profile.enemy_model else profile_defaults.enemy_model or base_profile.enemy_model,
        ),
        boss_model=answers.get(
            "boss_model",
            base_profile.boss_model if same_genre and base_profile.boss_model else profile_defaults.boss_model or base_profile.boss_model,
        ),
        testing_focus=list(
            base_profile.testing_focus if same_genre and base_profile.testing_focus else profile_defaults.testing_focus or base_profile.testing_focus
        ),
        combat_profile=(
            base_profile.combat_profile
            if same_genre and not base_profile.combat_profile.is_empty
            else profile_defaults.combat_profile if not profile_defaults.combat_profile.is_empty else base_profile.combat_profile
        ),
        reasons=[*base_profile.reasons, "Confirmed via TUI intent checkpoint."],
        conflicts=[],
        confirmed=True,
        confidence=1.0,
    )
    return resolved

"""Selects high-signal prompt skills for the current task."""

from __future__ import annotations

from collections import OrderedDict

from godot_agent.prompts.skill_library import SKILLS, PromptSkill
from godot_agent.runtime.design_memory import GameplayIntentProfile
from godot_agent.runtime.intent_resolver import gameplay_profile_to_skill_keys

_EXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    ".gd": ("physics", "movement", "_physics_process", "characterbody"),
    ".tscn": ("collision", "layer", "mask", "area2d", "physicsbody"),
}

_VERB_KEYWORDS: dict[str, tuple[str, ...]] = {
    "move": ("physics", "movement", "velocity", "characterbody"),
    "jump": ("physics", "jump", "gravity"),
    "collision": ("collision", "layer", "mask", "hitbox"),
    "bullet": ("collision", "projectile", "mask"),
    "trigger": ("collision", "trigger", "area2d"),
    "physics": ("physics", "_physics_process", "rigidbody"),
    "ui": ("ui", "layout", "hud", "menu"),
    "animate": ("animation", "spriteframes", "animationplayer", "tween"),
    "transition": ("transition", "scene", "change_scene", "loading"),
    "save": ("save", "load", "state", "user://"),
    "load": ("save", "load", "scene", "transition"),
}

SKILL_MODES = ("auto", "manual", "hybrid")
_SKILL_BY_KEY = {skill.key: skill for skill in SKILLS}
_FOUNDATION_TOOLS = {
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "grep",
    "glob",
    "read_script",
    "edit_script",
    "lint_script",
    "read_scene",
    "scene_tree",
    "add_scene_node",
    "write_scene_property",
    "add_scene_connection",
    "remove_scene_node",
    "validate_project",
    "check_consistency",
    "project_dependency_graph",
    "analyze_impact",
    "plan_ui_layout",
    "validate_ui_layout",
    "scaffold_audio",
    "validate_audio_nodes",
    "read_design_memory",
    "update_design_memory",
}


def available_skills() -> tuple[PromptSkill, ...]:
    return SKILLS


def normalize_skill_mode(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    if normalized not in SKILL_MODES:
        allowed = ", ".join(SKILL_MODES)
        raise ValueError(f"Unknown skill mode: {value}. Allowed: {allowed}")
    return normalized


def normalize_skill_name(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().lower().replace("_", " ").split())
    if not normalized:
        return None

    for skill in SKILLS:
        tokens = {
            skill.key,
            skill.name.lower(),
            *(alias.lower() for alias in skill.aliases),
        }
        if normalized in tokens:
            return skill.key
    return None


def skill_for_key(skill_key: str) -> PromptSkill | None:
    return _SKILL_BY_KEY.get(skill_key)


def skill_label(skill_key: str) -> str:
    skill = skill_for_key(skill_key)
    return skill.name if skill else skill_key


def sanitize_skill_keys(skill_keys: list[str] | None) -> list[str]:
    ordered: OrderedDict[str, None] = OrderedDict()
    for raw_value in skill_keys or []:
        normalized = normalize_skill_name(raw_value)
        if normalized is not None:
            ordered[normalized] = None
    return list(ordered)


def select_skills(
    user_prompt: str,
    file_paths: list[str] | None = None,
    max_skills: int = 2,
    intent_profile: GameplayIntentProfile | None = None,
) -> list[PromptSkill]:
    prompt_lower = user_prompt.lower()
    intent_skill_keys = set(gameplay_profile_to_skill_keys(intent_profile))

    ext_bonus: set[str] = set()
    if file_paths:
        for path in file_paths:
            for ext, keywords in _EXT_KEYWORDS.items():
                if path.endswith(ext):
                    ext_bonus.update(keywords)

    verb_bonus: set[str] = set()
    for verb, keywords in _VERB_KEYWORDS.items():
        if verb in prompt_lower:
            verb_bonus.update(keywords)

    scored: list[tuple[float, PromptSkill]] = []
    for skill in SKILLS:
        score = 0.0
        if skill.key in intent_skill_keys:
            score += 10.0
        for keyword in skill.keywords:
            if keyword in prompt_lower:
                score += 2.0
            if keyword in ext_bonus:
                score += 1.0
            if keyword in verb_bonus:
                score += 3.0
        scored.append((score, skill))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [skill for score, skill in scored[:max_skills] if score > 0]


def resolve_skills(
    user_prompt: str,
    file_paths: list[str] | None = None,
    *,
    max_skills: int = 2,
    skill_mode: str = "auto",
    enabled_skills: list[str] | None = None,
    disabled_skills: list[str] | None = None,
    intent_profile: GameplayIntentProfile | None = None,
) -> list[PromptSkill]:
    mode = normalize_skill_mode(skill_mode)
    enabled = [skill_for_key(skill_key) for skill_key in sanitize_skill_keys(enabled_skills)]
    enabled = [skill for skill in enabled if skill is not None]
    disabled = set(sanitize_skill_keys(disabled_skills))

    auto_skills = select_skills(user_prompt, file_paths, max_skills=max_skills, intent_profile=intent_profile)
    if mode == "manual":
        combined = enabled
    elif mode == "hybrid":
        combined = [*auto_skills, *enabled]
    else:
        combined = auto_skills

    ordered: OrderedDict[str, PromptSkill] = OrderedDict()
    for skill in combined:
        if skill.key in disabled:
            continue
        ordered[skill.key] = skill
    return list(ordered.values())


def format_skill_injection(skills: list[PromptSkill]) -> str:
    if not skills:
        return ""
    parts = ["## Active Skills", ""]
    for skill in skills:
        parts.append(f"### {skill.name}")
        parts.append(skill.content)
        parts.append("")
    return "\n".join(parts)


def narrow_tools_for_skills(
    skills: list[PromptSkill],
    base_allowed_tools: set[str] | None,
) -> set[str] | None:
    if base_allowed_tools is None:
        return None
    if not skills:
        return set(base_allowed_tools)

    narrowed: set[str] = set(base_allowed_tools) & _FOUNDATION_TOOLS
    for skill in skills:
        narrowed.update(skill.tool_names)
    scoped = set(base_allowed_tools) & narrowed
    # Skill narrowing is a hint, not a hard lockout. If the overlap would
    # remove the entire mode-level tool scope, keep the original scope.
    return scoped or set(base_allowed_tools)

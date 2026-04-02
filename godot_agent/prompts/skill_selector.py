"""Selects high-signal prompt skills for the current task."""

from __future__ import annotations

from godot_agent.prompts.skill_library import SKILLS, PromptSkill

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
}


def select_skills(
    user_prompt: str,
    file_paths: list[str] | None = None,
    max_skills: int = 2,
) -> list[PromptSkill]:
    prompt_lower = user_prompt.lower()

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

    narrowed: set[str] = set()
    for skill in skills:
        narrowed.update(skill.tool_names)
    return set(base_allowed_tools) & narrowed

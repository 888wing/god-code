"""Selects relevant Playbook sections based on task context.

Avoids injecting the full ~15K token playbook. Instead, scores each section
by keyword overlap with the user's prompt and current file types, then returns
the top-N most relevant sections.
"""

from __future__ import annotations

from godot_agent.prompts.godot_playbook import SECTIONS

# Map file extensions to relevant section keywords
_EXT_KEYWORDS: dict[str, list[str]] = {
    ".gd": ["style", "type", "signal", "lifecycle", "naming"],
    ".tscn": ["node", "scene", "collision", "area"],
    ".tres": ["resource", "data", "export"],
    ".gdshader": ["shader"],
    ".cfg": ["project", "input"],
}

# Map common task verbs to relevant keywords
_VERB_KEYWORDS: dict[str, list[str]] = {
    "move": ["physics", "characterbody", "input", "movement"],
    "shoot": ["physics", "collision", "pool", "area"],
    "bullet": ["pool", "collision", "area", "performance"],
    "ui": ["ui", "control", "layout", "container", "theme"],
    "enemy": ["collision", "area", "pattern", "state_machine", "component"],
    "boss": ["state_machine", "pattern", "animation", "collision"],
    "save": ["save", "resource", "data"],
    "animation": ["animation", "tween", "animationplayer"],
    "collision": ["collision", "layer", "mask", "physics"],
    "scene": ["scene", "node", "structure"],
    "autoload": ["autoload", "global", "singleton", "manager"],
    "signal": ["signal", "emit", "connect"],
    "export": ["export", "inspector", "range"],
    "performance": ["performance", "optimize", "pool", "cache"],
    "debug": ["error", "mistake", "bug", "trap"],
    "create": ["structure", "node", "scene", "style"],
    "fix": ["error", "mistake", "bug", "trap"],
}


def select_sections(
    user_prompt: str,
    file_paths: list[str] | None = None,
    max_sections: int = 4,
) -> list[tuple[str, str]]:
    """Return (title, content) pairs for the most relevant Playbook sections.

    Scoring:
    - +2 for each keyword match in user prompt
    - +1 for each keyword match from file extensions
    - +3 for verb-keyword matches (strongest signal)
    """
    prompt_lower = user_prompt.lower()

    # Collect bonus keywords from file extensions
    ext_bonus: set[str] = set()
    if file_paths:
        for fp in file_paths:
            for ext, kws in _EXT_KEYWORDS.items():
                if fp.endswith(ext):
                    ext_bonus.update(kws)

    # Collect bonus keywords from verbs in prompt
    verb_bonus: set[str] = set()
    for verb, kws in _VERB_KEYWORDS.items():
        if verb in prompt_lower:
            verb_bonus.update(kws)

    scored: list[tuple[float, str, str]] = []
    for title, keywords, content in SECTIONS:
        score = 0.0
        for kw in keywords:
            if kw in prompt_lower:
                score += 2.0
            if kw in ext_bonus:
                score += 1.0
            if kw in verb_bonus:
                score += 3.0
        scored.append((score, title, content.strip()))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Always include Common Mistakes if score > 0 (as safety net)
    result: list[tuple[str, str]] = []
    included_titles: set[str] = set()
    for score, title, content in scored[:max_sections]:
        if score > 0:
            result.append((title, content))
            included_titles.add(title)

    # Ensure Common Mistakes is always included as safety net
    if "Common Mistakes" not in included_titles and len(result) < max_sections:
        for _, title, content in scored:
            if title == "Common Mistakes":
                result.append((title, content))
                break

    return result


def format_knowledge_injection(sections: list[tuple[str, str]]) -> str:
    """Format selected sections for system prompt injection."""
    if not sections:
        return ""
    parts = ["## Godot Knowledge (auto-selected)", ""]
    for title, content in sections:
        parts.append(f"### {title}")
        parts.append(content)
        parts.append("")
    return "\n".join(parts)

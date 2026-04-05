# godot_agent/cli/helpers.py
"""Small utility functions shared across the CLI package."""
from __future__ import annotations

import html
from pathlib import Path

from godot_agent.prompts.skill_selector import (
    resolve_skills,
    skill_label,
)
from godot_agent.runtime.config import AgentConfig
from godot_agent.runtime.design_memory import (
    GameplayIntentProfile,
    resolved_asset_spec,
    resolved_polish_profile,
    resolved_quality_target,
    update_design_memory,
)
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.modes import get_mode_spec
from godot_agent.runtime.session import save_session


# ── tiny parsers ────────────────────────────────────────────────

def _has_meaningful_input(value: str) -> bool:
    return any(ch.isprintable() and not ch.isspace() for ch in value)


def _command_argument(value: str, command: str) -> str | None:
    stripped = value.strip()
    if stripped == command:
        return ""
    prefix = f"{command} "
    if not stripped.startswith(prefix):
        return None
    parts = stripped.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _set_arguments(value: str) -> tuple[str, str] | None:
    stripped = value.strip()
    if stripped == "/set":
        return None
    if not stripped.startswith("/set "):
        return None
    parts = stripped.split(None, 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _cd_argument(value: str) -> str | None:
    for command in ("/cd", "cd"):
        arg = _command_argument(value, command)
        if arg is not None:
            return arg
    return None


def _starts_multiline_input(value: str) -> bool:
    return value.strip().startswith('"""')


def _multiline_initial_fragment(value: str) -> str:
    stripped = value.strip()
    return stripped[3:] if stripped.startswith('"""') else ""


def _is_multiline_terminator(value: str | None) -> bool:
    return value is None or value.strip() == '"""'


# ── project / workspace ────────────────────────────────────────

def _project_details(project_root: Path) -> tuple[bool, str | None, dict[str, str]]:
    info = {
        "Main Scene": "-",
        "Resolution": "-",
        "Autoloads": "-",
        "Guide": "-",
        "File Count": "-",
    }
    project_file = project_root / "project.godot"
    if not project_file.exists():
        return False, None, info

    from godot_agent.godot.project import parse_project_godot

    proj = parse_project_godot(project_file)
    info.update({
        "Main Scene": proj.main_scene or "-",
        "Resolution": f"{proj.viewport_width}x{proj.viewport_height}",
        "Autoloads": str(len(proj.autoloads)),
    })
    return True, proj.name, info


def _toolbar_markup(
    cfg: AgentConfig,
    project_root: Path,
    project_name: str | None,
    intent_genre: str = "-",
    quality_target: str = "prototype",
) -> str:
    mode_label = html.escape(get_mode_spec(cfg.mode).label)
    provider = html.escape(cfg.provider)
    model = html.escape(cfg.model)
    effort = html.escape(cfg.reasoning_effort)
    skill_mode = html.escape(cfg.skill_mode)
    project = html.escape(project_name or project_root.name or str(project_root))
    intent = html.escape(intent_genre or "-")
    quality = html.escape(quality_target or "prototype")
    return (
        f"<b>mode</b>: {mode_label} | "
        f"<b>provider</b>: {provider} | "
        f"<b>model</b>: {model} | "
        f"<b>effort</b>: {effort} | "
        f"<b>skills</b>: {skill_mode} | "
        f"<b>intent</b>: {intent} | "
        f"<b>quality</b>: {quality} | "
        f"<b>project</b>: {project} | "
        "<b>triple quotes</b>: multiline | "
        "<b>/help</b>"
    )


# ── skill helpers ──────────────────────────────────────────────

def _resolved_active_skill_keys(engine: ConversationEngine, cfg: AgentConfig) -> list[str]:
    skills = resolve_skills(
        engine.last_user_input,
        engine._recent_context_files(),
        skill_mode=cfg.skill_mode,
        enabled_skills=cfg.enabled_skills,
        disabled_skills=cfg.disabled_skills,
        intent_profile=engine.intent_profile,
    )
    return [skill.key for skill in skills]


def _format_skill_list(skill_keys: list[str]) -> str:
    if not skill_keys:
        return "-"
    return ", ".join(skill_label(skill_key) for skill_key in skill_keys)


# ── intent / quality / asset helpers ───────────────────────────

def _intent_profile_dict(engine: ConversationEngine) -> dict[str, object]:
    return engine.intent_profile.to_dict()


def _quality_target(engine: ConversationEngine) -> str:
    memory = getattr(engine, "design_memory", None)
    return resolved_quality_target(memory)


def _asset_spec_dict(engine: ConversationEngine) -> dict[str, object]:
    memory = getattr(engine, "design_memory", None)
    return resolved_asset_spec(memory).to_dict()


def _polish_profile_dict(engine: ConversationEngine) -> dict[str, object]:
    memory = getattr(engine, "design_memory", None)
    return resolved_polish_profile(memory, quality_target=_quality_target(engine)).to_dict()


def _format_intent_inline(profile: dict[str, object]) -> str:
    genre = str(profile.get("genre", "") or "-")
    enemy = str(profile.get("enemy_model", "") or "-")
    confirmed = "confirmed" if profile.get("confirmed") else "inferred"
    return f"{genre} | {enemy} | {confirmed}"


def _persist_intent_profile(project_root: Path, profile: GameplayIntentProfile) -> None:
    update_design_memory(
        project_root,
        section="gameplay_intent",
        mapping=profile.to_dict(),
    )


# ── session helpers ────────────────────────────────────────────

def _save_chat_session(
    cfg: AgentConfig,
    session_id: str,
    engine: ConversationEngine,
    project_root: Path,
    project_name: str | None,
) -> Path:
    return save_session(
        cfg.session_dir,
        session_id,
        engine.messages,
        project_path=str(project_root),
        project_name=project_name,
        model=cfg.model,
        mode=cfg.mode,
        skill_mode=cfg.skill_mode,
        enabled_skills=cfg.enabled_skills,
        disabled_skills=cfg.disabled_skills,
        active_skills=_resolved_active_skill_keys(engine, cfg),
        gameplay_intent=_intent_profile_dict(engine),
    )

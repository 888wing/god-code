# godot_agent/cli/menus.py
"""Menu option builders for the interactive TUI."""
from __future__ import annotations

from godot_agent.prompts.skill_selector import available_skills
from godot_agent.runtime.config import AgentConfig
from godot_agent.runtime.modes import get_mode_spec
from godot_agent.runtime.providers import PROVIDER_PRESETS, REASONING_EFFORT_LEVELS
from godot_agent.tui.input_handler import MenuOption


# ── menu option factories ──────────────────────────────────────

def _mode_menu_options() -> list[MenuOption]:
    return [
        MenuOption(name, get_mode_spec(name).label, get_mode_spec(name).description)
        for name in ("apply", "plan", "explain", "review", "fix")
    ]


def _provider_menu_options() -> list[MenuOption]:
    return [
        MenuOption(
            provider,
            preset.name,
            preset.model or "Custom API configuration",
            aliases=(provider,),
        )
        for provider, preset in PROVIDER_PRESETS.items()
    ]


def _effort_menu_options() -> list[MenuOption]:
    descriptions = {
        "auto": "Let the provider decide.",
        "minimal": "Fastest possible reasoning.",
        "low": "Light reasoning for straightforward work.",
        "medium": "Balanced depth and latency.",
        "high": "Deeper reasoning for harder tasks.",
        "xhigh": "Maximum reasoning depth.",
    }
    return [
        MenuOption(level, level, descriptions.get(level, ""))
        for level in REASONING_EFFORT_LEVELS
    ]


def _model_menu_options(cfg: AgentConfig) -> list[MenuOption]:
    options: list[MenuOption] = []
    seen: set[str] = set()

    def add(value: str, label: str, description: str, aliases: tuple[str, ...] = ()) -> None:
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        options.append(MenuOption(normalized, label, description, aliases=aliases))

    add(cfg.model, f"{cfg.model}", "Current model", aliases=("current",))
    preset = PROVIDER_PRESETS.get(cfg.provider)
    if preset and preset.model and preset.model != cfg.model:
        add(preset.model, f"{preset.model}", f"{preset.name} default model", aliases=("default",))
    add("__custom__", "Custom model...", "Type any model identifier manually", aliases=("custom", "manual"))
    return options


def _skill_menu_options() -> list[MenuOption]:
    return [
        MenuOption(skill.key, skill.name, skill.summary, aliases=skill.aliases)
        for skill in available_skills()
    ]


def _settings_menu_options() -> list[MenuOption]:
    descriptions = {
        "api_key": "Update the provider API key (hidden input).",
        "provider": "Switch provider family and default base URL/model.",
        "base_url": "Edit the API base URL manually.",
        "model": "Switch the active model name.",
        "reasoning_effort": "Change reasoning depth.",
        "computer_use": "Enable OpenAI Responses computer-use requests for compatible tooling.",
        "computer_use_environment": "Computer-use environment label (browser, desktop, vm).",
        "computer_use_display_width": "Computer-use display width in pixels.",
        "computer_use_display_height": "Computer-use display height in pixels.",
        "oauth_token": "Update the OAuth token (hidden input).",
        "max_turns": "Maximum tool-calling turns per request.",
        "max_tokens": "Maximum output tokens per request.",
        "temperature": "Sampling temperature for supported providers.",
        "godot_path": "Path to the Godot executable.",
        "language": "Preferred response language.",
        "verbosity": "Response detail level.",
        "mode": "Change interaction mode.",
        "auto_validate": "Toggle post-change validation.",
        "auto_commit": "Toggle commit suggestion after edits.",
        "screenshot_max_iterations": "Max screenshot stabilization attempts.",
        "token_budget": "Session token budget, 0 = unlimited.",
        "safety": "Shell safety policy.",
        "streaming": "Toggle streamed assistant output.",
        "autosave_session": "Persist chat state after each turn.",
        "extra_prompt": "Append custom system instructions.",
        "session_dir": "Directory used to store chat sessions.",
    }
    return [
        MenuOption(key, key, descriptions.get(key, ""))
        for key in (
            "api_key", "provider", "base_url", "model", "reasoning_effort", "oauth_token",
            "computer_use", "computer_use_environment", "computer_use_display_width", "computer_use_display_height",
            "max_turns", "max_tokens", "temperature", "godot_path",
            "language", "verbosity", "mode", "auto_validate", "auto_commit",
            "screenshot_max_iterations", "token_budget", "safety", "streaming",
            "autosave_session", "extra_prompt", "session_dir",
        )
    ]


def _boolean_menu_options() -> list[MenuOption]:
    return [
        MenuOption("true", "Enable", "Set the option to true.", aliases=("yes", "on", "1")),
        MenuOption("false", "Disable", "Set the option to false.", aliases=("no", "off", "0")),
    ]


def _language_menu_options() -> list[MenuOption]:
    return [
        MenuOption("en", "English", "Respond in English.", aliases=("english",)),
        MenuOption("zh-TW", "Traditional Chinese", "Respond in Traditional Chinese.", aliases=("zh", "zh-tw", "traditional chinese")),
        MenuOption("ja", "Japanese", "Respond in Japanese.", aliases=("jp", "japanese")),
    ]


def _verbosity_menu_options() -> list[MenuOption]:
    return [
        MenuOption("concise", "Concise", "Short, high-signal responses."),
        MenuOption("normal", "Normal", "Balanced detail."),
        MenuOption("detailed", "Detailed", "More explanation and context."),
    ]


def _safety_menu_options() -> list[MenuOption]:
    return [
        MenuOption("strict", "Strict", "Most conservative shell policy."),
        MenuOption("normal", "Normal", "Balanced shell policy."),
        MenuOption("permissive", "Permissive", "Looser shell policy."),
    ]


def _setting_value_menu_options(key: str) -> list[MenuOption] | None:
    if key == "mode":
        return _mode_menu_options()
    if key == "provider":
        return _provider_menu_options()
    if key == "reasoning_effort":
        return _effort_menu_options()
    if key in {"auto_validate", "auto_commit", "streaming", "autosave_session", "computer_use"}:
        return _boolean_menu_options()
    if key == "language":
        return _language_menu_options()
    if key == "verbosity":
        return _verbosity_menu_options()
    if key == "safety":
        return _safety_menu_options()
    return None


_SECRET_SETTING_KEYS = {"api_key", "oauth_token"}
_MULTILINE_SETTING_KEYS = {"extra_prompt"}


def _session_menu_options(records) -> list[MenuOption]:
    options: list[MenuOption] = []
    for record in records:
        subtitle = record.project_name or record.project_path or "-"
        description = f"{record.mode or '-'} | {subtitle} | {record.title or 'Untitled session'}"
        options.append(MenuOption(record.session_id, record.session_id, description, aliases=("latest",) if not options else ()))
    return options


def _main_menu_options() -> list[MenuOption]:
    return [
        MenuOption("mode", "Change mode", "Switch between apply, plan, explain, review, and fix."),
        MenuOption("provider", "Switch provider", "Pick an LLM provider preset."),
        MenuOption("model", "Switch model", "Pick the current/default model or enter one manually."),
        MenuOption("effort", "Set reasoning effort", "Adjust reasoning depth."),
        MenuOption("skills", "Manage skills", "Inspect or override the internal domain skills."),
        MenuOption("intent", "Gameplay intent", "Inspect or confirm gameplay direction."),
        MenuOption("quality", "Quality target", "Show whether the project is targeting prototype or demo output."),
        MenuOption("assetspec", "Asset spec", "Show current sprite and asset acceptance constraints."),
        MenuOption("playtest", "Run playtest", "Run scripted playtest contracts for the current project."),
        MenuOption("scenarios", "List scenarios", "Show built-in playtest scenarios and relevance."),
        MenuOption("contracts", "Show contracts", "Inspect scripted-route contract details."),
        MenuOption("resume", "Resume session", "Choose a saved session to restore."),
        MenuOption("cd", "Change project directory", "Switch the active project root."),
        MenuOption("set", "Edit setting", "Choose any config field and update it."),
        MenuOption("workspace", "Show workspace", "Refresh the workspace snapshot."),
        MenuOption("status", "Show status", "Provider, model, auth, and mode."),
        MenuOption("settings", "Show settings", "Current config values and descriptions."),
        MenuOption("sessions", "List sessions", "Show recent saved sessions."),
        MenuOption("help", "Show commands", "Render the command cheat sheet."),
        MenuOption("quit", "Quit", "Exit the chat session."),
    ]


def _mask_secret(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "(empty)"
    if len(stripped) <= 8:
        return "*" * len(stripped)
    return f"{stripped[:4]}...{stripped[-4:]}"


def _format_setting_display_value(key: str, value) -> str:
    if key in _SECRET_SETTING_KEYS:
        return _mask_secret(str(value))
    return str(value)

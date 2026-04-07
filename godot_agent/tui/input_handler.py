"""Rich input with history, auto-complete, and multi-line support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML

from godot_agent.prompts.skill_selector import available_skills
from godot_agent.runtime.providers import PROVIDER_PRESETS, REASONING_EFFORT_LEVELS


def _suffix_after_first_space(text: str) -> str:
    if " " not in text:
        return ""
    parts = text.split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def _normalize_choice_token(value: str) -> str:
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True)
class MenuOption:
    value: str
    label: str
    description: str = ""
    aliases: tuple[str, ...] = ()


def resolve_menu_choice(raw_value: str | None, options: list[MenuOption]) -> str | None:
    if raw_value is None:
        return None

    normalized = _normalize_choice_token(raw_value)
    if not normalized:
        return None

    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(options):
            return options[index].value
        return None

    for option in options:
        tokens = {
            _normalize_choice_token(option.value),
            _normalize_choice_token(option.label),
            *(_normalize_choice_token(alias) for alias in option.aliases),
        }
        if normalized in tokens:
            return option.value
    return None


class MenuCompleter(Completer):
    """Completion helper for menu selections."""

    def __init__(self, options: list[MenuOption]):
        self.options = options

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        normalized = _normalize_choice_token(text)

        for index, option in enumerate(self.options, start=1):
            tokens = [option.value, option.label, *option.aliases]
            if normalized.isdigit():
                tokens = [str(index), *tokens]
            for token in tokens:
                token_normalized = _normalize_choice_token(token)
                if normalized and not token_normalized.startswith(normalized):
                    continue
                yield Completion(
                    option.value if not normalized.isdigit() else str(index),
                    start_position=-len(text),
                    display=f"{index}. {option.label}",
                    display_meta=option.description,
                )
                break


class CommandCompleter(Completer):
    """Auto-complete for / commands and file paths."""

    COMMANDS = [
        ("/cd ", "change project directory"),
        ("/mode ", "change interaction mode"),
        ("/provider ", "show or switch provider"),
        ("/model ", "show or switch model"),
        ("/effort ", "show or switch reasoning effort"),
        ("/skills ", "list or override internal skills"),
        ("/intent ", "show or confirm gameplay intent"),
        ("/quality", "show the current project quality target"),
        ("/assetspec", "show the current asset constraints"),
        ("/playtest ", "run scripted or profile-selected playtests"),
        ("/scenarios", "list built-in playtest scenarios"),
        ("/contracts ", "show scripted-route scenario contracts"),
        ("/info", "show project details"),
        ("/status", "show provider, model, and auth"),
        ("/usage", "show token usage"),
        ("/settings", "show all settings"),
        ("/set ", "change a setting"),
        ("/sessions", "list saved sessions"),
        ("/resume ", "resume a session"),
        ("/new", "start a fresh session"),
        ("/save", "save session"),
        ("/load", "restore session"),
        ("/workspace", "show workspace snapshot"),
        ("/menu", "open interactive command menu"),
        ("/help", "show commands"),
        ("/quit", "exit"),
    ]

    SETTINGS = [
        "api_key", "base_url", "provider", "model", "reasoning_effort", "oauth_token",
        "computer_use", "computer_use_environment", "computer_use_display_width", "computer_use_display_height",
        "skill_mode", "enabled_skills", "disabled_skills",
        "max_turns", "max_tokens", "temperature", "godot_path",
        "language", "verbosity", "mode", "auto_validate", "auto_commit",
        "screenshot_max_iterations", "token_budget", "safety", "streaming",
        "autosave_session", "extra_prompt", "session_dir",
    ]

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # /set <key> completion
        if text.startswith("/set "):
            parts = text.split()
            if len(parts) == 2:
                prefix = parts[1]
                for s in self.SETTINGS:
                    if s.startswith(prefix):
                        yield Completion(s, start_position=-len(prefix))
            return

        if text.startswith("/provider "):
            prefix = _suffix_after_first_space(text)
            for provider in PROVIDER_PRESETS:
                if provider.startswith(prefix.lower()):
                    yield Completion(provider, start_position=-len(prefix))
            return

        if text.startswith("/effort "):
            prefix = _suffix_after_first_space(text)
            for effort in REASONING_EFFORT_LEVELS:
                if effort.startswith(prefix.lower()):
                    yield Completion(effort, start_position=-len(prefix))
            return

        if text.startswith("/skills on "):
            prefix = text[len("/skills on "):]
            for skill in available_skills():
                if skill.key.startswith(prefix.lower()):
                    yield Completion(skill.key, start_position=-len(prefix), display_meta=skill.summary)
            return

        if text.startswith("/skills off "):
            prefix = text[len("/skills off "):]
            for skill in available_skills():
                if skill.key.startswith(prefix.lower()):
                    yield Completion(skill.key, start_position=-len(prefix), display_meta=skill.summary)
            return

        if text.startswith("/skills "):
            prefix = _suffix_after_first_space(text)
            for value, desc in (
                ("list", "show available and active skills"),
                ("on", "force-enable a skill"),
                ("off", "force-disable a skill"),
                ("auto", "clear overrides and use auto-selection"),
                ("clear", "clear all skill overrides"),
            ):
                if value.startswith(prefix.lower()):
                    yield Completion(value, start_position=-len(prefix), display_meta=desc)
            return

        if text.startswith("/intent "):
            prefix = _suffix_after_first_space(text)
            for value, desc in (
                ("status", "show the current gameplay intent profile"),
                ("confirm", "persist the current inferred profile"),
                ("edit", "open guided gameplay intent questions"),
                ("clear", "clear the confirmed gameplay intent"),
            ):
                if value.startswith(prefix.lower()):
                    yield Completion(value, start_position=-len(prefix), display_meta=desc)
            return

        if text.startswith("/playtest "):
            prefix = _suffix_after_first_space(text)
            for value, desc in (
                ("relevant", "run profile-selected scripted scenarios"),
                ("all", "run all scripted scenarios for the current profile"),
            ):
                if value.startswith(prefix.lower()):
                    yield Completion(value, start_position=-len(prefix), display_meta=desc)
            return

        if text.startswith("/contracts "):
            prefix = _suffix_after_first_space(text)
            for value, desc in (
                ("relevant", "show contracts for the current profile"),
                ("all", "show all built-in contracts"),
            ):
                if value.startswith(prefix.lower()):
                    yield Completion(value, start_position=-len(prefix), display_meta=desc)
            return

        # Command completion
        if text.startswith("/"):
            for cmd, desc in self.COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)
            return

        # cd/path completion
        if text.startswith("cd ") or text.startswith("/cd "):
            prefix = _suffix_after_first_space(text)
            path = Path(prefix).expanduser()
            parent = path.parent if not path.is_dir() else path
            stem = path.name if not path.is_dir() else ""
            try:
                for item in sorted(parent.iterdir()):
                    if item.name.startswith("."):
                        continue
                    if item.name.lower().startswith(stem.lower()):
                        suffix = "/" if item.is_dir() else ""
                        yield Completion(
                            item.name + suffix,
                            start_position=-len(stem),
                        )
            except (PermissionError, FileNotFoundError):
                pass


def create_session(history_file: str | None = None) -> PromptSession:
    """Create a PromptSession with file history."""
    history = FileHistory(history_file) if history_file else None
    return PromptSession(history=history)


def get_input(
    session: PromptSession,
    completer: Completer | None = None,
    bottom_toolbar: str | None = None,
    prompt_markup: str = "<green>you&gt;</green> ",
    password: bool = False,
) -> str | None:
    """Get user input with history and completion. Returns None on EOF/interrupt."""
    try:
        return session.prompt(
            HTML(prompt_markup),
            completer=completer,
            bottom_toolbar=HTML(bottom_toolbar) if bottom_toolbar else None,
            is_password=password,
        )
    except (EOFError, KeyboardInterrupt):
        return None


async def get_input_async(
    session: PromptSession,
    completer: Completer | None = None,
    bottom_toolbar: str | None = None,
    prompt_markup: str = "<green>you&gt;</green> ",
    password: bool = False,
) -> str | None:
    """Async prompt variant for use inside an active event loop."""
    try:
        return await session.prompt_async(
            HTML(prompt_markup),
            completer=completer,
            bottom_toolbar=HTML(bottom_toolbar) if bottom_toolbar else None,
            is_password=password,
        )
    except (EOFError, KeyboardInterrupt):
        return None


def get_multiline_continuation(session: PromptSession) -> str | None:
    """Get continuation line for multi-line input.

    v1.0.0/D4: shows an explicit cancel hint so users don't get
    trapped in multiline mode without knowing how to escape.
    """
    try:
        return session.prompt(HTML('<dim>... (""" to finish · Ctrl+C to cancel)</dim> '))
    except (EOFError, KeyboardInterrupt):
        return None


async def get_multiline_continuation_async(session: PromptSession) -> str | None:
    """Async continuation prompt for multi-line input."""
    try:
        return await session.prompt_async(
            HTML('<dim>... (""" to finish · Ctrl+C to cancel)</dim> ')
        )
    except (EOFError, KeyboardInterrupt):
        return None

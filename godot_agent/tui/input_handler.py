"""Rich input with history, auto-complete, and multi-line support."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML


class CommandCompleter(Completer):
    """Auto-complete for / commands and file paths."""

    COMMANDS = [
        ("/cd ", "change project directory"),
        ("/info", "show project details"),
        ("/status", "show model & auth"),
        ("/usage", "show token usage"),
        ("/settings", "show all settings"),
        ("/set ", "change a setting"),
        ("/save", "save session"),
        ("/load", "restore session"),
        ("/help", "show commands"),
        ("/quit", "exit"),
    ]

    SETTINGS = [
        "language", "verbosity", "auto_validate", "auto_commit",
        "token_budget", "safety", "streaming", "extra_prompt",
    ]

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        # Command completion
        if text.startswith("/"):
            for cmd, desc in self.COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)
            return

        # /set <key> completion
        if text.startswith("/set "):
            parts = text.split()
            if len(parts) == 2:
                prefix = parts[1]
                for s in self.SETTINGS:
                    if s.startswith(prefix):
                        yield Completion(s, start_position=-len(prefix))
            return

        # cd/path completion
        if text.startswith("cd ") or text.startswith("/cd "):
            prefix = text.split(None, 1)[1] if " " in text else ""
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


def get_input(session: PromptSession, completer: CommandCompleter | None = None) -> str | None:
    """Get user input with history and completion. Returns None on EOF/interrupt."""
    try:
        return session.prompt(
            HTML("<green>you&gt;</green> "),
            completer=completer,
        )
    except (EOFError, KeyboardInterrupt):
        return None


def get_multiline_continuation(session: PromptSession) -> str | None:
    """Get continuation line for multi-line input."""
    try:
        return session.prompt(HTML("<dim>...</dim> "))
    except (EOFError, KeyboardInterrupt):
        return None

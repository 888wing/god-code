"""Rich TUI display components for god-code chat."""

from __future__ import annotations

import difflib
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


class ChatDisplay:
    """Manages all TUI output for the chat session."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def welcome(self, session_id: str, model: str, project_name: str | None, project_path: str) -> None:
        title = Text("God Code", style="bold cyan")
        parts = [f"Session: {session_id}", f"Model: {model}"]
        if project_name:
            parts.append(f"Project: {project_name}")
        else:
            parts.append(f"Dir: {project_path}")
        subtitle = Text(" | ".join(parts), style="dim")
        self.console.print()
        self.console.print(Panel(title, subtitle=subtitle, border_style="cyan", padding=(0, 2)))

    def no_project_warning(self) -> None:
        self.console.print("[yellow]  No project.godot found. Use /cd to navigate to a Godot project.[/]")

    def commands_table(self) -> Table:
        t = Table(show_header=False, box=None, padding=(0, 2), show_edge=False)
        t.add_column(style="green")
        t.add_column(style="dim")
        t.add_row("/cd <path>", "change project directory")
        t.add_row("/info", "show project details")
        t.add_row("/status", "show model & auth")
        t.add_row("/usage", "show token usage & cost")
        t.add_row("/settings", "show all settings")
        t.add_row("/set <key> <val>", "change a setting")
        t.add_row("/save", "save session")
        t.add_row("/load", "restore last session")
        t.add_row("/quit", "exit (Ctrl+C also works)")
        return t

    def tool_start(self, tool_name: str, args_summary: str) -> None:
        icon = {
            "read_file": "📖",
            "write_file": "✏️",
            "edit_file": "🔧",
            "grep": "🔍",
            "glob": "📂",
            "list_dir": "📂",
            "git": "📦",
            "run_shell": "💻",
            "run_godot": "🎮",
            "screenshot_scene": "📸",
        }.get(tool_name, "⚙️")
        self.console.print(f"  [dim]{icon} {tool_name}({args_summary})[/]")

    def tool_result(self, tool_name: str, success: bool, summary: str = "") -> None:
        if success:
            self.console.print(f"  [dim green]  ✓ {summary}[/]" if summary else f"  [dim green]  ✓[/]")
        else:
            self.console.print(f"  [dim red]  ✗ {summary}[/]")

    def show_diff(self, old_text: str, new_text: str, filename: str = "") -> None:
        diff = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{filename}" if filename else "before",
            tofile=f"b/{filename}" if filename else "after",
            n=2,
        ))
        if not diff:
            return
        text = Text()
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                text.append(line.rstrip() + "\n", style="green")
            elif line.startswith("-") and not line.startswith("---"):
                text.append(line.rstrip() + "\n", style="red")
            elif line.startswith("@@"):
                text.append(line.rstrip() + "\n", style="cyan")
            else:
                text.append(line.rstrip() + "\n", style="dim")
        self.console.print(Panel(text, title=f"[dim]diff: {filename}[/]", border_style="dim", padding=(0, 1)))

    def agent_response(self, content: str) -> None:
        self.console.print()
        self.console.print(Panel(
            Markdown(content),
            title="[cyan]agent[/]",
            border_style="cyan",
            padding=(1, 2),
        ))

    def agent_streaming_start(self) -> None:
        self.console.print()
        self.console.print("[cyan]agent>[/] ", end="")

    def agent_streaming_chunk(self, chunk: str) -> None:
        self.console.print(chunk, end="", highlight=False)

    def agent_streaming_end(self) -> None:
        self.console.print()

    def usage_line(self, total: int, prompt: int, completion: int, cost: float,
                   tools: list[str], session_total: int, session_calls: int, session_cost: float) -> None:
        tools_str = f"  tools: {', '.join(tools)}" if tools else ""
        self.console.print(
            f"  [dim]tokens: {total:,} (in:{prompt:,} out:{completion:,}) "
            f"~${cost:.4f}{tools_str}[/]"
        )
        self.console.print(
            f"  [dim]session: {session_total:,} tokens "
            f"| {session_calls} API calls "
            f"| ~${session_cost:.4f} total[/]"
        )
        self.console.print()

    def budget_warning(self, used: int, budget: int) -> None:
        pct = used / budget * 100 if budget > 0 else 0
        if pct >= 90:
            self.console.print(f"  [bold red]⚠ Token budget: {used:,}/{budget:,} ({pct:.0f}%) — near limit![/]")
        elif pct >= 75:
            self.console.print(f"  [yellow]⚠ Token budget: {used:,}/{budget:,} ({pct:.0f}%)[/]")

    def session_summary(self, total: int, prompt: int, completion: int, calls: int, cost: float) -> None:
        self.console.print()
        self.console.print(Panel(
            f"Tokens: {total:,} (in:{prompt:,} out:{completion:,})\n"
            f"API calls: {calls}\n"
            f"Estimated cost: ${cost:.4f}",
            title="[dim]Session Summary[/]",
            border_style="dim",
        ))

    def info_panel(self, data: dict) -> None:
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(style="bold")
        t.add_column()
        for k, v in data.items():
            t.add_row(k, str(v))
        self.console.print(Panel(t, title="Project Info", border_style="blue"))

    def status_panel(self, data: dict) -> None:
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(style="bold")
        t.add_column()
        for k, v in data.items():
            t.add_row(k, str(v))
        self.console.print(Panel(t, title="Status", border_style="blue"))

    def settings_panel(self, cfg: Any) -> None:
        t = Table(show_header=True, box=None, padding=(0, 1))
        t.add_column("Setting", style="bold")
        t.add_column("Value")
        t.add_column("Description", style="dim")
        settings_desc = {
            "language": "Agent response language (en, zh-TW, ja)",
            "verbosity": "Response detail level (concise, normal, detailed)",
            "auto_validate": "Run Godot validation after file changes",
            "auto_commit": "Suggest git commit after changes",
            "token_budget": "Max tokens per session (0 = unlimited)",
            "safety": "Shell command restriction (strict, normal, permissive)",
            "streaming": "Stream responses word by word",
            "extra_prompt": "Custom instructions appended to system prompt",
        }
        for key, desc in settings_desc.items():
            val = getattr(cfg, key, "?")
            t.add_row(key, str(val), desc)
        self.console.print(Panel(t, title="Settings", border_style="blue"))

    def error(self, msg: str) -> None:
        self.console.print(f"[red]  {msg}[/]")

    def success(self, msg: str) -> None:
        self.console.print(f"[green]  {msg}[/]")

    def info(self, msg: str) -> None:
        self.console.print(f"  [dim]{msg}[/]")

    def thinking(self):
        return self.console.status("[cyan]Thinking...[/]", spinner="dots")

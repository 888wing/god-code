"""Rich TUI display components for god-code chat."""

from __future__ import annotations

import difflib
from datetime import datetime
from typing import Any

from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from godot_agent.runtime.events import EngineEvent
from godot_agent.runtime.modes import get_mode_spec


class ChatDisplay:
    """Manages all TUI output for the chat session."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.activity_log: list[str] = []
        self.session_id = ""
        self.provider = ""
        self.model = ""
        self.effort = "high"
        self.mode = "apply"
        self.project_name: str | None = None
        self.project_path = ""
        self.project_info: dict[str, Any] = {}
        self.last_focus = ""
        self.last_response_preview = ""
        self.last_validation = "Not run"
        self.session_total_tokens = 0
        self.session_api_calls = 0
        self.session_cost = 0.0
        self._stream_buffer = ""
        self._stream_live: Live | None = None

    def add_activity(self, message: str) -> None:
        clean = " ".join(message.split())
        if not clean:
            return
        self.activity_log.append(clean)
        self.activity_log = self.activity_log[-10:]

    def configure_workspace(
        self,
        *,
        session_id: str,
        provider: str = "",
        model: str,
        effort: str = "high",
        mode: str,
        project_name: str | None,
        project_path: str,
        project_info: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.provider = provider
        self.model = model
        self.effort = effort
        self.mode = mode
        self.project_name = project_name
        self.project_path = project_path
        if project_info is not None:
            self.project_info = project_info

    def update_project_info(self, project_info: dict[str, Any]) -> None:
        self.project_info = project_info

    def update_mode(self, mode: str) -> None:
        self.mode = mode
        spec = get_mode_spec(mode)
        self.add_activity(f"mode -> {spec.label}")

    def update_session_metrics(self, total_tokens: int, api_calls: int, cost: float) -> None:
        self.session_total_tokens = total_tokens
        self.session_api_calls = api_calls
        self.session_cost = cost

    def welcome(
        self,
        session_id: str,
        model: str,
        project_name: str | None,
        project_path: str,
        mode: str,
        *,
        provider: str = "",
        effort: str = "high",
    ) -> None:
        self.configure_workspace(
            session_id=session_id,
            provider=provider,
            model=model,
            effort=effort,
            mode=mode,
            project_name=project_name,
            project_path=project_path,
        )
        title = Text("God Code", style="bold cyan")
        spec = get_mode_spec(mode)
        parts = [f"Session: {session_id}"]
        if provider:
            parts.append(f"Provider: {provider}")
        parts.extend([f"Model: {model}", f"Effort: {effort}", f"Mode: {spec.label}"])
        if project_name:
            parts.append(f"Project: {project_name}")
        else:
            parts.append(f"Dir: {project_path}")
        subtitle = Text(" | ".join(parts), style="dim")
        self.console.print()
        self.console.print(Panel(title, subtitle=subtitle, border_style="cyan", padding=(0, 2)))

    def no_project_warning(self) -> None:
        self.add_activity("No project.godot found in the current directory")
        self.console.print("[yellow]  No project.godot found. Use /cd to navigate to a Godot project.[/]")

    def commands_table(self) -> Table:
        t = Table(show_header=False, box=None, padding=(0, 2), show_edge=False)
        t.add_column(style="green")
        t.add_column(style="dim")
        t.add_row("/cd <path>", "change project directory")
        t.add_row("/mode [name]", "show or change interaction mode")
        t.add_row("/provider [name]", "show or switch provider")
        t.add_row("/model [name]", "show or switch model")
        t.add_row("/effort [level]", "show or switch reasoning effort")
        t.add_row("/info", "show project details")
        t.add_row("/status", "show provider, model, auth, and mode")
        t.add_row("/usage", "show token usage and cost")
        t.add_row("/settings", "show all settings")
        t.add_row("/set <key> <val>", "change a setting")
        t.add_row("/sessions", "list recent saved sessions")
        t.add_row("/resume [id]", "resume latest or chosen session")
        t.add_row("/new", "start a fresh session")
        t.add_row("/save", "save session snapshot")
        t.add_row("/load", "alias for /resume latest")
        t.add_row("/workspace", "show the workspace snapshot")
        t.add_row("/quit", "exit (Ctrl+C also works)")
        return t

    def workspace_snapshot(self, *, show_commands: bool = False) -> None:
        spec = get_mode_spec(self.mode)

        session_table = Table(show_header=False, box=None, padding=(0, 1))
        session_table.add_column(style="bold")
        session_table.add_column()
        session_table.add_row("Session", self.session_id or "-")
        session_table.add_row("Provider", self.provider or "-")
        session_table.add_row("Model", self.model or "-")
        session_table.add_row("Effort", self.effort or "-")
        session_table.add_row("Mode", spec.label)
        session_table.add_row("Project", self.project_name or self.project_path or "-")

        project_table = Table(show_header=False, box=None, padding=(0, 1))
        project_table.add_column(style="bold")
        project_table.add_column()
        project_table.add_row("Path", self.project_path or "-")
        project_table.add_row("Main Scene", str(self.project_info.get("Main Scene", "-")))
        project_table.add_row("Resolution", str(self.project_info.get("Resolution", "-")))
        project_table.add_row("Files", str(self.project_info.get("File Count", "-")))
        project_table.add_row("Guide", str(self.project_info.get("Guide", "-")))

        runtime_table = Table(show_header=False, box=None, padding=(0, 1))
        runtime_table.add_column(style="bold")
        runtime_table.add_column()
        runtime_table.add_row("Focus", self.last_focus or "-")
        runtime_table.add_row("Last Validation", self.last_validation)
        runtime_table.add_row("Tokens", f"{self.session_total_tokens:,}")
        runtime_table.add_row("API Calls", str(self.session_api_calls))
        runtime_table.add_row("Est. Cost", f"${self.session_cost:.4f}")

        activity_table = Table(show_header=False, box=None, padding=(0, 1))
        activity_table.add_column(style="dim")
        if self.activity_log:
            for item in self.activity_log[-8:]:
                activity_table.add_row(item)
        else:
            activity_table.add_row("No activity yet")

        panels = Columns(
            [
                Panel(session_table, title="Session", border_style="cyan"),
                Panel(project_table, title="Project", border_style="blue"),
                Panel(runtime_table, title="Runtime", border_style="magenta"),
            ],
            equal=True,
            expand=True,
        )

        content: list[Any] = [panels, Panel(activity_table, title="Recent Activity", border_style="dim")]
        if show_commands:
            content.append(Panel(self.commands_table(), title="Commands", border_style="green"))
        self.console.print()
        self.console.print(Group(*content))

    def tool_start(self, tool_name: str, args_summary: str) -> None:
        label = f"{tool_name}({args_summary})" if args_summary else tool_name
        self.add_activity(f"tool start: {label}")
        self.console.print(f"  [dim]> {label}[/]")

    def tool_result(self, tool_name: str, success: bool, summary: str = "") -> None:
        self.add_activity(f"tool {'ok' if success else 'fail'}: {tool_name} - {summary or 'done'}")
        if success:
            self.console.print(f"  [dim green]  ok  {summary}[/]" if summary else "  [dim green]  ok[/]")
        else:
            self.console.print(f"  [dim red]  fail  {summary}[/]")

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
        self.add_activity(f"diff: {filename or 'updated file'}")
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
        self.last_response_preview = content.strip().splitlines()[0][:120] if content.strip() else ""
        self.add_activity(f"assistant: {self.last_response_preview or 'reply ready'}")
        self.console.print()
        self.console.print(Panel(
            Markdown(content or ""),
            title="[cyan]assistant[/]",
            border_style="cyan",
            padding=(1, 2),
        ))

    def agent_streaming_start(self) -> None:
        self._stream_buffer = ""
        self._stream_live = Live(
            Panel(Markdown(" "), title="[cyan]assistant[/]", border_style="cyan", padding=(1, 2)),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._stream_live.start()

    def agent_streaming_chunk(self, chunk: str) -> None:
        self._stream_buffer += chunk
        if self._stream_live:
            text = self._stream_buffer if self._stream_buffer.strip() else " "
            self._stream_live.update(
                Panel(Markdown(text), title="[cyan]assistant[/]", border_style="cyan", padding=(1, 2))
            )

    def agent_streaming_end(self, finalize: bool) -> None:
        if self._stream_live:
            self._stream_live.stop()
            self._stream_live = None
        buffered = self._stream_buffer
        self._stream_buffer = ""
        if finalize and buffered.strip():
            self.agent_response(buffered)

    def usage_line(self, total: int, prompt: int, completion: int, cost: float,
                   tools: list[str], session_total: int, session_calls: int, session_cost: float) -> None:
        tools_str = f"  tools: {', '.join(tools)}" if tools else ""
        self.update_session_metrics(session_total, session_calls, session_cost)
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
            self.console.print(f"  [bold red]! Token budget: {used:,}/{budget:,} ({pct:.0f}%) near limit[/]")
        elif pct >= 75:
            self.console.print(f"  [yellow]! Token budget: {used:,}/{budget:,} ({pct:.0f}%)[/]")

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
            "provider": "Model API family (openai, anthropic, gemini, xai, ...)",
            "base_url": "API base URL; used to build the chat/completions endpoint",
            "model": "Default model name for the active provider",
            "reasoning_effort": "Normalized reasoning level (minimal, low, medium, high, xhigh)",
            "language": "Agent response language (en, zh-TW, ja)",
            "verbosity": "Response detail level (concise, normal, detailed)",
            "mode": "Interaction mode (apply, plan, explain, review, fix)",
            "auto_validate": "Run Godot validation after file changes",
            "auto_commit": "Suggest git commit after changes",
            "token_budget": "Max tokens per session (0 = unlimited)",
            "safety": "Shell command restriction (strict, normal, permissive)",
            "streaming": "Render assistant replies incrementally",
            "autosave_session": "Persist chat state after each completed turn",
            "extra_prompt": "Custom instructions appended to system prompt",
        }
        for key, desc in settings_desc.items():
            val = getattr(cfg, key, "?")
            t.add_row(key, str(val), desc)
        self.console.print(Panel(t, title="Settings", border_style="blue"))

    def session_list_panel(self, sessions: list[Any]) -> None:
        t = Table(show_header=True, box=None, padding=(0, 1))
        t.add_column("ID", style="bold cyan")
        t.add_column("When", style="dim")
        t.add_column("Mode")
        t.add_column("Project")
        t.add_column("Messages", justify="right")
        t.add_column("Title")
        if sessions:
            for session in sessions:
                when = datetime.fromtimestamp(session.timestamp).strftime("%Y-%m-%d %H:%M")
                t.add_row(
                    session.session_id,
                    when,
                    session.mode or "-",
                    session.project_name or session.project_path or "-",
                    str(session.message_count),
                    session.title or "-",
                )
        else:
            t.add_row("-", "-", "-", "-", "-", "No saved sessions")
        self.console.print(Panel(t, title="Saved Sessions", border_style="blue"))

    def mode_panel(self, mode: str) -> None:
        spec = get_mode_spec(mode)
        body = f"{spec.label}\n\n{spec.description}"
        self.console.print(Panel(body, title="Interaction Mode", border_style="magenta"))

    def handle_event(self, event: EngineEvent) -> None:
        if event.kind == "turn_started":
            self.last_focus = event.message
            self.add_activity(f"user: {event.message}")
        elif event.kind == "project_scanned":
            sample_files = event.data.get("sample_files") or []
            self.project_info["File Count"] = event.data.get("file_count", "-")
            self.project_info["Guide"] = event.data.get("guide_file") or "-"
            if sample_files:
                self.add_activity(f"scan: {', '.join(sample_files[:3])}")
        elif event.kind == "validation_started":
            self.last_validation = "Running"
            self.add_activity("validation: running")
        elif event.kind == "validation_passed":
            warnings = int(event.data.get("warnings", 0))
            self.last_validation = f"Passed ({warnings} warnings)"
            self.add_activity(self.last_validation)
        elif event.kind == "validation_failed":
            errors = int(event.data.get("errors", 0))
            suggestion = event.data.get("suggestion", "")
            self.last_validation = f"Failed ({errors} errors)"
            self.add_activity(self.last_validation)
            body = f"Errors: {errors}\nWarnings: {event.data.get('warnings', 0)}"
            if suggestion:
                body += f"\nSuggestion: {suggestion}"
            self.console.print(Panel(body, title="Validation Failed", border_style="red"))
        elif event.kind == "validation_skipped":
            self.last_validation = "Skipped"
            self.add_activity(event.message)
        elif event.kind == "assistant_response_ready" and event.message:
            self.last_response_preview = event.message
        elif event.kind == "assistant_stream_finished" and not event.data.get("final", False):
            self.add_activity("assistant: requested tools")
        elif event.kind == "context_compacted":
            self.add_activity(event.message)

    def error(self, msg: str) -> None:
        self.add_activity(f"error: {msg}")
        self.console.print(f"[red]  {msg}[/]")

    def success(self, msg: str) -> None:
        self.add_activity(f"success: {msg}")
        self.console.print(f"[green]  {msg}[/]")

    def info(self, msg: str) -> None:
        self.add_activity(msg)
        self.console.print(f"  [dim]{msg}[/]")

    def thinking(self):
        return self.console.status("[cyan]Thinking...[/]", spinner="dots")

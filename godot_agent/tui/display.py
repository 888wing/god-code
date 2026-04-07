"""Rich TUI display components for god-code chat."""

from __future__ import annotations

import difflib
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from godot_agent.runtime.events import EngineEvent
from godot_agent.runtime.modes import get_mode_spec
from godot_agent.tui.input_handler import MenuOption

if TYPE_CHECKING:
    from godot_agent.runtime.execution_plan import ExecutionPlan


class ChatDisplay:
    """Manages all TUI output for the chat session."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.activity_log: list[str] = []
        self.session_id = ""
        self.provider = ""
        self.model = ""
        self.effort = "high"
        self.skill_mode = "auto"
        self.active_skills: list[str] = []
        self.enabled_skills: list[str] = []
        self.disabled_skills: list[str] = []
        self.mode = "apply"
        self.project_name: str | None = None
        self.project_path = ""
        self.project_info: dict[str, Any] = {}
        self.intent_profile: dict[str, Any] = {}
        self.quality_target = "prototype"
        self.asset_spec: dict[str, Any] = {}
        self.last_focus = ""
        self.last_response_preview = ""
        self.last_validation = "Not run"
        self.session_total_tokens = 0
        self.session_api_calls = 0
        self.session_cost = 0.0
        self._stream_buffer = ""
        self._stream_live: Live | None = None
        self._tool_status = None

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
        model: str,
        mode: str,
        project_name: str | None,
        project_path: str,
        provider: str = "",
        effort: str = "high",
        skill_mode: str = "auto",
        active_skills: list[str] | None = None,
        enabled_skills: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        project_info: dict[str, Any] | None = None,
        intent_profile: dict[str, Any] | None = None,
        quality_target: str = "prototype",
        asset_spec: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.provider = provider
        self.model = model
        self.effort = effort
        self.skill_mode = skill_mode
        self.active_skills = list(active_skills or [])
        self.enabled_skills = list(enabled_skills or [])
        self.disabled_skills = list(disabled_skills or [])
        self.mode = mode
        self.project_name = project_name
        self.project_path = project_path
        if project_info is not None:
            self.project_info = project_info
        if intent_profile is not None:
            self.intent_profile = dict(intent_profile)
        self.quality_target = quality_target or "prototype"
        if asset_spec is not None:
            self.asset_spec = dict(asset_spec)

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
        skill_mode: str = "auto",
        active_skills: list[str] | None = None,
        enabled_skills: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        intent_profile: dict[str, Any] | None = None,
        quality_target: str = "prototype",
        asset_spec: dict[str, Any] | None = None,
    ) -> None:
        self.configure_workspace(
            session_id=session_id,
            provider=provider,
            model=model,
            effort=effort,
            skill_mode=skill_mode,
            active_skills=active_skills,
            enabled_skills=enabled_skills,
            disabled_skills=disabled_skills,
            mode=mode,
            project_name=project_name,
            project_path=project_path,
            intent_profile=intent_profile,
            quality_target=quality_target,
            asset_spec=asset_spec,
        )
        title = Text("God Code", style="bold cyan")
        spec = get_mode_spec(mode)
        # v1.0.0/D3: previous welcome packed 8 fields on one line, wrapping
        # ugly on terminals < 120 cols. Trim to 4 essentials; the rest are
        # accessible via /workspace whenever the user wants them.
        parts = [
            f"Session {session_id[:8]}",
            f"Mode {spec.label}",
            f"Model {model}",
            f"Project {project_name or Path(project_path).name or '-'}" if project_path else "Dir -",
        ]
        subtitle = Text(" · ".join(parts), style="dim")
        self.console.print()
        self.console.print(Panel(title, subtitle=subtitle, border_style="cyan", padding=(0, 2)))
        # v1.0.0/H2: tab-completion hint, since otherwise a power feature
        # nobody discovers.
        self.console.print(
            "  [dim]Type / for commands · Tab for autocomplete · /help for cheat sheet[/]"
        )

    def no_project_warning(self) -> None:
        self.add_activity("No project.godot found in the current directory")
        self.console.print("[yellow]  No project.godot found. Use /cd to navigate to a Godot project.[/]")

    def commands_table(self) -> Table:
        # v1.0.0/E1: previous flat 27-row table was overwhelming. Group
        # commands by purpose so users can scan to the section they need.
        t = Table(show_header=False, box=None, padding=(0, 2), show_edge=False)
        t.add_column(style="green")
        t.add_column(style="dim")

        def section(label: str) -> None:
            t.add_row("", "")
            t.add_row(f"[bold cyan]{label}[/]", "")

        section("Project")
        t.add_row("/cd <path>", "change project directory")
        t.add_row("/info", "show project details")
        t.add_row("/intent [cmd]", "show or confirm gameplay intent")
        t.add_row("/quality", "show the current project quality target")
        t.add_row("/assetspec", "show the current sprite and asset constraints")

        section("Chat")
        t.add_row("/mode [name]", "show or change interaction mode")
        t.add_row("/auto <request>", "plan, approve, and auto-execute a task")
        t.add_row("/playtest [relevant|all|id]", "run scripted playtest contracts")
        t.add_row("/scenarios", "list built-in playtest scenarios")
        t.add_row("/contracts [relevant|all|id]", "show scripted-route contract details")

        section("Session")
        t.add_row("/sessions", "list recent saved sessions")
        t.add_row("/resume [id]", "resume latest or chosen session")
        t.add_row("/new", "start a fresh session")
        t.add_row("/save", "save session snapshot")
        t.add_row("/load", "alias for /resume latest")
        t.add_row("/workspace", "show the workspace snapshot")

        section("Settings")
        t.add_row("/provider [name]", "show or switch provider")
        t.add_row("/model [name]", "show or switch model")
        t.add_row("/effort [level]", "show or switch reasoning effort")
        t.add_row("/skills [cmd]", "list or override internal skills")
        t.add_row("/settings", "show all settings")
        t.add_row("/set <key> <val>", "change a setting (Tab autocompletes keys)")

        section("Info")
        t.add_row("/status", "show provider, model, auth, and mode")
        t.add_row("/usage", "show token usage and cost")
        t.add_row("/version", "show current version and check for updates")
        t.add_row("/menu", "open the interactive command menu")
        t.add_row("/help", "this cheat sheet")

        section("Exit")
        t.add_row("/exit", "exit (also: /quit, Ctrl+C)")

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
        session_table.add_row("Skills", self.skill_mode or "-")
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
        runtime_table.add_row("Active Skills", ", ".join(self.active_skills) if self.active_skills else "-")
        runtime_table.add_row("Quality", self.quality_target or "prototype")
        runtime_table.add_row("Last Validation", self.last_validation)
        runtime_table.add_row("Tokens", f"{self.session_total_tokens:,}")
        runtime_table.add_row("API Calls", str(self.session_api_calls))
        runtime_table.add_row("Est. Cost", f"${self.session_cost:.4f}")

        intent_table = Table(show_header=False, box=None, padding=(0, 1))
        intent_table.add_column(style="bold")
        intent_table.add_column()
        intent_table.add_row("Genre", str(self.intent_profile.get("genre", "-") or "-"))
        intent_table.add_row("Combat", str(self.intent_profile.get("combat_model", "-") or "-"))
        intent_table.add_row("Enemy", str(self.intent_profile.get("enemy_model", "-") or "-"))
        intent_table.add_row("Boss", str(self.intent_profile.get("boss_model", "-") or "-"))
        combat_profile = self.intent_profile.get("combat_profile") or {}
        combat_summary = ", ".join(
            filter(
                None,
                [
                    str(combat_profile.get("player_space_model", "") or ""),
                    str(combat_profile.get("density_curve", "") or ""),
                    str(combat_profile.get("readability_target", "") or ""),
                ],
            )
        )
        intent_table.add_row("Combat Profile", combat_summary or "-")
        intent_table.add_row("Confidence", f"{float(self.intent_profile.get('confidence', 0.0) or 0.0):.2f}")
        conflicts = self.intent_profile.get("conflicts") or []
        intent_table.add_row("Conflicts", ", ".join(conflicts) if conflicts else "-")
        asset_style = str(self.asset_spec.get("style", "-") or "-")
        target_size = self.asset_spec.get("target_size") or []
        size_label = f"{target_size[0]}x{target_size[1] if len(target_size) > 1 else target_size[0]}" if target_size else "-"
        intent_table.add_row("Asset Style", asset_style)
        intent_table.add_row("Asset Size", size_label)

        activity_table = Table(show_header=False, box=None, padding=(0, 1))
        activity_table.add_column(style="dim")
        if self.activity_log:
            # v1.0.0/E2: was [-8:] while add_activity caps at [-10:],
            # silently dropping the 2 oldest visible entries. Now both 10.
            for item in self.activity_log[-10:]:
                activity_table.add_row(item)
        else:
            activity_table.add_row("No activity yet")

        panels = Columns(
            [
                Panel(session_table, title="Session", border_style="cyan"),
                Panel(project_table, title="Project", border_style="blue"),
                Panel(runtime_table, title="Runtime", border_style="magenta"),
                Panel(intent_table, title="Intent", border_style="yellow"),
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
        # Cap long args so a grep regex / huge file content doesn't overflow
        # the terminal and corrupt TUI rendering (v1.0.0/B4).
        truncated_args = args_summary
        if len(args_summary) > 100:
            truncated_args = args_summary[:100] + "…"
        label = f"{tool_name}({truncated_args})" if truncated_args else tool_name
        self.add_activity(f"tool start: {label}")
        self.console.print(f"  [dim]> {label}[/]")
        # Open a status spinner so long-running tools (validation, sprite gen,
        # screenshot — all 10-60s typical) show movement instead of leaving
        # the user staring at "tool: started" for a minute (v1.0.0/A2).
        if self._tool_status is None:
            self._tool_status = self.console.status(
                f"[dim]{tool_name} running…[/]", spinner="dots"
            )
            self._tool_status.start()

    def tool_result(self, tool_name: str, success: bool, summary: str = "") -> None:
        # Close the spinner first so the result line is the last thing printed.
        if self._tool_status is not None:
            self._tool_status.stop()
            self._tool_status = None
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
        # Show a thinking spinner during the silent reasoning phase before
        # the first streamed token arrives. Without this placeholder, gpt-5.4
        # with reasoning_effort=high left users staring at an empty cyan panel
        # for 30-60s, indistinguishable from a frozen CLI (regression v1.0.0/A1).
        self._stream_live = Live(
            Panel(
                Spinner("dots", text="[dim]thinking…[/]"),
                title="[cyan]assistant[/]",
                border_style="cyan",
                padding=(1, 2),
            ),
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
        # Blank line separator between successive assistant turns so back-to-back
        # streamed responses don't visually blur together (v1.0.0/A3).
        self.console.print()
        buffered = self._stream_buffer
        self._stream_buffer = ""
        if finalize and buffered.strip():
            self.agent_response(buffered)

    def usage_line(self, total: int, prompt: int, completion: int, cost: float,
                   tools: list[str], session_total: int, session_calls: int, session_cost: float,
                   *, cost_known: bool = True) -> None:
        tools_str = f"  tools: {', '.join(tools)}" if tools else ""
        self.update_session_metrics(session_total, session_calls, session_cost)
        # When the model is not in the pricing table the cost is a misleading
        # fallback (gpt-4o rate). Show "unknown" instead so users don't trust
        # a number that has no relationship to their actual bill (v1.0.0/C5).
        if cost_known:
            cost_str = f"~${cost:.4f}"
            session_cost_str = f"~${session_cost:.4f}"
        else:
            cost_str = "[yellow]~$unknown[/] [dim](model not in pricing table)[/]"
            session_cost_str = "[yellow]~$unknown[/]"
        self.console.print(
            f"  [dim]tokens: {total:,} (in:{prompt:,} out:{completion:,})[/] "
            f"{cost_str}[dim]{tools_str}[/]"
        )
        self.console.print(
            f"  [dim]session: {session_total:,} tokens "
            f"| {session_calls} API calls "
            f"| {session_cost_str}[dim] total[/]"
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
            "api_key": "Provider API key (masked)",
            "provider": "Model API family (openai, anthropic, gemini, xai, ...)",
            "base_url": "API base URL; used to build the chat/completions endpoint",
            "model": "Default model name for the active provider",
            "reasoning_effort": "Normalized reasoning level (minimal, low, medium, high, xhigh)",
            "computer_use": "Enable OpenAI Responses computer-use requests",
            "computer_use_environment": "Computer-use environment label",
            "computer_use_display_width": "Computer-use display width in pixels",
            "computer_use_display_height": "Computer-use display height in pixels",
            "skill_mode": "Internal skill selection mode (auto, manual, hybrid)",
            "enabled_skills": "Skills forced on for prompt injection and tool narrowing",
            "disabled_skills": "Skills forced off even when auto-selection would choose them",
            "oauth_token": "OAuth token used when no API key is configured (masked)",
            "max_turns": "Maximum tool rounds per request",
            "max_tokens": "Maximum output tokens requested from the model",
            "temperature": "Sampling temperature",
            "godot_path": "Path to the Godot executable",
            "language": "Agent response language (en, zh-TW, ja)",
            "verbosity": "Response detail level (concise, normal, detailed)",
            "mode": "Interaction mode (apply, plan, explain, review, fix)",
            "auto_validate": "Run Godot validation after file changes",
            "auto_commit": "Suggest git commit after changes",
            "screenshot_max_iterations": "Retry budget for screenshot stabilization",
            "token_budget": "Max tokens per session (0 = unlimited)",
            "safety": "Shell command restriction (strict, normal, permissive)",
            "streaming": "Render assistant replies incrementally",
            "autosave_session": "Persist chat state after each completed turn",
            "extra_prompt": "Custom instructions appended to system prompt",
            "session_dir": "Directory used to store chat sessions",
        }
        secret_keys = {"api_key", "oauth_token"}
        ordered_keys = [
            "api_key", "provider", "base_url", "model", "reasoning_effort", "oauth_token",
            "computer_use", "computer_use_environment", "computer_use_display_width", "computer_use_display_height",
            "skill_mode", "enabled_skills", "disabled_skills",
            "max_turns", "max_tokens", "temperature", "godot_path",
            "language", "verbosity", "mode", "auto_validate", "auto_commit",
            "screenshot_max_iterations", "token_budget", "safety", "streaming",
            "autosave_session", "extra_prompt", "session_dir",
        ]
        for key in ordered_keys:
            desc = settings_desc[key]
            val = getattr(cfg, key, "?")
            if key in secret_keys and val:
                text = str(val)
                val = "*" * min(len(text), 8) if len(text) <= 8 else f"{text[:4]}...{text[-4:]}"
            t.add_row(key, str(val), desc)
        self.console.print(Panel(t, title="Settings", border_style="blue"))

    def skills_panel(
        self,
        *,
        available: list[MenuOption],
        skill_mode: str,
        active_skills: list[str],
        enabled_skills: list[str],
        disabled_skills: list[str],
    ) -> None:
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("ID", style="bold cyan")
        table.add_column("Skill", style="bold")
        table.add_column("Status")
        table.add_column("Description", style="dim")
        active = set(active_skills)
        enabled = set(enabled_skills)
        disabled = set(disabled_skills)
        for option in available:
            status_parts: list[str] = []
            if option.value in active:
                status_parts.append("active")
            if option.value in enabled:
                status_parts.append("forced on")
            if option.value in disabled:
                status_parts.append("forced off")
            table.add_row(
                option.value,
                option.label,
                ", ".join(status_parts) if status_parts else "-",
                option.description or "-",
            )

        summary = Table(show_header=False, box=None, padding=(0, 1))
        summary.add_column(style="bold")
        summary.add_column()
        summary.add_row("Mode", skill_mode)
        summary.add_row("Active", ", ".join(active_skills) if active_skills else "-")
        summary.add_row("Enabled", ", ".join(enabled_skills) if enabled_skills else "-")
        summary.add_row("Disabled", ", ".join(disabled_skills) if disabled_skills else "-")
        self.console.print(Panel(Group(summary, table), title="Skills", border_style="blue"))

    def intent_panel(self, profile: dict[str, Any]) -> None:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        for key, label in (
            ("genre", "Genre"),
            ("camera_model", "Camera"),
            ("player_control_model", "Player Control"),
            ("combat_model", "Combat"),
            ("enemy_model", "Enemy Model"),
            ("boss_model", "Boss Model"),
        ):
            table.add_row(label, str(profile.get(key, "-") or "-"))
        testing_focus = profile.get("testing_focus") or []
        conflicts = profile.get("conflicts") or []
        combat_profile = profile.get("combat_profile") or {}
        table.add_row("Testing Focus", ", ".join(testing_focus) if testing_focus else "-")
        table.add_row("Player Space", str(combat_profile.get("player_space_model", "-") or "-"))
        table.add_row("Density Curve", str(combat_profile.get("density_curve", "-") or "-"))
        table.add_row("Readability", str(combat_profile.get("readability_target", "-") or "-"))
        table.add_row("Bullet Cleanup", str(combat_profile.get("bullet_cleanup_policy", "-") or "-"))
        table.add_row("Phase Style", str(combat_profile.get("phase_style", "-") or "-"))
        table.add_row("Confirmed", "yes" if profile.get("confirmed") else "no")
        table.add_row("Confidence", f"{float(profile.get('confidence', 0.0) or 0.0):.2f}")
        table.add_row("Conflicts", ", ".join(conflicts) if conflicts else "-")
        reasons = profile.get("reasons") or []
        if reasons:
            table.add_row("Reasons", " | ".join(str(item) for item in reasons[:3]))
        self.console.print(Panel(table, title="Gameplay Intent", border_style="yellow"))

    def quality_panel(self, quality_target: str, polish_profile: dict[str, Any] | None = None) -> None:
        profile = polish_profile or {}
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Quality Target", quality_target or "prototype")
        table.add_row("Combat Feedback", str(profile.get("combat_feedback", "-") or "-"))
        table.add_row("Boss Transition", str(profile.get("boss_transition", "-") or "-"))
        table.add_row("UI Readability", str(profile.get("ui_readability", "-") or "-"))
        table.add_row("Wave Pacing", str(profile.get("wave_pacing", "-") or "-"))
        table.add_row("Juice Level", str(profile.get("juice_level", "-") or "-"))
        self.console.print(Panel(table, title="Quality Contract", border_style="magenta"))

    def asset_spec_panel(self, asset_spec: dict[str, Any]) -> None:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        target_size = asset_spec.get("target_size") or []
        size_label = f"{target_size[0]}x{target_size[1] if len(target_size) > 1 else target_size[0]}" if target_size else "-"
        table.add_row("Style", str(asset_spec.get("style", "-") or "-"))
        table.add_row("Target Size", size_label)
        table.add_row("Background Key", str(asset_spec.get("background_key", "-") or "-"))
        table.add_row("Alpha Required", "yes" if asset_spec.get("alpha_required") else "no")
        table.add_row("Palette Mode", str(asset_spec.get("palette_mode", "-") or "-"))
        table.add_row("Import Filter", str(asset_spec.get("import_filter", "-") or "-"))
        table.add_row("Allow Resize", "yes" if asset_spec.get("allow_resize", True) else "no")
        self.console.print(Panel(table, title="Asset Spec", border_style="cyan"))

    def scenarios_panel(self, scenarios: list[dict[str, Any]], quality_target: str) -> None:
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("ID", style="bold cyan")
        table.add_column("Genre")
        table.add_column("Quality", style="magenta")
        table.add_column("Steps", justify="right")
        table.add_column("Relevant", justify="center")
        table.add_column("Title")
        for scenario in scenarios:
            table.add_row(
                str(scenario.get("id", "-")),
                ", ".join(scenario.get("genres") or []) or "-",
                ", ".join(scenario.get("quality_targets") or []) or quality_target,
                "yes" if scenario.get("has_steps") else "no",
                "yes" if scenario.get("relevant") else "no",
                str(scenario.get("title", "-")),
            )
        self.console.print(Panel(table, title="Playtest Scenarios", border_style="green"))

    def contracts_panel(self, contracts: list[dict[str, Any]], quality_target: str) -> None:
        if not contracts:
            self.console.print(Panel("No contracts matched the current selection.", title="Playtest Contracts", border_style="green"))
            return
        sections: list[Any] = []
        for contract in contracts:
            header = Text(f"{contract.get('id', '-')} | {contract.get('title', '-')}", style="bold cyan")
            meta = Table(show_header=False, box=None, padding=(0, 1))
            meta.add_column(style="bold")
            meta.add_column()
            meta.add_row("Genres", ", ".join(contract.get("genres") or []) or "-")
            meta.add_row("Quality", ", ".join(contract.get("quality_targets") or []) or quality_target)
            meta.add_row("Focus", ", ".join(contract.get("testing_focus") or []) or "-")
            meta.add_row("Evidence", str(contract.get("evidence_policy", "-")))
            sections.append(header)
            sections.append(meta)
            for index, step in enumerate(contract.get("steps") or [], start=1):
                sections.append(Text(f"Step {index}: {step.get('title', '-')}", style="yellow"))
                sections.append(
                    Text(
                        f"  action={step.get('action', '-')}"
                        + (
                            f" | segments={len(step.get('route_segments') or [])}"
                            if step.get("route_segments")
                            else ""
                        ),
                        style="dim",
                    )
                )
        self.console.print(Panel(Group(*sections), title="Playtest Contracts", border_style="green"))

    def playtest_panel(
        self,
        *,
        verdict: str,
        gameplay_review_verdict: str,
        report: str,
        scenarios: list[dict[str, Any]],
    ) -> None:
        summary = Table(show_header=False, box=None, padding=(0, 1))
        summary.add_column(style="bold")
        summary.add_column()
        summary.add_row("Playtest", verdict)
        summary.add_row("Gameplay Review", gameplay_review_verdict or "-")
        summary.add_row("Scenario Count", str(len(scenarios)))
        body = Group(summary, Text(report, style="default"))
        self.console.print(Panel(body, title="Playtest Run", border_style="green"))

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

    def plan_panel(self, plan: ExecutionPlan) -> None:
        """Rich panel showing all plan steps with status icons."""
        from godot_agent.runtime.execution_plan import ExecutionPlan  # noqa: F811

        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column(width=3)  # icon
        t.add_column()          # step description
        t.add_column(style="dim")  # summary/files
        STATUS_ICONS = {"done": "[green]OK[/]", "running": "[yellow]>>[/]", "pending": "[dim]..[/]",
                        "approved": "[dim]..[/]", "failed": "[red]!![/]", "skipped": "[dim]--[/]"}
        for s in plan.steps:
            icon = STATUS_ICONS.get(s.status, "  ")
            desc = f"{s.index}. {s.action} {s.target}"
            info = s.summary if s.summary else ", ".join(s.files[:2])
            t.add_row(icon, desc, f"[dim]{info}[/]")
        progress = f"Progress: {plan.done_count}/{plan.total_actionable}"
        panel = Panel(Group(t, Text(progress, style="dim")), title=f"Plan: {plan.title}", border_style="green")
        self.console.print(panel)

    def plan_status_line(self, plan: ExecutionPlan) -> str:
        """One-line status for persistent display during auto execution."""
        step = plan.current_step
        if not step:
            return f"[green]Plan complete: {plan.done_count}/{plan.total_actionable}[/]"
        return f"[yellow]Step {step.index}/{plan.total_actionable}: {step.action} {step.target}...[/]"

    def menu_panel(
        self,
        title: str,
        options: list[MenuOption],
        *,
        current_value: str | None = None,
        prompt_hint: str = "Type number or name. Enter to cancel.",
    ) -> None:
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("#", style="bold cyan", justify="right")
        table.add_column("Option", style="bold")
        table.add_column("Description", style="dim")
        for index, option in enumerate(options, start=1):
            label = option.label
            if current_value is not None and option.value == current_value:
                label = f"{label} [current]"
            table.add_row(str(index), label, option.description or "-")
        self.console.print(Panel(Group(table, Text(prompt_hint, style="dim")), title=title, border_style="magenta"))

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
        elif event.kind == "planner_started":
            # v1.0.0/A4: visually bracket planner output with Rule separators
            # so users can distinguish the planner sub-agent's response from
            # the main turn's response (both stream into cyan panels otherwise).
            self.console.print()
            self.console.print(Rule("[dim cyan]planner[/]", style="dim cyan"))
            self.add_activity("planner: composing plan")
        elif event.kind == "planner_finished":
            used = event.data.get("used_tools") or []
            suffix = f" ({', '.join(used[:3])})" if used else ""
            self.console.print(Rule(style="dim cyan"))
            self.console.print()
            self.add_activity(f"planner: plan ready{suffix}")
        elif event.kind == "diff_failed":
            path = event.data.get("path", "?")
            reason = event.data.get("reason", "unknown")
            self.add_activity(f"diff: failed for {path} ({reason[:60]})")
        elif event.kind == "session_autosaved":
            # v1.0.0/A5: previous behaviour was completely silent.
            self.add_activity(event.message or "session: autosaved")
        elif event.kind == "session_autosave_failed":
            self.add_activity(event.message or "session: autosave failed")
            self.console.print(f"  [red]autosave failed:[/] {event.data.get('error', '?')}")
        elif event.kind == "turn_cancelled":
            # v1.0.0/C2: visible trail when Ctrl+C actually cancels a turn.
            self.add_activity(event.message or "turn cancelled")
        elif event.kind == "tool_result_truncated":
            tool_name = event.data.get("tool_name", "?")
            original = int(event.data.get("original_length", 0))
            truncated = int(event.data.get("truncated_length", 0))
            cut = max(0, original - truncated)
            self.add_activity(
                f"tool: {tool_name} result truncated ({cut} chars cut, {original} total)"
            )
        elif event.kind == "tool_progress":
            # v1.0.1/D3: per-tool progress updates for slow multi-stage tools.
            # Update the active status spinner's label so the user sees what
            # stage the tool is in instead of a static tool name for 20-60s.
            tool_name = event.data.get("tool_name", "?")
            step = event.data.get("step", 0)
            total = event.data.get("total", 0)
            label = event.data.get("label", "")
            self.add_activity(f"tool: {tool_name} ({step}/{total}) {label}")
            # If there's an active tool status spinner, update its label
            status = getattr(self, "_active_tool_status", None)
            if status is not None:
                try:
                    status.update(f"[yellow]tool: {tool_name} ({step}/{total}) {label}[/]")
                except Exception:
                    pass
        elif event.kind == "plan_pruned":
            # v1.0.1/T1: visible signal that old planner blocks were dropped
            # from history. Dogfood uses this to verify token savings.
            dropped = event.data.get("dropped", 0)
            kept = event.data.get("kept", 0)
            self.add_activity(
                f"planner: pruned {dropped} stale block(s) (keeping latest {kept})"
            )
        elif event.kind == "planner_skipped":
            # v1.0.1/T2: visible signal that the planner was skipped on a
            # trivial read-only input. Helps users understand why their
            # turn was faster than expected.
            reason = event.data.get("reason", "unknown")
            self.add_activity(f"planner: skipped ({reason})")
        elif event.kind == "context_compacted":
            self.add_activity(event.message)
        elif event.kind == "intent_inferred":
            profile = dict(event.data.get("profile") or {})
            if profile:
                self.intent_profile = profile
                genre = profile.get("genre", "") or "unresolved"
                self.add_activity(f"intent: {genre}")
        elif event.kind == "intent_conflict_detected":
            profile = dict(event.data.get("profile") or {})
            if profile:
                self.intent_profile = profile
            self.add_activity(f"intent conflict: {event.message}")

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

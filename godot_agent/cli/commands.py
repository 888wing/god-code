# godot_agent/cli/commands.py
"""Click commands for the god-code CLI."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

import click
import httpx

from godot_agent.llm.client import LLMClient, LLMConfig
from godot_agent.llm.vision import encode_image
from godot_agent.prompts.skill_selector import (
    available_skills,
    normalize_skill_mode,
    normalize_skill_name,
    sanitize_skill_keys,
    skill_label,
)
from godot_agent.runtime.config import AgentConfig, default_config_path, load_config
from godot_agent.runtime.design_memory import (
    gameplay_intent_from_data,
    GameplayIntentProfile,
    load_design_memory,
    resolved_asset_spec,
    resolved_quality_target,
)
from godot_agent.runtime.intent_resolver import (
    apply_intent_answers,
    intent_questions_for_profile,
    is_gameplay_architecture_task,
    resolve_gameplay_intent,
    should_prompt_for_intent,
)
from godot_agent.runtime.modes import normalize_mode
from godot_agent.runtime.providers import PROVIDER_PRESETS
from godot_agent.runtime.session import list_sessions, load_latest_session, load_session
from godot_agent.tools.editor_bridge import (
    ListContractsTool,
    ListScenariosTool,
    RunScriptedPlaytestTool,
)
from godot_agent.tui.input_handler import MenuOption, resolve_menu_choice

from godot_agent.cli.engine_wiring import (
    _apply_provider_preset,
    _has_usable_provider_auth,
    _is_interactive_terminal,
    _load_or_setup_config as _load_or_setup_config_impl,
    _normalize_reasoning_effort,
    _persist_config_updates,
    _provider_auth_issue,
    _save_config_data,
    _sync_provider_from_model,
    _wire_engine_callbacks,
    build_engine as _build_engine_impl,
    build_registry,
)
from godot_agent.cli.helpers import (
    _asset_spec_dict,
    _cd_argument,
    _command_argument,
    _format_intent_inline,
    _format_skill_list,
    _has_meaningful_input,
    _intent_profile_dict,
    _is_multiline_terminator,
    _multiline_initial_fragment,
    _persist_intent_profile,
    _polish_profile_dict,
    _project_details,
    _quality_target,
    _resolved_active_skill_keys,
    _save_chat_session,
    _set_arguments,
    _starts_multiline_input,
    _toolbar_markup,
)
from godot_agent.cli.menus import (
    _MULTILINE_SETTING_KEYS,
    _SECRET_SETTING_KEYS,
    _effort_menu_options,
    _format_setting_display_value,
    _main_menu_options,
    _mode_menu_options,
    _model_menu_options,
    _provider_menu_options,
    _session_menu_options,
    _setting_value_menu_options,
    _settings_menu_options,
    _skill_menu_options,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Monkeypatch-friendly indirection: tests do
#   monkeypatch.setattr("godot_agent.cli.build_engine", ...)
# which replaces the attribute on the *package* module.  The helpers below
# resolve names through that package module at call time so that patches are
# respected without modifying any test code.
# ---------------------------------------------------------------------------

def _pkg_attr(name: str, fallback):
    """Look up *name* on the ``godot_agent.cli`` package module."""
    import sys
    pkg = sys.modules.get("godot_agent.cli")
    if pkg is not None:
        return getattr(pkg, name, fallback)
    return fallback


_PROVIDERS = {
    "1": {
        "provider": "openai",
        "name": "OpenAI",
        "summary": "gpt-5.4, vision, tool calling",
    },
    "2": {
        "provider": "anthropic",
        "name": "Anthropic",
        "summary": "Claude 4.6, coding, long-context reasoning",
    },
    "3": {
        "provider": "openrouter",
        "name": "OpenRouter",
        "summary": "Aggregator with OpenAI-compatible routing",
    },
    "4": {
        "provider": "gemini",
        "name": "Gemini",
        "summary": "2M-context multimodal via OpenAI-compatible endpoint",
    },
    "5": {
        "provider": "xai",
        "name": "xAI",
        "summary": "Grok models via xAI API",
    },
    "6": {
        "provider": "glm",
        "name": "GLM / Z.AI",
        "summary": "GLM models via Z.AI platform",
    },
    "7": {
        "provider": "minimax",
        "name": "MiniMax",
        "summary": "MiniMax multimodal models",
    },
    "8": {
        "provider": "custom",
        "name": "Custom",
        "summary": "Local models, self-hosted, or other compatible APIs",
    },
}


_VERSION = "0.8.0"


def _is_configured() -> bool:
    """Check if god-code has been configured with an API key."""
    cfg = load_config(default_config_path())
    return _has_usable_provider_auth(cfg)


def _check_update() -> None:
    """Check PyPI for a newer version. Non-blocking, fails silently."""
    try:
        import httpx as _httpx
        from packaging.version import Version
        resp = _httpx.get("https://pypi.org/pypi/god-code/json", timeout=3)
        if resp.status_code == 200:
            latest = resp.json()["info"]["version"]
            if Version(latest) > Version(_VERSION):
                click.secho(f"  Update available: {_VERSION} → {latest}", fg="yellow")
                click.echo(f"  Run: pip install --upgrade god-code")
                click.echo()
    except Exception:
        pass


def _run_setup_wizard(config_path: Path | None = None) -> None:
    """Interactive first-run setup wizard."""
    click.echo()
    click.secho("  God Code — AI Agent for Godot Development", fg="cyan", bold=True)
    click.echo()
    click.echo("  First-time setup. Choose your LLM provider:")
    click.echo()
    for key, item in _PROVIDERS.items():
        preset = PROVIDER_PRESETS[item["provider"]]
        click.echo(f"  {key}. {item['name']:<15} ({item['summary']})")
        if preset.key_url:
            click.echo(f"     Get a key at: {preset.key_url}")
        click.echo()

    choice = ""
    while choice not in _PROVIDERS:
        choice = click.prompt("  Select provider", type=str, default="1")

    provider_choice = _PROVIDERS[choice]
    provider = PROVIDER_PRESETS[provider_choice["provider"]]
    config_data: dict = {}

    config_data["provider"] = provider.provider
    config_data["reasoning_effort"] = "high"

    if provider.provider == "custom":
        config_data["base_url"] = click.prompt("  Base URL", default="http://localhost:11434/v1")
        config_data["model"] = click.prompt("  Model name", default="llama3")
        api_key = click.prompt("  API key (leave empty if none)", default="", show_default=False, hide_input=True)
        if api_key:
            config_data["api_key"] = api_key
    else:
        config_data["base_url"] = provider.base_url
        config_data["model"] = click.prompt("  Default model", default=provider.model)
        click.echo()
        api_key = click.prompt(f"  Paste your {provider.name} API key", hide_input=True)
        if not api_key:
            click.secho("  No API key provided. Setup cancelled.", fg="red")
            raise SystemExit(1)
        config_data["api_key"] = api_key

    # Test the connection
    click.echo()
    click.echo("  Testing connection...", nl=False)

    async def _test() -> bool:
        llm_config = LLMConfig(
            api_key=config_data.get("api_key", ""),
            base_url=config_data["base_url"],
            provider=config_data["provider"],
            model=config_data["model"],
            reasoning_effort=config_data["reasoning_effort"],
            max_tokens=50,
        )
        client = LLMClient(llm_config)
        try:
            from godot_agent.llm.client import Message
            resp = await client.chat([Message.user("Say OK")])
            return bool(resp.message.content)
        except Exception as e:
            click.echo()
            click.secho(f"  Connection failed: {e}", fg="red")
            return False
        finally:
            await client.close()

    success = asyncio.run(_test())
    if not success:
        click.echo()
        retry = click.confirm("  Try again with different settings?", default=True)
        if retry:
            _run_setup_wizard()
            return
        raise SystemExit(1)

    click.secho(" Connected!", fg="green")

    # Detect Godot path
    import shutil
    godot_path = shutil.which("godot")
    if not godot_path:
        # macOS common path
        mac_path = "/Applications/Godot.app/Contents/MacOS/Godot"
        if Path(mac_path).exists():
            godot_path = mac_path
    if godot_path:
        config_data["godot_path"] = godot_path
        click.echo(f"  Godot found: {godot_path}")
    else:
        click.echo("  Godot not found in PATH. Set 'godot_path' in config later.")

    # Save config
    config_path = config_path or default_config_path()
    _save_config_data(config_path, config_data)

    click.echo()
    click.secho(f"  Config saved to {config_path}", fg="green")
    click.echo()
    click.echo("  Ready! Try:")
    click.echo("    god-code chat -p ./your-godot-project")
    click.echo("    god-code ask \"Add a health bar\" -p ./your-game")
    click.echo("    god-code info -p ./your-game")
    click.echo()


# ── Click group & subcommands ──────────────────────────────────

@click.group(invoke_without_command=True)
@click.version_option(version=_VERSION)
@click.pass_context
def main(ctx):
    """God Code -- AI coding assistant for Godot game development."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    _pkg_attr("_check_update", _check_update)()
    if ctx.invoked_subcommand is None:
        if not _is_configured():
            _run_setup_wizard()
        else:
            ctx.invoke(chat)


@main.command()
def setup():
    """Run the interactive setup wizard (reconfigure provider/API key)."""
    _run_setup_wizard(default_config_path())


@main.command()
def login():
    """Login via Codex CLI refresh token (experimental)."""
    from godot_agent.runtime.oauth import login as oauth_login
    try:
        tokens = oauth_login()
        click.secho("Login successful!", fg="green")
        click.echo(f"Token expires in: {tokens.get('expires_in', '?')}s")
        click.echo("Saved to ~/.config/god-code/auth.json")
    except Exception as e:
        click.secho(f"Login failed: {e}", fg="red", err=True)
        raise SystemExit(1)


@main.command()
def logout():
    """Remove stored OAuth credentials."""
    from godot_agent.runtime.oauth import AUTH_STORE_PATH
    if AUTH_STORE_PATH.exists():
        AUTH_STORE_PATH.unlink()
        click.echo("Logged out. Credentials removed.")
    else:
        click.echo("No stored credentials found.")


@main.command()
def status():
    """Show authentication and configuration status."""
    cfg = load_config(default_config_path())
    click.echo(f"Provider: {cfg.provider}")
    click.echo(f"Model:    {cfg.model}")
    click.echo(f"Effort:   {cfg.reasoning_effort}")
    click.echo(f"Computer: {cfg.computer_use} ({cfg.computer_use_environment} {cfg.computer_use_display_width}x{cfg.computer_use_display_height})")
    click.echo(f"Skills:   {cfg.skill_mode}")
    click.echo(f"Enabled:  {_format_skill_list(cfg.enabled_skills)}")
    click.echo(f"Disabled: {_format_skill_list(cfg.disabled_skills)}")
    click.echo(f"Base URL: {cfg.base_url}")
    click.echo(f"Godot:    {cfg.godot_path}")
    if cfg.provider == "custom" and not cfg.api_key and not cfg.oauth_token:
        click.echo("Auth:     Not required for custom provider")
    elif cfg.oauth_token:
        click.echo(f"Auth:     OAuth token ({cfg.oauth_token[:8]}...)")
    elif cfg.api_key:
        click.echo(f"Auth:     API key ({cfg.api_key[:8]}...)")
    else:
        click.secho("Auth:     Not configured. Run 'god-code setup'.", fg="yellow")
    project_root = Path.cwd()
    if (project_root / "project.godot").exists():
        memory = load_design_memory(project_root)
        intent = resolve_gameplay_intent(project_root, design_memory=memory)
        click.echo(f"Intent:   {_format_intent_inline(intent.to_dict())}")
        conflicts = ", ".join(intent.conflicts) if intent.conflicts else "-"
        click.echo(f"Conflict: {conflicts}")
        click.echo(f"Quality:  {resolved_quality_target(memory)}")
        asset_spec = resolved_asset_spec(memory)
        if not asset_spec.is_empty:
            size = f"{asset_spec.target_size[0]}x{asset_spec.target_size[1] if len(asset_spec.target_size) > 1 else asset_spec.target_size[0]}" if asset_spec.target_size else "-"
            click.echo(f"Assets:   {asset_spec.style or '-'} | {size} | {asset_spec.background_key or '-'}")


@main.command()
@click.argument("prompt")
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--image", "-i", multiple=True, help="Reference image paths")
@click.option("--plain", is_flag=True, help="Print only the final response")
def ask(prompt: str, project: str, config: str | None, image: tuple[str, ...], plain: bool):
    """Send a single prompt to the agent."""
    from godot_agent.tui.display import ChatDisplay

    config_path = Path(config) if config else default_config_path()
    cfg = _pkg_attr("_load_or_setup_config", _load_or_setup_config_impl)(config_path)
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"
    project_root = Path(project).resolve()
    show_rich = sys.stdout.isatty() and not plain
    engine = _pkg_attr("build_engine", _build_engine_impl)(cfg, project_root)
    display = ChatDisplay()
    active_skills = _resolved_active_skill_keys(engine, cfg)

    has_project, proj_name, project_info = _project_details(project_root)
    if show_rich:
        display.welcome(
            "one-shot",
            cfg.model,
            proj_name,
            str(project_root),
            cfg.mode,
            provider=cfg.provider,
            effort=cfg.reasoning_effort,
            skill_mode=cfg.skill_mode,
            active_skills=active_skills,
            enabled_skills=cfg.enabled_skills,
            disabled_skills=cfg.disabled_skills,
            intent_profile=_intent_profile_dict(engine),
            quality_target=_quality_target(engine),
            asset_spec=_asset_spec_dict(engine),
        )
        display.update_project_info(project_info)
        _wire_engine_callbacks(engine, display, cfg)
        if has_project:
            scan_result = engine.scan_project()
            if scan_result:
                project_info["File Count"] = str(scan_result.file_count)
                project_info["Guide"] = scan_result.guide_file or "-"
                display.update_project_info(project_info)
        display.workspace_snapshot()

    async def _run() -> str:
        try:
            if image:
                images_b64 = [encode_image(p) for p in image]
                return await engine.submit_with_images(prompt, images_b64)
            return await engine.submit(prompt)
        finally:
            await engine.close()

    result = asyncio.run(_run())
    if show_rich:
        if not cfg.streaming:
            display.agent_response(result)
        turn = engine.last_turn
        sess = engine.session_usage
        if turn:
            display.usage_line(
                turn.usage.total_tokens, turn.usage.prompt_tokens, turn.usage.completion_tokens,
                turn.usage.cost_estimate(cfg.model), turn.tools_called,
                sess.total_tokens, engine.session_api_calls, sess.cost_estimate(cfg.model),
            )
        display.session_summary(
            sess.total_tokens, sess.prompt_tokens, sess.completion_tokens,
            engine.session_api_calls, sess.cost_estimate(cfg.model),
        )
    else:
        click.echo(result)


@main.command()
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
def chat(project: str = ".", config: str | None = None):
    """Start an interactive chat session."""
    from godot_agent.tui.display import ChatDisplay
    from godot_agent.runtime.providers import infer_provider

    display = ChatDisplay()
    config_path = Path(config) if config else default_config_path()
    cfg = _pkg_attr("_load_or_setup_config", _load_or_setup_config_impl)(config_path)
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"

    project_root = Path(project).resolve()
    session_id = str(uuid.uuid4())[:8]
    has_project, proj_name, project_info = _project_details(project_root)

    engine = _pkg_attr("build_engine", _build_engine_impl)(cfg, project_root)
    _wire_engine_callbacks(engine, display, cfg)
    display.welcome(
        session_id,
        cfg.model,
        proj_name,
        str(project_root),
        cfg.mode,
        provider=cfg.provider,
        effort=cfg.reasoning_effort,
        skill_mode=cfg.skill_mode,
        active_skills=_resolved_active_skill_keys(engine, cfg),
        enabled_skills=cfg.enabled_skills,
        disabled_skills=cfg.disabled_skills,
        intent_profile=_intent_profile_dict(engine),
        quality_target=_quality_target(engine),
        asset_spec=_asset_spec_dict(engine),
    )
    if not has_project:
        display.no_project_warning()

    # Auto-scan project on entry
    if has_project:
        scan_result = engine.scan_project()
        if scan_result:
            project_info["File Count"] = str(scan_result.file_count)
            project_info["Guide"] = scan_result.guide_file or "-"
            display.info(f"Project auto-scanned: {scan_result.file_count} files")
        if not engine.intent_profile.confirmed and (engine.intent_profile.conflicts or engine.intent_profile.confidence < 0.8):
            display.info("Gameplay intent is not confirmed yet. Use /intent to review or confirm the current profile.")
    display.update_project_info(project_info)
    display.workspace_snapshot(show_commands=True)

    # Setup prompt_toolkit for history + autocomplete
    from godot_agent.tui.input_handler import (
        CommandCompleter,
        MenuCompleter,
        create_session as create_input_session,
        get_input_async,
        get_multiline_continuation_async,
    )
    history_file = str(Path.home() / ".config" / "god-code" / "history")
    Path(history_file).parent.mkdir(parents=True, exist_ok=True)
    input_session = create_input_session(history_file)
    completer = CommandCompleter(project_root)

    intent_checkpoint_dismissed = False

    def _refresh_workspace(show_commands: bool = False) -> None:
        active_skills = _resolved_active_skill_keys(engine, cfg)
        display.configure_workspace(
            session_id=session_id,
            provider=cfg.provider,
            model=cfg.model,
            effort=cfg.reasoning_effort,
            mode=cfg.mode,
            project_name=proj_name,
            project_path=str(project_root),
            project_info=project_info,
            skill_mode=cfg.skill_mode,
            active_skills=active_skills,
            enabled_skills=cfg.enabled_skills,
            disabled_skills=cfg.disabled_skills,
            intent_profile=_intent_profile_dict(engine),
            quality_target=_quality_target(engine),
            asset_spec=_asset_spec_dict(engine),
        )
        display.workspace_snapshot(show_commands=show_commands)

    async def _replace_engine(
        new_root: Path,
        *,
        preserve_messages: bool = False,
        seed_messages: list | None = None,
        rescan_project: bool = True,
        new_session_id: str | None = None,
    ) -> None:
        nonlocal engine, project_root, has_project, proj_name, project_info, completer, session_id, intent_checkpoint_dismissed
        old_messages = engine.messages[1:] if preserve_messages else []
        previous_root = project_root
        previous_project_info = dict(project_info)
        await engine.close()

        project_root = new_root.resolve()
        has_project, proj_name, project_info = _project_details(project_root)
        engine = _pkg_attr("build_engine", _build_engine_impl)(cfg, project_root)
        _wire_engine_callbacks(engine, display, cfg)

        carried_messages = seed_messages if seed_messages is not None else old_messages
        if carried_messages:
            engine.messages.extend(carried_messages)
            if project_root == previous_root:
                project_info.update({
                    key: value for key, value in previous_project_info.items()
                    if value not in {"", "-"}
                })
        elif has_project and rescan_project:
            scan_result = engine.scan_project()
            if scan_result:
                project_info["File Count"] = str(scan_result.file_count)
                project_info["Guide"] = scan_result.guide_file or "-"

        completer = CommandCompleter(project_root)
        if new_session_id is not None:
            session_id = new_session_id
        intent_checkpoint_dismissed = False

        display.configure_workspace(
            session_id=session_id,
            provider=cfg.provider,
            model=cfg.model,
            effort=cfg.reasoning_effort,
            mode=cfg.mode,
            project_name=proj_name,
            project_path=str(project_root),
            project_info=project_info,
            skill_mode=cfg.skill_mode,
            active_skills=_resolved_active_skill_keys(engine, cfg),
            enabled_skills=cfg.enabled_skills,
            disabled_skills=cfg.disabled_skills,
            intent_profile=_intent_profile_dict(engine),
            quality_target=_quality_target(engine),
            asset_spec=_asset_spec_dict(engine),
        )
        if not has_project:
            display.no_project_warning()

    def _intent_status_data() -> dict[str, object]:
        profile = _intent_profile_dict(engine)
        combat_profile = profile.get("combat_profile") or {}
        asset_spec = _asset_spec_dict(engine)
        target_size = asset_spec.get("target_size") or []
        size_label = f"{target_size[0]}x{target_size[1] if len(target_size) > 1 else target_size[0]}" if target_size else "-"
        return {
            "Gameplay Intent": _format_intent_inline(profile),
            "Genre": profile.get("genre", "-") or "-",
            "Player Control": profile.get("player_control_model", "-") or "-",
            "Combat": profile.get("combat_model", "-") or "-",
            "Enemy Model": profile.get("enemy_model", "-") or "-",
            "Boss Model": profile.get("boss_model", "-") or "-",
            "Combat Profile": ", ".join(
                filter(
                    None,
                    [
                        str(combat_profile.get("player_space_model", "") or ""),
                        str(combat_profile.get("density_curve", "") or ""),
                        str(combat_profile.get("readability_target", "") or ""),
                    ],
                )
            )
            or "-",
            "Testing Focus": ", ".join(profile.get("testing_focus") or []) or "-",
            "Intent Confirmed": "yes" if profile.get("confirmed") else "no",
            "Intent Confidence": f"{float(profile.get('confidence', 0.0) or 0.0):.2f}",
            "Intent Conflicts": ", ".join(profile.get("conflicts") or []) or "-",
            "Quality Target": _quality_target(engine),
            "Asset Style": asset_spec.get("style", "-") or "-",
            "Asset Size": size_label,
        }

    def _toolbar() -> str:
        return _toolbar_markup(
            cfg,
            project_root,
            proj_name,
            str(_intent_profile_dict(engine).get("genre", "-") or "-"),
            _quality_target(engine),
        )

    async def _prompt_menu_choice(
        title: str,
        options: list[MenuOption],
        *,
        current_value: str | None = None,
        prompt_hint: str = "Type number or name. Enter to cancel.",
    ) -> str | None:
        if not options:
            return None

        while True:
            display.menu_panel(title, options, current_value=current_value, prompt_hint=prompt_hint)
            raw_choice = await get_input_async(
                input_session,
                completer=MenuCompleter(options),
                prompt_markup="<cyan>select&gt;</cyan> ",
            )
            if raw_choice is None or not raw_choice.strip():
                return None
            choice = resolve_menu_choice(raw_choice, options)
            if choice is not None:
                return choice
            display.error("Unknown selection. Choose a number or listed option.")

    async def _prompt_text_value(
        prompt_markup: str,
        *,
        bottom_toolbar: str | None = None,
        password: bool = False,
    ) -> str | None:
        value = await get_input_async(
            input_session,
            prompt_markup=prompt_markup,
            bottom_toolbar=bottom_toolbar,
            password=password,
        )
        if value is None:
            return None
        return value.strip()

    async def _prompt_multiline_value(
        prompt_markup: str,
        *,
        bottom_toolbar: str | None = None,
    ) -> str | None:
        first_line = await get_input_async(
            input_session,
            prompt_markup=prompt_markup,
            bottom_toolbar=bottom_toolbar or 'Enter one line, or start with """ for multiline. Blank cancels.',
        )
        if first_line is None:
            return None
        if not first_line.strip():
            return None
        if not _starts_multiline_input(first_line):
            return first_line

        lines: list[str] = []
        initial = _multiline_initial_fragment(first_line)
        if initial:
            lines.append(initial)

        while True:
            line = await get_multiline_continuation_async(input_session)
            if line is None:
                return None
            if _is_multiline_terminator(line):
                break
            lines.append(line)
        return "\n".join(lines)

    async def _maybe_complete_provider_auth(
        *,
        provider_changed: bool,
        previous_issue: str | None,
    ) -> bool:
        issue = _provider_auth_issue(cfg.provider, cfg.api_key, cfg.oauth_token)
        if issue is None:
            return True
        if not provider_changed and previous_issue == issue:
            return False

        display.info(issue)
        if cfg.provider == "openai":
            toolbar = "Enter an OpenAI API key. Blank cancels. Or run 'god-code login' to use OAuth."
        else:
            provider_name = PROVIDER_PRESETS.get(cfg.provider).name if cfg.provider in PROVIDER_PRESETS else cfg.provider
            toolbar = f"Enter a {provider_name} API key. Blank cancels."

        entered_value = await _prompt_text_value(
            "<cyan>api_key&gt;</cyan> ",
            bottom_toolbar=toolbar,
            password=True,
        )
        if entered_value is None:
            return False
        if entered_value.upper() == "CLEAR":
            entered_value = ""
        if not entered_value:
            display.error("This provider does not have usable credentials yet.")
            return False
        return await _apply_setting_value("api_key", entered_value, prompt_for_auth=False)

    async def _apply_setting_value(key: str, value: str, *, prompt_for_auth: bool = True) -> bool:
        if not hasattr(cfg, key):
            display.error(f"Unknown setting: {key}")
            return False

        old_val = getattr(cfg, key)
        previous_provider = cfg.provider
        previous_issue = _provider_auth_issue(cfg.provider, cfg.api_key, cfg.oauth_token)
        try:
            if key == "mode":
                setattr(cfg, key, normalize_mode(value))
            elif key == "provider":
                _apply_provider_preset(cfg, value)
            elif key == "reasoning_effort":
                setattr(cfg, key, _normalize_reasoning_effort(value))
            elif key == "model":
                previous_provider = cfg.provider
                previous_base_url = cfg.base_url
                setattr(cfg, key, value)
                if not cfg.model:
                    raise ValueError("Usage: /model <name>")
                _sync_provider_from_model(cfg, previous_provider, previous_base_url)
            elif isinstance(old_val, bool):
                setattr(cfg, key, value.lower() in ("true", "1", "yes", "on", "enable", "enabled"))
            elif isinstance(old_val, int):
                setattr(cfg, key, int(value))
            elif isinstance(old_val, float):
                setattr(cfg, key, float(value))
            else:
                setattr(cfg, key, value)
        except ValueError as e:
            display.error(str(e))
            return False

        display.success(f"{key} = {_format_setting_display_value(key, getattr(cfg, key))}")
        if key == "base_url":
            cfg.provider = infer_provider(
                base_url=cfg.base_url,
                model=cfg.model,
                provider="",
            )

        persisted_updates: dict[str, object] = {key: getattr(cfg, key)}
        if key == "provider":
            persisted_updates.update({
                "base_url": cfg.base_url,
                "model": cfg.model,
            })
        elif key == "model":
            persisted_updates.update({
                "provider": cfg.provider,
                "base_url": cfg.base_url,
            })
        elif key == "base_url":
            persisted_updates.update({"provider": cfg.provider})

        _persist_config_updates(config_path, persisted_updates)

        if key in {
            "language",
            "verbosity",
            "extra_prompt",
            "auto_validate",
            "mode",
            "safety",
            "godot_path",
            "provider",
            "model",
            "base_url",
            "reasoning_effort",
            "api_key",
            "oauth_token",
            "max_tokens",
            "temperature",
        }:
            await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
            display.info("Engine rebuilt with updated settings")
        else:
            _wire_engine_callbacks(engine, display, cfg)
        _refresh_workspace()

        if prompt_for_auth and key in {"provider", "model", "base_url"}:
            provider_changed = cfg.provider != previous_provider
            await _maybe_complete_provider_auth(
                provider_changed=provider_changed or key == "provider",
                previous_issue=previous_issue,
            )
        return True

    async def _resume_session_target(target: str) -> bool:
        record = (
            load_latest_session(cfg.session_dir, project_path=str(project_root))
            if target == "latest"
            else load_session(cfg.session_dir, target)
        )
        if target == "latest" and record is None:
            record = load_latest_session(cfg.session_dir)
        if not record:
            display.error("No saved sessions found")
            return False

        if record.mode:
            try:
                cfg.mode = normalize_mode(record.mode)
            except ValueError:
                pass
        if record.skill_mode:
            try:
                cfg.skill_mode = normalize_skill_mode(record.skill_mode)
            except ValueError:
                cfg.skill_mode = "auto"
        cfg.enabled_skills = sanitize_skill_keys(record.enabled_skills)
        cfg.disabled_skills = sanitize_skill_keys(record.disabled_skills)

        resume_root = Path(record.project_path).expanduser().resolve() if record.project_path else project_root
        if record.project_path and not resume_root.exists():
            display.error(f"Saved project path no longer exists: {record.project_path}")
            return False

        if record.gameplay_intent:
            _persist_intent_profile(resume_root, gameplay_intent_from_data(record.gameplay_intent))

        loaded_messages = record.messages[1:] if record.messages and record.messages[0].role == "system" else record.messages
        await _replace_engine(
            resume_root,
            preserve_messages=False,
            seed_messages=loaded_messages,
            rescan_project=False,
            new_session_id=record.session_id,
        )
        display.success(f"Resumed session {record.session_id} ({record.message_count} messages)")
        _refresh_workspace()
        return True

    async def _show_mode_menu() -> bool:
        choice = await _prompt_menu_choice("Interaction Mode", _mode_menu_options(), current_value=cfg.mode)
        if choice is None:
            return False
        display.mode_panel(choice)
        return await _apply_setting_value("mode", choice)

    async def _show_provider_menu() -> bool:
        choice = await _prompt_menu_choice("Provider", _provider_menu_options(), current_value=cfg.provider)
        if choice is None:
            return False
        return await _apply_setting_value("provider", choice)

    async def _show_effort_menu() -> bool:
        choice = await _prompt_menu_choice("Reasoning Effort", _effort_menu_options(), current_value=cfg.reasoning_effort)
        if choice is None:
            return False
        return await _apply_setting_value("reasoning_effort", choice)

    def _skill_state_updates() -> dict[str, object]:
        return {
            "skill_mode": cfg.skill_mode,
            "enabled_skills": list(cfg.enabled_skills),
            "disabled_skills": list(cfg.disabled_skills),
        }

    async def _rebuild_for_skills(message: str) -> bool:
        _persist_config_updates(config_path, _skill_state_updates())
        await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
        display.success(message)
        _refresh_workspace()
        return True

    async def _show_skills_panel() -> bool:
        display.skills_panel(
            available=_skill_menu_options(),
            skill_mode=cfg.skill_mode,
            active_skills=_resolved_active_skill_keys(engine, cfg),
            enabled_skills=cfg.enabled_skills,
            disabled_skills=cfg.disabled_skills,
        )
        return True

    async def _show_intent_panel() -> bool:
        engine.refresh_intent_profile()
        display.intent_panel(_intent_profile_dict(engine))
        return True

    async def _show_quality_panel() -> bool:
        display.quality_panel(_quality_target(engine), _polish_profile_dict(engine))
        return True

    async def _show_asset_spec_panel() -> bool:
        display.asset_spec_panel(_asset_spec_dict(engine))
        return True

    async def _show_scenarios_panel(*, include_generated: bool = False) -> bool:
        tool = ListScenariosTool()
        result = await tool.execute(tool.Input(project_path=str(project_root), include_generated=include_generated))
        if result.error:
            display.error(result.error)
            return False
        display.scenarios_panel(result.output.scenarios, result.output.quality_target)
        return True

    async def _show_contracts_panel(selection: str = "") -> bool:
        normalized = selection.strip().lower()
        include_generated = normalized == "all"
        scenario_id = "" if normalized in {"", "relevant", "all"} else selection.strip()
        tool = ListContractsTool()
        result = await tool.execute(
            tool.Input(
                project_path=str(project_root),
                scenario_id=scenario_id,
                include_generated=include_generated,
                show_all=normalized == "all",
            )
        )
        if result.error:
            display.error(result.error)
            return False
        display.contracts_panel(result.output.contracts, result.output.quality_target)
        return True

    async def _run_scripted_playtest_command(selection: str = "") -> bool:
        raw = selection.strip()
        scenario_ids: list[str] = []
        if raw and raw.lower() not in {"relevant", "all"}:
            scenario_ids = [item.strip() for item in raw.split(",") if item.strip()]
        tool = RunScriptedPlaytestTool()
        changed_files = [str(path) for path in getattr(engine, "recent_changed_files", [])] if getattr(engine, "recent_changed_files", None) else []
        result = await tool.execute(
            tool.Input(
                project_path=str(project_root),
                scenario_ids=scenario_ids,
                changed_files=changed_files,
                run_all=raw.lower() == "all",
            )
        )
        if result.error:
            display.error(result.error)
            return False
        display.playtest_panel(
            verdict=result.output.verdict,
            gameplay_review_verdict=result.output.gameplay_review_verdict,
            report=result.output.report,
            scenarios=result.output.scenarios,
        )
        return True

    async def _edit_intent_profile(*, checkpoint: bool = False) -> bool:
        nonlocal intent_checkpoint_dismissed
        if not has_project:
            display.error("No project.godot found in the current directory.")
            return False

        current_profile = engine.refresh_intent_profile(engine.last_user_input)
        if checkpoint:
            display.info("Gameplay intent needs confirmation for this gameplay-level task.")
        display.intent_panel(current_profile.to_dict())

        answers: dict[str, str] = {}
        for question in intent_questions_for_profile(current_profile)[:3]:
            options = [
                MenuOption(option.value, option.label, option.description, aliases=(option.value,))
                for option in question.options
            ]
            current_value = answers.get(question.key) or getattr(current_profile, question.key) or None
            choice = await _prompt_menu_choice(
                f"Intent: {question.key.replace('_', ' ').title()}",
                options,
                current_value=current_value,
                prompt_hint=question.prompt,
            )
            if choice is None:
                if checkpoint:
                    intent_checkpoint_dismissed = True
                    display.info("Intent checkpoint skipped. Continuing with inferred profile.")
                return False
            answers[question.key] = choice

        updated = apply_intent_answers(current_profile, answers)
        _persist_intent_profile(project_root, updated)
        await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
        intent_checkpoint_dismissed = False
        display.success("Gameplay intent confirmed.")
        display.intent_panel(_intent_profile_dict(engine))
        _refresh_workspace()
        return True

    async def _apply_intent_command(action: str) -> bool:
        nonlocal intent_checkpoint_dismissed
        normalized = action.strip().lower()
        if normalized in {"", "status"}:
            return await _show_intent_panel()
        if normalized == "confirm":
            profile = engine.refresh_intent_profile(engine.last_user_input)
            if profile.is_empty:
                display.error("No gameplay intent could be inferred yet.")
                return False
            updated = gameplay_intent_from_data(profile.to_dict())
            updated.confirmed = True
            updated.confidence = 1.0
            _persist_intent_profile(project_root, updated)
            await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
            intent_checkpoint_dismissed = False
            display.success("Gameplay intent confirmed.")
            display.intent_panel(_intent_profile_dict(engine))
            _refresh_workspace()
            return True
        if normalized == "edit":
            return await _edit_intent_profile(checkpoint=False)
        if normalized == "clear":
            _persist_intent_profile(project_root, GameplayIntentProfile())
            await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
            intent_checkpoint_dismissed = False
            display.success("Gameplay intent cleared.")
            _refresh_workspace()
            return True
        display.error("Usage: /intent [status|confirm|edit|clear]")
        return False

    async def _apply_skill_command(action: str, raw_skill_name: str | None = None) -> bool:
        if action in {"", "list"}:
            return await _show_skills_panel()
        if action == "auto":
            cfg.skill_mode = "auto"
            cfg.enabled_skills = []
            cfg.disabled_skills = []
            return await _rebuild_for_skills("Skill overrides cleared. Auto selection restored.")
        if action == "clear":
            cfg.enabled_skills = []
            cfg.disabled_skills = []
            cfg.skill_mode = "auto"
            return await _rebuild_for_skills("Skill overrides cleared.")

        skill_key = normalize_skill_name(raw_skill_name)
        if skill_key is None:
            available = ", ".join(skill.key for skill in available_skills())
            display.error(f"Unknown skill: {raw_skill_name}. Available: {available}")
            return False

        if action == "on":
            cfg.skill_mode = "hybrid"
            cfg.disabled_skills = [item for item in cfg.disabled_skills if item != skill_key]
            if skill_key not in cfg.enabled_skills:
                cfg.enabled_skills = [*cfg.enabled_skills, skill_key]
            return await _rebuild_for_skills(f"Skill enabled: {skill_label(skill_key)}")

        if action == "off":
            cfg.skill_mode = "hybrid"
            cfg.enabled_skills = [item for item in cfg.enabled_skills if item != skill_key]
            if skill_key not in cfg.disabled_skills:
                cfg.disabled_skills = [*cfg.disabled_skills, skill_key]
            return await _rebuild_for_skills(f"Skill disabled: {skill_label(skill_key)}")

        display.error("Usage: /skills [list|on <name>|off <name>|auto|clear]")
        return False

    async def _show_model_menu() -> bool:
        choice = await _prompt_menu_choice("Model", _model_menu_options(cfg), current_value=cfg.model)
        if choice is None:
            return False
        if choice == "__custom__":
            raw_model = await _prompt_text_value("<cyan>model&gt;</cyan> ")
            if not raw_model:
                return False
            choice = raw_model
        return await _apply_setting_value("model", choice)

    async def _show_resume_menu() -> bool:
        sessions = list_sessions(cfg.session_dir, project_path=str(project_root))
        if not sessions:
            sessions = list_sessions(cfg.session_dir)
        if not sessions:
            display.error("No saved sessions found")
            return False
        choice = await _prompt_menu_choice(
            "Resume Session",
            _session_menu_options(sessions),
            prompt_hint="Type number or session id. Enter to cancel.",
        )
        if choice is None:
            return False
        return await _resume_session_target(choice)

    async def _show_cd_prompt() -> bool:
        display.info(f"Current project: {project_root}")
        new_path_value = await _prompt_text_value("<cyan>path&gt;</cyan> ", bottom_toolbar="Enter a project path. Blank cancels.")
        if not new_path_value:
            return False
        new_path = Path(new_path_value).expanduser().resolve()
        if not new_path.exists():
            display.error(f"Path not found: {new_path}")
            return False
        await _replace_engine(new_path, preserve_messages=False, new_session_id=str(uuid.uuid4())[:8])
        if has_project:
            display.success(f"Switched to: {proj_name} ({new_path})")
        else:
            display.info(f"Working dir: {new_path}")
        _refresh_workspace()
        return True

    async def _show_setting_menu() -> bool:
        setting_key = await _prompt_menu_choice("Settings", _settings_menu_options())
        if setting_key is None:
            return False

        if setting_key == "mode":
            return await _show_mode_menu()
        if setting_key == "provider":
            return await _show_provider_menu()
        if setting_key == "reasoning_effort":
            return await _show_effort_menu()
        if setting_key == "model":
            return await _show_model_menu()

        value_options = _setting_value_menu_options(setting_key)
        if value_options is not None:
            current_value = getattr(cfg, setting_key)
            normalized_current = str(current_value).lower() if isinstance(current_value, bool) else str(current_value)
            selected_value = await _prompt_menu_choice(
                f"Set {setting_key}",
                value_options,
                current_value=normalized_current,
            )
            if selected_value is None:
                return False
            return await _apply_setting_value(setting_key, selected_value)

        if setting_key in _SECRET_SETTING_KEYS:
            entered_value = await _prompt_text_value(
                f"<cyan>{setting_key}&gt;</cyan> ",
                bottom_toolbar="Hidden input. Type CLEAR to remove. Blank cancels.",
                password=True,
            )
            if entered_value is None:
                return False
            if entered_value.upper() == "CLEAR":
                entered_value = ""
            return await _apply_setting_value(setting_key, entered_value)

        if setting_key in _MULTILINE_SETTING_KEYS:
            entered_value = await _prompt_multiline_value(
                f"<cyan>{setting_key}&gt;</cyan> ",
                bottom_toolbar='Enter one line, or start with """ for multiline. Type CLEAR on a single line to remove.',
            )
            if entered_value is None:
                return False
            if entered_value.strip().upper() == "CLEAR":
                entered_value = ""
            return await _apply_setting_value(setting_key, entered_value)

        if setting_key in {"godot_path", "session_dir"}:
            entered_value = await _prompt_text_value(
                f"<cyan>{setting_key}&gt;</cyan> ",
                bottom_toolbar="Enter a path. Blank cancels.",
            )
        else:
            entered_value = await _prompt_text_value(f"<cyan>{setting_key}&gt;</cyan> ")
        if not entered_value:
            return False
        return await _apply_setting_value(setting_key, entered_value)

    async def _show_main_menu() -> str | None:
        choice = await _prompt_menu_choice("Command Menu", _main_menu_options())
        if choice is None:
            return None
        if choice == "mode":
            await _show_mode_menu()
            return "handled"
        if choice == "provider":
            await _show_provider_menu()
            return "handled"
        if choice == "model":
            await _show_model_menu()
            return "handled"
        if choice == "effort":
            await _show_effort_menu()
            return "handled"
        if choice == "skills":
            await _show_skills_panel()
            return "handled"
        if choice == "intent":
            await _show_intent_panel()
            return "handled"
        if choice == "quality":
            await _show_quality_panel()
            return "handled"
        if choice == "assetspec":
            await _show_asset_spec_panel()
            return "handled"
        if choice == "playtest":
            await _run_scripted_playtest_command("relevant")
            return "handled"
        if choice == "scenarios":
            await _show_scenarios_panel()
            return "handled"
        if choice == "contracts":
            await _show_contracts_panel("relevant")
            return "handled"
        if choice == "resume":
            await _show_resume_menu()
            return "handled"
        if choice == "cd":
            await _show_cd_prompt()
            return "handled"
        if choice == "set":
            await _show_setting_menu()
            return "handled"
        if choice == "workspace":
            _refresh_workspace()
            return "handled"
        if choice == "status":
            if cfg.provider == "custom" and not cfg.api_key and not cfg.oauth_token:
                auth = "Not required (custom provider)"
            else:
                auth = f"API key ({cfg.api_key[:8]}...)" if cfg.api_key else "OAuth" if cfg.oauth_token else "None"
            display.status_panel({
                "Provider": cfg.provider,
                "Model": cfg.model,
                "Effort": cfg.reasoning_effort,
                "Computer Use": f"{cfg.computer_use} ({cfg.computer_use_environment} {cfg.computer_use_display_width}x{cfg.computer_use_display_height})",
                "Skill Mode": cfg.skill_mode,
                "Active Skills": _format_skill_list(_resolved_active_skill_keys(engine, cfg)),
                "Enabled Skills": _format_skill_list(cfg.enabled_skills),
                "Disabled Skills": _format_skill_list(cfg.disabled_skills),
                "Mode": cfg.mode,
                "Project": str(project_root),
                "Godot": cfg.godot_path,
                "Auth": auth,
                "Language": cfg.language,
                "Verbosity": cfg.verbosity,
                **_intent_status_data(),
            })
            return "handled"
        if choice == "settings":
            display.settings_panel(cfg)
            return "handled"
        if choice == "sessions":
            sessions = list_sessions(cfg.session_dir, project_path=str(project_root))
            if not sessions:
                sessions = list_sessions(cfg.session_dir)
            display.session_list_panel(sessions)
            return "handled"
        if choice == "help":
            _refresh_workspace(show_commands=True)
            return "handled"
        if choice == "quit":
            return "quit"
        return None

    multiline_buffer: list[str] = []
    in_multiline = False

    async def _loop() -> None:
        nonlocal engine, in_multiline, multiline_buffer
        try:
            if has_project and engine.intent_profile.conflicts:
                await _edit_intent_profile(checkpoint=True)

            while True:
                try:
                    if in_multiline:
                        line = await get_multiline_continuation_async(input_session)
                        if _is_multiline_terminator(line):
                            in_multiline = False
                            user_input = "\n".join(multiline_buffer)
                            multiline_buffer = []
                        else:
                            multiline_buffer.append(line)
                            continue
                    else:
                        user_input = await get_input_async(input_session, completer, bottom_toolbar=_toolbar())
                        if user_input is None:
                            break
                        if _starts_multiline_input(user_input):
                            in_multiline = True
                            rest = _multiline_initial_fragment(user_input)
                            if rest:
                                multiline_buffer.append(rest)
                            continue
                except (EOFError, KeyboardInterrupt):
                    break

                stripped = user_input.strip()
                cmd = stripped.lower()

                if not _has_meaningful_input(user_input):
                    continue

                if cmd in ("/quit", "quit", "/exit", "exit"):
                    break

                if cmd in ("/save", "save"):
                    path = _save_chat_session(cfg, session_id, engine, project_root, proj_name)
                    display.info(f"Session saved to {path}")
                    continue

                if cmd in ("/load", "load"):
                    target = "latest"
                else:
                    resume_arg = _command_argument(user_input, "/resume")
                    if cmd in ("/resume", "resume") or resume_arg == "":
                        target = "__menu__"
                    else:
                        target = resume_arg or None if resume_arg is not None else None

                if target is not None:
                    if target == "__menu__":
                        await _show_resume_menu()
                    else:
                        await _resume_session_target(target)
                    continue

                if cmd == "/help":
                    _refresh_workspace(show_commands=True)
                    continue

                if cmd == "/workspace":
                    _refresh_workspace()
                    continue

                if cmd == "/sessions":
                    sessions = list_sessions(cfg.session_dir, project_path=str(project_root))
                    if not sessions:
                        sessions = list_sessions(cfg.session_dir)
                    display.session_list_panel(sessions)
                    continue

                if cmd == "/new":
                    await _replace_engine(project_root, preserve_messages=False, new_session_id=str(uuid.uuid4())[:8])
                    display.success(f"Started new session {session_id}")
                    _refresh_workspace()
                    continue

                if cmd == "/menu":
                    menu_result = await _show_main_menu()
                    if menu_result == "quit":
                        break
                    if menu_result == "handled":
                        continue

                if cmd == "/info":
                    if has_project:
                        from godot_agent.godot.project import parse_project_godot
                        proj = parse_project_godot(project_root / "project.godot")
                        display.info_panel({
                            "Project": proj.name,
                            "Version": proj.version,
                            "Main Scene": proj.main_scene,
                            "Resolution": f"{proj.viewport_width}x{proj.viewport_height}",
                            "Autoloads": str(len(proj.autoloads)),
                        })
                    else:
                        display.error(f"No project.godot in {project_root}")
                    continue

                mode_arg = _command_argument(user_input, "/mode")
                if cmd == "/mode" or mode_arg == "":
                    await _show_mode_menu()
                    continue

                if mode_arg:
                    await _apply_setting_value("mode", mode_arg)
                    continue

                provider_arg = _command_argument(user_input, "/provider")
                if cmd == "/provider" or provider_arg == "":
                    await _show_provider_menu()
                    continue

                if provider_arg:
                    await _apply_setting_value("provider", provider_arg)
                    continue

                model_arg = _command_argument(user_input, "/model")
                if cmd == "/model" or model_arg == "":
                    await _show_model_menu()
                    continue

                if model_arg is not None:
                    await _apply_setting_value("model", model_arg)
                    continue

                effort_arg = _command_argument(user_input, "/effort")
                if cmd == "/effort" or effort_arg == "":
                    await _show_effort_menu()
                    continue

                if effort_arg is not None:
                    await _apply_setting_value("reasoning_effort", effort_arg)
                    continue

                skills_arg = _command_argument(user_input, "/skills")
                if cmd == "/skills":
                    await _show_skills_panel()
                    continue
                if skills_arg is not None:
                    parts = skills_arg.split(None, 1)
                    action = parts[0].lower() if parts else ""
                    skill_name = parts[1] if len(parts) > 1 else None
                    await _apply_skill_command(action, skill_name)
                    continue

                intent_arg = _command_argument(user_input, "/intent")
                if cmd == "/intent":
                    await _show_intent_panel()
                    continue
                if intent_arg is not None:
                    await _apply_intent_command(intent_arg or "status")
                    continue

                if cmd == "/quality":
                    await _show_quality_panel()
                    continue

                if cmd == "/assetspec":
                    await _show_asset_spec_panel()
                    continue

                if cmd == "/scenarios":
                    await _show_scenarios_panel()
                    continue

                playtest_arg = _command_argument(user_input, "/playtest")
                if cmd == "/playtest":
                    await _run_scripted_playtest_command("relevant")
                    continue
                if playtest_arg is not None:
                    await _run_scripted_playtest_command(playtest_arg)
                    continue

                contracts_arg = _command_argument(user_input, "/contracts")
                if cmd == "/contracts":
                    await _show_contracts_panel("relevant")
                    continue
                if contracts_arg is not None:
                    await _show_contracts_panel(contracts_arg)
                    continue

                if cmd == "/usage":
                    sess = engine.session_usage
                    cost = sess.cost_estimate(cfg.model)
                    display.info_panel({
                        "Input tokens": f"{sess.prompt_tokens:,}",
                        "Output tokens": f"{sess.completion_tokens:,}",
                        "Total tokens": f"{sess.total_tokens:,}",
                        "API calls": str(engine.session_api_calls),
                        "Est. cost": f"${cost:.4f}",
                    })
                    continue

                if cmd == "/status":
                    if cfg.provider == "custom" and not cfg.api_key and not cfg.oauth_token:
                        auth = "Not required (custom provider)"
                    else:
                        auth = f"API key ({cfg.api_key[:8]}...)" if cfg.api_key else "OAuth" if cfg.oauth_token else "None"
                    display.status_panel({
                        "Provider": cfg.provider,
                        "Model": cfg.model,
                        "Effort": cfg.reasoning_effort,
                        "Computer Use": f"{cfg.computer_use} ({cfg.computer_use_environment} {cfg.computer_use_display_width}x{cfg.computer_use_display_height})",
                        "Skill Mode": cfg.skill_mode,
                        "Active Skills": _format_skill_list(_resolved_active_skill_keys(engine, cfg)),
                        "Enabled Skills": _format_skill_list(cfg.enabled_skills),
                        "Disabled Skills": _format_skill_list(cfg.disabled_skills),
                        "Mode": cfg.mode,
                        "Project": str(project_root),
                        "Godot": cfg.godot_path,
                        "Auth": auth,
                        "Language": cfg.language,
                        "Verbosity": cfg.verbosity,
                        **_intent_status_data(),
                    })
                    continue

                if cmd == "/settings":
                    display.settings_panel(cfg)
                    continue

                set_args = _set_arguments(user_input)
                if stripped == "/set" or set_args is not None:
                    if set_args is None:
                        await _show_setting_menu()
                        continue
                    key, val = set_args
                    await _apply_setting_value(key, val)
                    continue

                # Support both /cd and cd
                cd_input = _cd_argument(user_input)

                if cd_input is not None:
                    if not cd_input:
                        await _show_cd_prompt()
                        continue
                    new_path = Path(cd_input).expanduser().resolve()
                    if not new_path.exists():
                        display.error(f"Path not found: {new_path}")
                        continue
                    await _replace_engine(new_path, preserve_messages=False, new_session_id=str(uuid.uuid4())[:8])
                    if has_project:
                        display.success(f"Switched to: {proj_name} ({new_path})")
                    else:
                        display.info(f"Working dir: {new_path}")
                    _refresh_workspace()
                    continue

                # Regular message → send to LLM
                try:
                    engine.refresh_intent_profile(user_input)
                    if (
                        has_project
                        and not intent_checkpoint_dismissed
                        and should_prompt_for_intent(engine.intent_profile, user_hint=user_input)
                        and is_gameplay_architecture_task(user_input)
                    ):
                        await _edit_intent_profile(checkpoint=True)
                        engine.refresh_intent_profile(user_input)
                        _refresh_workspace()
                    if cfg.streaming and engine.on_stream_chunk:
                        response = await engine.submit(user_input)
                    else:
                        with display.thinking():
                            response = await engine.submit(user_input)
                        display.agent_response(response)
                except KeyboardInterrupt:
                    display.info("Cancelled")
                    continue
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code if e.response is not None else "?"
                    display.error(f"API request failed ({status_code}). The session is still active.")
                    continue

                # Token usage
                turn = engine.last_turn
                sess = engine.session_usage
                if turn:
                    display.usage_line(
                        turn.usage.total_tokens, turn.usage.prompt_tokens, turn.usage.completion_tokens,
                        turn.usage.cost_estimate(cfg.model), turn.tools_called,
                        sess.total_tokens, engine.session_api_calls, sess.cost_estimate(cfg.model),
                    )

                if cfg.autosave_session:
                    _save_chat_session(cfg, session_id, engine, project_root, proj_name)

                # Budget warning
                if cfg.token_budget > 0:
                    display.budget_warning(sess.total_tokens, cfg.token_budget)

        finally:
            if cfg.autosave_session:
                _save_chat_session(cfg, session_id, engine, project_root, proj_name)
            await engine.close()

    asyncio.run(_loop())
    sess = engine.session_usage
    display.session_summary(
        sess.total_tokens, sess.prompt_tokens, sess.completion_tokens,
        engine.session_api_calls, sess.cost_estimate(cfg.model),
    )


@main.command()
@click.option("--project", "-p", default=".", help="Path to Godot project root")
def info(project: str):
    """Show detected Godot project information."""
    project_root = Path(project).resolve()
    project_file = project_root / "project.godot"
    if not project_file.exists():
        click.echo(f"No project.godot found in {project_root}")
        return
    from godot_agent.godot.project import parse_project_godot
    proj = parse_project_godot(project_file)
    click.echo(f"Project:    {proj.name}")
    click.echo(f"Version:    {proj.version}")
    click.echo(f"Main Scene: {proj.main_scene}")
    click.echo(f"Resolution: {proj.viewport_width}x{proj.viewport_height}")
    click.echo(f"Autoloads:  {len(proj.autoloads)}")
    for name, path in proj.autoloads.items():
        click.echo(f"  {name} -> {path}")


@main.command("mcp")
@click.option("--project", "-p", default=".", help="Path to Godot project root")
def mcp_command(project: str):
    """Start MCP server (for Claude Code, Codex, and other AI agents).

    Exposes god-code's Godot tools via Model Context Protocol over stdio.
    No LLM needed — tools run locally, zero token cost.

    Configure in Claude Code:
    \b
    {
      "mcpServers": {
        "god-code": {
          "command": "god-code",
          "args": ["mcp", "--project", "/path/to/project"]
        }
      }
    }
    """
    from godot_agent.mcp_server import run_mcp_server
    run_mcp_server(project_path=project)


@main.command()
def tools():
    """List all available MCP tools with descriptions."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    try:
        from godot_agent.mcp_server import mcp as mcp_instance
        mcp_tools = mcp_instance._tool_manager._tools
    except Exception:
        console.print("[red]MCP not available. Install with: pip install god-code[mcp][/]")
        return

    t = Table(show_header=True, padding=(0, 1))
    t.add_column("#", style="dim", width=3)
    t.add_column("Tool", style="green bold")
    t.add_column("Description", style="dim")

    for i, (name, tool) in enumerate(sorted(mcp_tools.items()), 1):
        desc = (tool.description or "").split("\n")[0][:80]
        t.add_row(str(i), name, desc)

    console.print(Panel(t, title=f"[cyan]God Code MCP Tools ({len(mcp_tools)})[/]", border_style="cyan"))
    console.print()
    console.print("[dim]Use these tools via MCP in Claude Code, or directly in god-code chat.[/]")


@main.command("update-skill")
def update_skill():
    """Download/update the god-code-setup skill for Claude Code."""
    from pathlib import Path
    import httpx

    skill_dir = Path.home() / ".claude" / "skills" / "god-code-setup"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    url = "https://raw.githubusercontent.com/888wing/god-code/main/skills/god-code-setup/SKILL.md"

    click.echo(f"Downloading skill from {url}...")
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        skill_file.write_text(resp.text)
        click.secho(f"Skill updated: {skill_file}", fg="green")
        click.echo("Restart Claude Code to activate.")
    except Exception as e:
        click.secho(f"Failed: {e}", fg="red")


@main.command("setup-bridge")
@click.argument("project", default=".")
def setup_bridge(project: str):
    """Install GodCodeBridge plugin into a Godot project."""
    import shutil

    project_path = Path(project).resolve()
    project_godot = project_path / "project.godot"

    # Validate project
    if not project_godot.exists():
        click.secho(
            f"Error: No project.godot found in {project_path}",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    # Locate bundled plugin source
    source_dir = Path(__file__).resolve().parent.parent / "addons" / "god_code_bridge"
    if not source_dir.is_dir():
        click.secho(
            f"Error: Plugin source not found at {source_dir}",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    # Copy plugin to project addons/
    dest_dir = project_path / "addons" / "god_code_bridge"
    if dest_dir.exists():
        click.echo(f"  Updating existing plugin at {dest_dir}")
        shutil.rmtree(dest_dir)
    else:
        click.echo(f"  Installing plugin to {dest_dir}")
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source_dir), str(dest_dir))
    click.secho("  Plugin files copied.", fg="green")

    # Add autoload entry to project.godot
    autoload_line = 'GodCodeBridge="*res://addons/god_code_bridge/god_code_bridge.gd"'
    text = project_godot.read_text(encoding="utf-8")
    if "GodCodeBridge" in text:
        click.echo("  Autoload entry already exists in project.godot.")
    elif "[autoload]" in text:
        # Append under existing [autoload] section
        text = text.replace(
            "[autoload]",
            f"[autoload]\n\n{autoload_line}",
        )
        project_godot.write_text(text, encoding="utf-8")
        click.secho("  Autoload entry added to project.godot.", fg="green")
    else:
        # No [autoload] section yet — append one at the end
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n[autoload]\n\n{autoload_line}\n"
        project_godot.write_text(text, encoding="utf-8")
        click.secho("  [autoload] section created in project.godot.", fg="green")

    click.echo()
    click.secho("  GodCodeBridge installed successfully!", fg="cyan", bold=True)
    click.echo()
    click.echo("  Next steps:")
    click.echo("    1. Restart Godot (or reload the project)")
    click.echo("    2. Run your game — the bridge listens on TCP port 9394")
    click.echo("    3. Use 'god-code chat' to connect the AI agent")
    click.echo()


if __name__ == "__main__":
    main()

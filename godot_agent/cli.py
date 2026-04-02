# godot_agent/cli.py
from __future__ import annotations

import asyncio
import html
import json
import logging
import sys
import uuid
from pathlib import Path

import click
import httpx

from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.llm.client import LLMClient, LLMConfig
from godot_agent.llm.vision import encode_image
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.config import AgentConfig, default_config_path, load_config
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.modes import get_mode_spec, normalize_mode
from godot_agent.runtime.providers import (
    PROVIDER_PRESETS,
    REASONING_EFFORT_LEVELS,
    infer_provider,
    normalize_provider,
)
from godot_agent.runtime.session import list_sessions, load_latest_session, load_session, save_session
from godot_agent.tools.analysis_tools import (
    AnalyzeImpactTool,
    CheckConsistencyTool,
    ProjectDependencyGraphTool,
    ValidateProjectTool,
)
from godot_agent.tools.editor_bridge import GetRuntimeSnapshotTool, RunPlaytestTool
from godot_agent.tools.image_gen import GenerateSpriteTool
from godot_agent.tools.web_search import WebSearchTool
from godot_agent.tools.file_ops import EditFileTool, ReadFileTool, WriteFileTool
from godot_agent.tools.git import GitTool
from godot_agent.tools.godot_cli import RunGodotTool
from godot_agent.tools.list_dir import ListDirTool
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.scene_tools import (
    AddSceneConnectionTool,
    AddSceneNodeTool,
    ReadSceneTool,
    RemoveSceneNodeTool,
    SceneTreeTool,
    WriteScenePropertyTool,
)
from godot_agent.tools.screenshot import ScreenshotTool
from godot_agent.tools.search import GlobTool, GrepTool
from godot_agent.tools.shell import RunShellTool
from godot_agent.tools.memory_tool import ReadDesignMemoryTool, UpdateDesignMemoryTool
from godot_agent.tools.script_tools import EditScriptTool, LintScriptTool, ReadScriptTool

log = logging.getLogger(__name__)

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


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in [
        ReadFileTool, WriteFileTool, EditFileTool, ListDirTool,
        GrepTool, GlobTool, GitTool, RunShellTool, RunGodotTool, ScreenshotTool,
        ReadScriptTool, EditScriptTool, LintScriptTool,
        ReadSceneTool, SceneTreeTool, AddSceneNodeTool, WriteScenePropertyTool,
        AddSceneConnectionTool, RemoveSceneNodeTool,
        ValidateProjectTool, CheckConsistencyTool, ProjectDependencyGraphTool, AnalyzeImpactTool,
        ReadDesignMemoryTool, UpdateDesignMemoryTool,
        GetRuntimeSnapshotTool, RunPlaytestTool,
        GenerateSpriteTool, WebSearchTool,
    ]:
        registry.register(tool_cls())
    return registry


def build_engine(config: AgentConfig, project_root: Path) -> ConversationEngine:
    from godot_agent.tools.file_ops import set_project_root
    from godot_agent.tools.shell import set_safety_level
    set_project_root(project_root)
    set_safety_level(config.safety)

    llm_config = LLMConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        provider=config.provider,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        oauth_token=config.oauth_token,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    client = LLMClient(llm_config)
    registry = build_registry()
    prompt_assembler = PromptAssembler(
        PromptContext(
            project_root=project_root,
            godot_path=config.godot_path,
            language=config.language,
            verbosity=config.verbosity,
            mode=config.mode,
            extra_prompt=config.extra_prompt,
        )
    )
    allowed_tools = set(get_mode_spec(config.mode).allowed_tools)
    dispatcher = AgentDispatcher(
        client=client,
        registry=registry,
        prompt_context=prompt_assembler.context,
        project_path=str(project_root),
        godot_path=config.godot_path,
        base_allowed_tools=allowed_tools,
    )
    system_prompt = prompt_assembler.build(
        user_hint="",
        active_tools=[tool.name for tool in registry.list_tools() if tool.name in allowed_tools],
    )
    engine = ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=system_prompt,
        max_tool_rounds=config.max_turns,
        project_path=str(project_root),
        godot_path=config.godot_path,
        auto_validate=config.auto_validate,
        prompt_assembler=prompt_assembler,
        mode=config.mode,
        dispatcher=dispatcher,
    )
    engine.base_allowed_tools = set(allowed_tools)
    engine.allowed_tools = set(allowed_tools)
    return engine


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


def _toolbar_markup(cfg: AgentConfig, project_root: Path, project_name: str | None) -> str:
    mode_label = html.escape(get_mode_spec(cfg.mode).label)
    provider = html.escape(cfg.provider)
    model = html.escape(cfg.model)
    effort = html.escape(cfg.reasoning_effort)
    project = html.escape(project_name or project_root.name or str(project_root))
    return (
        f"<b>mode</b>: {mode_label} | "
        f"<b>provider</b>: {provider} | "
        f"<b>model</b>: {model} | "
        f"<b>effort</b>: {effort} | "
        f"<b>project</b>: {project} | "
        "<b>triple quotes</b>: multiline | "
        "<b>/help</b>"
    )


def _apply_provider_preset(cfg: AgentConfig, provider_name: str) -> str:
    provider = normalize_provider(provider_name)
    if provider not in PROVIDER_PRESETS:
        available = ", ".join(PROVIDER_PRESETS.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available: {available}")
    preset = PROVIDER_PRESETS[provider]
    cfg.provider = provider
    if preset.base_url:
        cfg.base_url = preset.base_url
    if preset.model:
        cfg.model = preset.model
    return provider


def _sync_provider_from_model(cfg: AgentConfig, previous_provider: str, previous_base_url: str) -> str:
    inferred = infer_provider(base_url=cfg.base_url, model=cfg.model, provider="")
    cfg.provider = inferred
    previous_preset = PROVIDER_PRESETS.get(previous_provider)
    new_preset = PROVIDER_PRESETS.get(inferred)
    if (
        new_preset
        and new_preset.base_url
        and ((previous_preset and previous_base_url == previous_preset.base_url) or not cfg.base_url)
    ):
        cfg.base_url = new_preset.base_url
    return inferred


def _normalize_reasoning_effort(value: str) -> str:
    effort = value.strip().lower()
    if effort not in REASONING_EFFORT_LEVELS:
        allowed = ", ".join(REASONING_EFFORT_LEVELS)
        raise ValueError(f"Unknown effort: {value}. Allowed: {allowed}")
    return effort


def _wire_engine_callbacks(
    engine: ConversationEngine,
    display,
    cfg: AgentConfig,
) -> None:
    engine.on_tool_start = lambda name, args: display.tool_start(name, engine._summarize_args(name, args))
    engine.on_tool_end = lambda name, ok, summary: display.tool_result(name, ok, summary)
    engine.on_diff = lambda old, new, fn: display.show_diff(old, new, fn)
    engine.on_event = display.handle_event
    engine.auto_commit = cfg.auto_commit
    engine.use_streaming = cfg.streaming
    if cfg.streaming:
        engine.on_stream_start = display.agent_streaming_start
        engine.on_stream_chunk = display.agent_streaming_chunk
        engine.on_stream_end = display.agent_streaming_end
    else:
        engine.on_stream_start = None
        engine.on_stream_chunk = None
        engine.on_stream_end = None
    engine.on_commit_suggest = lambda: display.info("Changes made. Run 'git add -A && git commit' to save.")


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
    )


def _is_configured() -> bool:
    """Check if god-code has been configured with an API key."""
    cfg = load_config(default_config_path())
    return bool(cfg.api_key or cfg.oauth_token)


def _run_setup_wizard() -> None:
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
        api_key = click.prompt("  API key (leave empty if none)", default="", show_default=False)
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
    config_path = default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config_data, indent=2))
    config_path.chmod(0o600)

    click.echo()
    click.secho(f"  Config saved to {config_path}", fg="green")
    click.echo()
    click.echo("  Ready! Try:")
    click.echo("    god-code chat -p ./your-godot-project")
    click.echo("    god-code ask \"Add a health bar\" -p ./your-game")
    click.echo("    god-code info -p ./your-game")
    click.echo()


_VERSION = "0.5.1"


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


@click.group(invoke_without_command=True)
@click.version_option(version=_VERSION)
@click.pass_context
def main(ctx):
    """God Code -- AI coding assistant for Godot game development."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    _check_update()
    if ctx.invoked_subcommand is None:
        if not _is_configured():
            _run_setup_wizard()
        else:
            ctx.invoke(chat)


@main.command()
def setup():
    """Run the interactive setup wizard (reconfigure provider/API key)."""
    _run_setup_wizard()


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
    click.echo(f"Base URL: {cfg.base_url}")
    click.echo(f"Godot:    {cfg.godot_path}")
    if cfg.oauth_token:
        click.echo(f"Auth:     OAuth token ({cfg.oauth_token[:8]}...)")
    elif cfg.api_key:
        click.echo(f"Auth:     API key ({cfg.api_key[:8]}...)")
    else:
        click.secho("Auth:     Not configured. Run 'god-code setup'.", fg="yellow")


@main.command()
@click.argument("prompt")
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--image", "-i", multiple=True, help="Reference image paths")
@click.option("--plain", is_flag=True, help="Print only the final response")
def ask(prompt: str, project: str, config: str | None, image: tuple[str, ...], plain: bool):
    """Send a single prompt to the agent."""
    from godot_agent.tui.display import ChatDisplay

    cfg = load_config(Path(config) if config else default_config_path())
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"
    if not cfg.api_key and not cfg.oauth_token:
        click.secho("Not configured. Run 'god-code setup' first.", fg="yellow", err=True)
        raise SystemExit(1)
    project_root = Path(project).resolve()
    show_rich = sys.stdout.isatty() and not plain
    engine = build_engine(cfg, project_root)
    display = ChatDisplay()

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

    display = ChatDisplay()
    cfg = load_config(Path(config) if config else default_config_path())
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"
    if not cfg.api_key and not cfg.oauth_token:
        display.error("Not configured. Run 'god-code setup' first.")
        raise SystemExit(1)

    project_root = Path(project).resolve()
    session_id = str(uuid.uuid4())[:8]
    has_project, proj_name, project_info = _project_details(project_root)

    display.welcome(
        session_id,
        cfg.model,
        proj_name,
        str(project_root),
        cfg.mode,
        provider=cfg.provider,
        effort=cfg.reasoning_effort,
    )
    if not has_project:
        display.no_project_warning()
    engine = build_engine(cfg, project_root)
    _wire_engine_callbacks(engine, display, cfg)

    # Auto-scan project on entry
    if has_project:
        scan_result = engine.scan_project()
        if scan_result:
            project_info["File Count"] = str(scan_result.file_count)
            project_info["Guide"] = scan_result.guide_file or "-"
            display.info(f"Project auto-scanned: {scan_result.file_count} files")
    display.update_project_info(project_info)
    display.workspace_snapshot(show_commands=True)

    # Setup prompt_toolkit for history + autocomplete
    from godot_agent.tui.input_handler import CommandCompleter, create_session as create_input_session
    history_file = str(Path.home() / ".config" / "god-code" / "history")
    Path(history_file).parent.mkdir(parents=True, exist_ok=True)
    input_session = create_input_session(history_file)
    completer = CommandCompleter(project_root)

    def _refresh_workspace(show_commands: bool = False) -> None:
        display.configure_workspace(
            session_id=session_id,
            provider=cfg.provider,
            model=cfg.model,
            effort=cfg.reasoning_effort,
            mode=cfg.mode,
            project_name=proj_name,
            project_path=str(project_root),
            project_info=project_info,
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
        nonlocal engine, project_root, has_project, proj_name, project_info, completer, session_id
        old_messages = engine.messages[1:] if preserve_messages else []
        previous_root = project_root
        previous_project_info = dict(project_info)
        await engine.close()

        project_root = new_root.resolve()
        has_project, proj_name, project_info = _project_details(project_root)
        engine = build_engine(cfg, project_root)
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

        display.configure_workspace(
            session_id=session_id,
            provider=cfg.provider,
            model=cfg.model,
            effort=cfg.reasoning_effort,
            mode=cfg.mode,
            project_name=proj_name,
            project_path=str(project_root),
            project_info=project_info,
        )
        if not has_project:
            display.no_project_warning()

    def _toolbar() -> str:
        return _toolbar_markup(cfg, project_root, proj_name)

    multiline_buffer: list[str] = []
    in_multiline = False

    async def _loop() -> None:
        nonlocal engine, in_multiline, multiline_buffer
        try:
            while True:
                try:
                    if in_multiline:
                        from godot_agent.tui.input_handler import get_multiline_continuation_async
                        line = await get_multiline_continuation_async(input_session)
                        if _is_multiline_terminator(line):
                            in_multiline = False
                            user_input = "\n".join(multiline_buffer)
                            multiline_buffer = []
                        else:
                            multiline_buffer.append(line)
                            continue
                    else:
                        from godot_agent.tui.input_handler import get_input_async
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

                if cmd in ("/load", "/resume", "resume"):
                    target = "latest"
                else:
                    resume_arg = _command_argument(user_input, "/resume")
                    target = resume_arg or "latest" if resume_arg is not None else None

                if target is not None:
                    record = (
                        load_latest_session(cfg.session_dir, project_path=str(project_root))
                        if target == "latest"
                        else load_session(cfg.session_dir, target)
                    )
                    if target == "latest" and record is None:
                        record = load_latest_session(cfg.session_dir)
                    if not record:
                        display.error("No saved sessions found")
                        continue

                    if record.mode:
                        try:
                            cfg.mode = normalize_mode(record.mode)
                        except ValueError:
                            pass

                    resume_root = Path(record.project_path).expanduser().resolve() if record.project_path else project_root
                    if record.project_path and not resume_root.exists():
                        display.error(f"Saved project path no longer exists: {record.project_path}")
                        continue

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
                    display.mode_panel(cfg.mode)
                    continue

                if mode_arg:
                    try:
                        cfg.mode = normalize_mode(mode_arg)
                    except ValueError as e:
                        display.error(str(e))
                        continue
                    await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
                    display.update_mode(cfg.mode)
                    display.success(f"Mode = {cfg.mode}")
                    _refresh_workspace()
                    continue

                provider_arg = _command_argument(user_input, "/provider")
                if cmd == "/provider" or provider_arg == "":
                    display.info_panel({
                        "Provider": cfg.provider,
                        "Base URL": cfg.base_url,
                        "Default model": cfg.model,
                        "Available": ", ".join(PROVIDER_PRESETS.keys()),
                    })
                    continue

                if provider_arg:
                    try:
                        provider = _apply_provider_preset(cfg, provider_arg)
                    except ValueError as e:
                        display.error(str(e))
                        continue
                    await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
                    display.success(f"Provider = {provider} ({cfg.model})")
                    _refresh_workspace()
                    continue

                model_arg = _command_argument(user_input, "/model")
                if cmd == "/model" or model_arg == "":
                    display.info_panel({
                        "Provider": cfg.provider,
                        "Model": cfg.model,
                        "Base URL": cfg.base_url,
                    })
                    continue

                if model_arg is not None:
                    previous_provider = cfg.provider
                    previous_base_url = cfg.base_url
                    cfg.model = model_arg
                    if not cfg.model:
                        display.error("Usage: /model <name>")
                        continue
                    _sync_provider_from_model(cfg, previous_provider, previous_base_url)
                    await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
                    display.success(f"Model = {cfg.model}")
                    _refresh_workspace()
                    continue

                effort_arg = _command_argument(user_input, "/effort")
                if cmd == "/effort" or effort_arg == "":
                    display.info_panel({
                        "Effort": cfg.reasoning_effort,
                        "Allowed": ", ".join(REASONING_EFFORT_LEVELS),
                        "Provider": cfg.provider,
                    })
                    continue

                if effort_arg is not None:
                    try:
                        if not effort_arg:
                            raise ValueError("Usage: /effort <level>")
                        cfg.reasoning_effort = _normalize_reasoning_effort(effort_arg)
                    except ValueError as e:
                        display.error(str(e))
                        continue
                    await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
                    display.success(f"Effort = {cfg.reasoning_effort}")
                    _refresh_workspace()
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
                    auth = f"API key ({cfg.api_key[:8]}...)" if cfg.api_key else "OAuth" if cfg.oauth_token else "None"
                    display.status_panel({
                        "Provider": cfg.provider,
                        "Model": cfg.model,
                        "Effort": cfg.reasoning_effort,
                        "Mode": cfg.mode,
                        "Project": str(project_root),
                        "Godot": cfg.godot_path,
                        "Auth": auth,
                        "Language": cfg.language,
                        "Verbosity": cfg.verbosity,
                    })
                    continue

                if cmd == "/settings":
                    display.settings_panel(cfg)
                    continue

                set_args = _set_arguments(user_input)
                if stripped == "/set" or set_args is not None:
                    if set_args is None:
                        display.error("Usage: /set <key> <value>")
                        continue
                    key, val = set_args
                    if hasattr(cfg, key):
                        old_val = getattr(cfg, key)
                        try:
                            if key == "mode":
                                setattr(cfg, key, normalize_mode(val))
                            elif key == "provider":
                                _apply_provider_preset(cfg, val)
                            elif key == "reasoning_effort":
                                setattr(cfg, key, _normalize_reasoning_effort(val))
                            elif key == "model":
                                previous_provider = cfg.provider
                                previous_base_url = cfg.base_url
                                setattr(cfg, key, val)
                                _sync_provider_from_model(cfg, previous_provider, previous_base_url)
                            elif isinstance(old_val, bool):
                                setattr(cfg, key, val.lower() in ("true", "1", "yes", "on"))
                            elif isinstance(old_val, int):
                                setattr(cfg, key, int(val))
                            elif isinstance(old_val, float):
                                setattr(cfg, key, float(val))
                            else:
                                setattr(cfg, key, val)
                        except ValueError as e:
                            display.error(str(e))
                            continue

                        display.success(f"{key} = {getattr(cfg, key)}")
                        if key == "base_url":
                            cfg.provider = infer_provider(
                                base_url=cfg.base_url,
                                model=cfg.model,
                                provider="",
                            )

                        if key in (
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
                        ):
                            await _replace_engine(project_root, preserve_messages=True, rescan_project=False)
                            display.info("Engine rebuilt with updated settings")
                        else:
                            _wire_engine_callbacks(engine, display, cfg)
                        _refresh_workspace()
                    else:
                        display.error(f"Unknown setting: {key}")
                    continue

                # Support both /cd and cd
                cd_input = _cd_argument(user_input)

                if cd_input is not None:
                    if not cd_input:
                        display.error("Usage: /cd <path>")
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


if __name__ == "__main__":
    main()

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
from godot_agent.tui.input_handler import MenuOption, resolve_menu_choice

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


def _settings_menu_options() -> list[MenuOption]:
    descriptions = {
        "api_key": "Update the provider API key (hidden input).",
        "provider": "Switch provider family and default base URL/model.",
        "base_url": "Edit the API base URL manually.",
        "model": "Switch the active model name.",
        "reasoning_effort": "Change reasoning depth.",
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
    if key in {"auto_validate", "auto_commit", "streaming", "autosave_session"}:
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


def _save_config_data(config_path: Path, data: dict) -> Path:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2))
    config_path.chmod(0o600)
    return config_path


def _persist_config_updates(config_path: Path, updates: dict[str, object]) -> Path:
    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return _save_config_data(config_path, data)


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _provider_auth_issue(provider: str, api_key: str = "", oauth_token: str | None = None) -> str | None:
    normalized_provider = normalize_provider(provider)
    preset = PROVIDER_PRESETS.get(normalized_provider)

    if normalized_provider == "custom":
        return None

    if normalized_provider == "openai":
        if api_key or oauth_token:
            return None
        return "OpenAI requires an API key or an OAuth login."

    if not api_key:
        provider_name = preset.name if preset else normalized_provider
        return f"{provider_name} requires an API key."

    if preset and preset.key_prefix and not api_key.startswith(preset.key_prefix):
        return f"Current API key does not look like a {preset.name} key (expected prefix {preset.key_prefix})."

    return None


def _has_usable_provider_auth(cfg: AgentConfig) -> bool:
    return _provider_auth_issue(cfg.provider, cfg.api_key, cfg.oauth_token) is None


def _load_or_setup_config(config_path: Path) -> AgentConfig:
    cfg = load_config(config_path)
    if _has_usable_provider_auth(cfg):
        return cfg

    if _is_interactive_terminal():
        _run_setup_wizard(config_path)
        cfg = load_config(config_path)
        if _has_usable_provider_auth(cfg):
            return cfg

    raise click.ClickException("Not configured. Run 'god-code setup' first.")


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
    return _has_usable_provider_auth(cfg)


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


_VERSION = "0.5.3"


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
    cfg = _load_or_setup_config(config_path)
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"
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
    config_path = Path(config) if config else default_config_path()
    cfg = _load_or_setup_config(config_path)
    try:
        cfg.mode = normalize_mode(cfg.mode)
    except ValueError:
        cfg.mode = "apply"

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

        resume_root = Path(record.project_path).expanduser().resolve() if record.project_path else project_root
        if record.project_path and not resume_root.exists():
            display.error(f"Saved project path no longer exists: {record.project_path}")
            return False

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
                "Mode": cfg.mode,
                "Project": str(project_root),
                "Godot": cfg.godot_path,
                "Auth": auth,
                "Language": cfg.language,
                "Verbosity": cfg.verbosity,
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

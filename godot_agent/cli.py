# godot_agent/cli.py
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import click

from godot_agent.llm.client import LLMClient, LLMConfig
from godot_agent.llm.vision import encode_image
from godot_agent.prompts.system import build_system_prompt
from godot_agent.runtime.config import AgentConfig, default_config_path, load_config
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.session import save_session
from godot_agent.tools.file_ops import EditFileTool, ReadFileTool, WriteFileTool
from godot_agent.tools.git import GitTool
from godot_agent.tools.godot_cli import RunGodotTool
from godot_agent.tools.list_dir import ListDirTool
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.screenshot import ScreenshotTool
from godot_agent.tools.search import GlobTool, GrepTool
from godot_agent.tools.shell import RunShellTool

log = logging.getLogger(__name__)

_PROVIDERS = {
    "1": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.4",
        "key_url": "https://platform.openai.com/api-keys",
        "key_prefix": "sk-",
    },
    "2": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o",
        "key_url": "https://openrouter.ai/keys",
        "key_prefix": "sk-or-",
    },
    "3": {
        "name": "Custom",
        "base_url": "",
        "model": "",
        "key_url": "",
        "key_prefix": "",
    },
}


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in [
        ReadFileTool, WriteFileTool, EditFileTool, ListDirTool,
        GrepTool, GlobTool, GitTool, RunShellTool, RunGodotTool, ScreenshotTool,
    ]:
        registry.register(tool_cls())
    return registry


def build_engine(config: AgentConfig, project_root: Path) -> ConversationEngine:
    from godot_agent.tools.file_ops import set_project_root
    set_project_root(project_root)

    llm_config = LLMConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        oauth_token=config.oauth_token,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    client = LLMClient(llm_config)
    registry = build_registry()
    system_prompt = build_system_prompt(
        project_root,
        godot_path=config.godot_path,
        language=config.language,
        verbosity=config.verbosity,
        extra_prompt=config.extra_prompt,
    )
    return ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=system_prompt,
        max_tool_rounds=config.max_turns,
        project_path=str(project_root),
        godot_path=config.godot_path,
        auto_validate=config.auto_validate,
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
    click.echo("  1. OpenAI          (gpt-5.4, vision, tool calling)")
    click.echo("     Get a key at: https://platform.openai.com/api-keys")
    click.echo()
    click.echo("  2. OpenRouter      (access all models with one key)")
    click.echo("     Get a key at: https://openrouter.ai/keys")
    click.echo()
    click.echo("  3. Custom provider (local models, self-hosted, etc.)")
    click.echo()

    choice = ""
    while choice not in _PROVIDERS:
        choice = click.prompt("  Select provider", type=str, default="1")

    provider = _PROVIDERS[choice]
    config_data: dict = {}

    if choice == "3":
        config_data["base_url"] = click.prompt("  Base URL", default="http://localhost:11434/v1")
        config_data["model"] = click.prompt("  Model name", default="llama3")
        api_key = click.prompt("  API key (leave empty if none)", default="", show_default=False)
        if api_key:
            config_data["api_key"] = api_key
    else:
        config_data["base_url"] = provider["base_url"]
        config_data["model"] = provider["model"]
        click.echo()
        api_key = click.prompt(f"  Paste your {provider['name']} API key", hide_input=True)
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
            model=config_data["model"],
            max_tokens=50,
        )
        client = LLMClient(llm_config)
        try:
            from godot_agent.llm.client import Message
            resp = await client.chat([Message.user("Say OK")])
            return bool(resp.content)
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


_VERSION = "0.4.0"


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
    click.echo(f"Model:    {cfg.model}")
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
def ask(prompt: str, project: str, config: str | None, image: tuple[str, ...]):
    """Send a single prompt to the agent."""
    cfg = load_config(Path(config) if config else default_config_path())
    if not cfg.api_key and not cfg.oauth_token:
        click.secho("Not configured. Run 'god-code setup' first.", fg="yellow", err=True)
        raise SystemExit(1)
    project_root = Path(project).resolve()
    engine = build_engine(cfg, project_root)

    async def _run() -> str:
        try:
            if image:
                images_b64 = [encode_image(p) for p in image]
                return await engine.submit_with_images(prompt, images_b64)
            return await engine.submit(prompt)
        finally:
            await engine.close()

    result = asyncio.run(_run())
    click.echo(result)


@main.command()
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
def chat(project: str = ".", config: str | None = None):
    """Start an interactive chat session."""
    from godot_agent.tui.display import ChatDisplay

    display = ChatDisplay()
    cfg = load_config(Path(config) if config else default_config_path())
    if not cfg.api_key and not cfg.oauth_token:
        display.error("Not configured. Run 'god-code setup' first.")
        raise SystemExit(1)

    project_root = Path(project).resolve()
    session_id = str(uuid.uuid4())[:8]
    has_project = (project_root / "project.godot").exists()

    proj_name = None
    if has_project:
        from godot_agent.godot.project import parse_project_godot
        proj_name = parse_project_godot(project_root / "project.godot").name

    display.welcome(session_id, cfg.model, proj_name, str(project_root))
    if not has_project:
        display.no_project_warning()
    cmd_table = display.commands_table()
    display.console.print(cmd_table)
    display.console.print()

    engine = build_engine(cfg, project_root)

    # Wire tool callbacks to TUI
    engine.on_tool_start = lambda name, args: display.tool_start(name, engine._summarize_args(name, args))
    engine.on_tool_end = lambda name, ok, err: display.tool_result(name, ok, err)
    engine.on_diff = lambda old, new, fn: display.show_diff(old, new, fn)

    # Auto-scan project on entry
    if has_project:
        scan_result = engine.scan_project()
        if scan_result:
            display.info(f"Project auto-scanned: {scan_result}")

    def _rebuild_engine(new_root: Path) -> ConversationEngine:
        nonlocal project_root, has_project, proj_name
        project_root = new_root.resolve()
        has_project = (project_root / "project.godot").exists()
        if has_project:
            from godot_agent.godot.project import parse_project_godot
            proj_name = parse_project_godot(project_root / "project.godot").name
        else:
            proj_name = None
        eng = build_engine(cfg, project_root)
        eng.on_tool_start = lambda name, args: display.tool_start(name, eng._summarize_args(name, args))
        eng.on_tool_end = lambda name, ok, err: display.tool_result(name, ok, err)
        eng.on_diff = lambda old, new, fn: display.show_diff(old, new, fn)
        if has_project:
            eng.scan_project()
        return eng

    multiline_buffer: list[str] = []
    in_multiline = False

    async def _loop() -> None:
        nonlocal engine, in_multiline, multiline_buffer
        try:
            while True:
                try:
                    if in_multiline:
                        line = display.console.input("[dim]...[/] ")
                        if line.strip() == '"""':
                            in_multiline = False
                            user_input = "\n".join(multiline_buffer)
                            multiline_buffer = []
                        else:
                            multiline_buffer.append(line)
                            continue
                    else:
                        user_input = display.console.input("[green]you>[/] ")
                        if user_input.strip().startswith('"""'):
                            in_multiline = True
                            rest = user_input.strip()[3:]
                            if rest:
                                multiline_buffer.append(rest)
                            continue
                except (EOFError, KeyboardInterrupt):
                    break

                cmd = user_input.strip().lower()

                if cmd in ("/quit", "quit", "/exit", "exit"):
                    break

                if cmd in ("/save", "save"):
                    path = save_session(cfg.session_dir, session_id, engine.messages)
                    display.info(f"Session saved to {path}")
                    continue

                if cmd == "/load":
                    from godot_agent.runtime.session import load_session as _load_sess
                    import os
                    sess_dir = cfg.session_dir
                    if os.path.exists(sess_dir):
                        files = sorted(Path(sess_dir).glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
                        if files:
                            display.info(f"Loading: {files[0].name}")
                            # Note: restore is informational — messages are raw dicts
                            display.success("Session history loaded for context")
                        else:
                            display.error("No saved sessions found")
                    else:
                        display.error("No saved sessions found")
                    continue

                if cmd == "/help":
                    display.console.print(cmd_table)
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
                        "Model": cfg.model,
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

                if user_input.strip().startswith("/set "):
                    parts = user_input.strip().split(None, 2)
                    if len(parts) == 3:
                        key, val = parts[1], parts[2]
                        if hasattr(cfg, key):
                            # Convert types
                            old_val = getattr(cfg, key)
                            if isinstance(old_val, bool):
                                setattr(cfg, key, val.lower() in ("true", "1", "yes"))
                            elif isinstance(old_val, int):
                                setattr(cfg, key, int(val))
                            else:
                                setattr(cfg, key, val)
                            display.success(f"{key} = {getattr(cfg, key)}")
                            # Rebuild engine if prompt-affecting setting changed
                            if key in ("language", "verbosity", "extra_prompt", "auto_validate"):
                                await engine.close()
                                engine = _rebuild_engine(project_root)
                                display.info("Engine rebuilt with new settings")
                        else:
                            display.error(f"Unknown setting: {key}")
                    else:
                        display.error("Usage: /set <key> <value>")
                    continue

                # Support both /cd and cd
                cd_input = user_input.strip()
                if cd_input.startswith("/cd "):
                    cd_input = cd_input[4:]
                elif cd_input.startswith("cd "):
                    cd_input = cd_input[3:]
                else:
                    cd_input = None

                if cd_input is not None:
                    new_path = Path(cd_input).expanduser().resolve()
                    if not new_path.exists():
                        display.error(f"Path not found: {new_path}")
                        continue
                    await engine.close()
                    engine = _rebuild_engine(new_path)
                    if has_project:
                        display.success(f"Switched to: {proj_name} ({new_path})")
                    else:
                        display.info(f"Working dir: {new_path}")
                        display.no_project_warning()
                    continue

                # Regular message → send to LLM
                try:
                    with display.thinking():
                        response = await engine.submit(user_input)
                except KeyboardInterrupt:
                    display.info("Cancelled")
                    continue

                display.agent_response(response)

                # Token usage
                turn = engine.last_turn
                sess = engine.session_usage
                if turn:
                    display.usage_line(
                        turn.usage.total_tokens, turn.usage.prompt_tokens, turn.usage.completion_tokens,
                        turn.usage.cost_estimate(cfg.model), turn.tools_called,
                        sess.total_tokens, engine.session_api_calls, sess.cost_estimate(cfg.model),
                    )

                # Budget warning
                if cfg.token_budget > 0:
                    display.budget_warning(sess.total_tokens, cfg.token_budget)

        finally:
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

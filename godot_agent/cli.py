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
    system_prompt = build_system_prompt(project_root)
    return ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=system_prompt,
        max_tool_rounds=config.max_turns,
        project_path=str(project_root),
        godot_path=config.godot_path,
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


_VERSION = "0.2.0"


def _check_update() -> None:
    """Check PyPI for a newer version. Non-blocking, fails silently."""
    try:
        import httpx as _httpx
        resp = _httpx.get("https://pypi.org/pypi/god-code/json", timeout=3)
        if resp.status_code == 200:
            latest = resp.json()["info"]["version"]
            if latest != _VERSION:
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
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    cfg = load_config(Path(config) if config else default_config_path())
    if not cfg.api_key and not cfg.oauth_token:
        console.print("[yellow]Not configured. Run 'god-code setup' first.[/]")
        raise SystemExit(1)

    project_root = Path(project).resolve()
    session_id = str(uuid.uuid4())[:8]
    has_project = (project_root / "project.godot").exists()

    # Welcome banner
    console.print()
    title = Text("God Code", style="bold cyan")
    subtitle_parts = [f"Session: {session_id}", f"Model: {cfg.model}"]
    if has_project:
        from godot_agent.godot.project import parse_project_godot
        proj = parse_project_godot(project_root / "project.godot")
        subtitle_parts.append(f"Project: {proj.name}")
    else:
        subtitle_parts.append(f"Dir: {project_root.name}")
    subtitle = Text(" | ".join(subtitle_parts), style="dim")
    console.print(Panel(title, subtitle=subtitle, border_style="cyan", padding=(0, 2)))

    if not has_project:
        console.print("[yellow]  No project.godot found. Use /cd to navigate to a Godot project.[/]")

    # Commands table
    cmd_table = Table(show_header=False, box=None, padding=(0, 2), show_edge=False)
    cmd_table.add_column(style="green")
    cmd_table.add_column(style="dim")
    cmd_table.add_row("/cd <path>", "change project directory")
    cmd_table.add_row("/info", "show project details")
    cmd_table.add_row("/status", "show model & auth")
    cmd_table.add_row("/save", "save session")
    cmd_table.add_row("/quit", "exit")
    console.print(cmd_table)
    console.print()

    engine = build_engine(cfg, project_root)

    def _rebuild_engine(new_root: Path) -> ConversationEngine:
        nonlocal project_root, has_project
        project_root = new_root.resolve()
        has_project = (project_root / "project.godot").exists()
        return build_engine(cfg, project_root)

    async def _loop() -> None:
        nonlocal engine
        try:
            while True:
                try:
                    user_input = console.input("[green]you>[/] ")
                except (EOFError, KeyboardInterrupt):
                    break

                cmd = user_input.strip().lower()

                if cmd in ("/quit", "quit", "/exit", "exit"):
                    break

                if cmd in ("/save", "save"):
                    path = save_session(cfg.session_dir, session_id, engine.messages)
                    console.print(f"  [dim]Session saved to {path}[/]")
                    continue

                if cmd == "/help":
                    console.print(cmd_table)
                    continue

                if cmd == "/info":
                    if has_project:
                        from godot_agent.godot.project import parse_project_godot
                        proj = parse_project_godot(project_root / "project.godot")
                        info_table = Table(show_header=False, box=None, padding=(0, 1))
                        info_table.add_column(style="bold")
                        info_table.add_column()
                        info_table.add_row("Project", proj.name)
                        info_table.add_row("Version", proj.version)
                        info_table.add_row("Main Scene", proj.main_scene)
                        info_table.add_row("Resolution", f"{proj.viewport_width}x{proj.viewport_height}")
                        info_table.add_row("Autoloads", str(len(proj.autoloads)))
                        console.print(Panel(info_table, title="Project Info", border_style="blue"))
                    else:
                        console.print(f"[yellow]  No project.godot in {project_root}[/]")
                    continue

                if cmd == "/status":
                    st = Table(show_header=False, box=None, padding=(0, 1))
                    st.add_column(style="bold")
                    st.add_column()
                    st.add_row("Model", cfg.model)
                    st.add_row("Project", str(project_root))
                    st.add_row("Godot", cfg.godot_path)
                    auth = f"API key ({cfg.api_key[:8]}...)" if cfg.api_key else "OAuth" if cfg.oauth_token else "None"
                    st.add_row("Auth", auth)
                    console.print(Panel(st, title="Status", border_style="blue"))
                    continue

                if user_input.strip().startswith("/cd "):
                    new_path = Path(user_input.strip()[4:]).expanduser().resolve()
                    if not new_path.exists():
                        console.print(f"[red]  Path not found: {new_path}[/]")
                        continue
                    await engine.close()
                    engine = _rebuild_engine(new_path)
                    if (new_path / "project.godot").exists():
                        from godot_agent.godot.project import parse_project_godot
                        proj = parse_project_godot(new_path / "project.godot")
                        console.print(f"[green]  Switched to: {proj.name}[/] [dim]({new_path})[/]")
                    else:
                        console.print(f"  Working dir: {new_path}")
                        console.print("[yellow]  No project.godot found here.[/]")
                    continue

                # Regular message → send to LLM with spinner
                with console.status("[cyan]Thinking...[/]", spinner="dots"):
                    response = await engine.submit(user_input)

                console.print()
                console.print(Panel(
                    Markdown(response),
                    title="[cyan]agent[/]",
                    border_style="cyan",
                    padding=(1, 2),
                ))
                console.print()
        finally:
            await engine.close()

    asyncio.run(_loop())
    console.print("[dim]Session ended.[/]")


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

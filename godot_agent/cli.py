from __future__ import annotations

import asyncio
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
from godot_agent.tools.godot_cli import RunGodotTool
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.screenshot import ScreenshotTool
from godot_agent.tools.search import GlobTool, GrepTool


def build_registry() -> ToolRegistry:
    """Create a tool registry populated with all available agent tools."""
    registry = ToolRegistry()
    for tool_cls in [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        GrepTool,
        GlobTool,
        RunGodotTool,
        ScreenshotTool,
    ]:
        registry.register(tool_cls())
    return registry


def build_engine(config: AgentConfig, project_root: Path) -> ConversationEngine:
    """Construct a ConversationEngine from agent config and project root."""
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
    )


@click.group()
@click.version_option(version="0.1.0")
def main():
    """God Code -- AI coding assistant for Godot game development."""


@main.command()
@click.argument("prompt")
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--image", "-i", multiple=True, help="Reference image paths")
def ask(prompt: str, project: str, config: str | None, image: tuple[str, ...]):
    """Send a single prompt to the agent."""
    cfg = load_config(Path(config) if config else default_config_path())
    project_root = Path(project).resolve()
    engine = build_engine(cfg, project_root)

    async def _run() -> str:
        if image:
            images_b64 = [encode_image(p) for p in image]
            return await engine.submit_with_images(prompt, images_b64)
        return await engine.submit(prompt)

    result = asyncio.run(_run())
    click.echo(result)


@main.command()
@click.option("--project", "-p", default=".", help="Path to Godot project root")
@click.option("--config", "-c", default=None, help="Path to config file")
def chat(project: str, config: str | None):
    """Start an interactive chat session."""
    cfg = load_config(Path(config) if config else default_config_path())
    project_root = Path(project).resolve()
    engine = build_engine(cfg, project_root)
    session_id = str(uuid.uuid4())[:8]

    click.echo(f"God Code v0.1.0 -- Session {session_id}")
    click.echo(f"Project: {project_root}")
    click.echo("Type 'quit' to exit, 'save' to save session.\n")

    async def _loop() -> None:
        while True:
            try:
                user_input = click.prompt("you", prompt_suffix="> ")
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() == "quit":
                break
            if user_input.strip().lower() == "save":
                path = save_session(cfg.session_dir, session_id, engine.messages)
                click.echo(f"Session saved to {path}")
                continue
            response = await engine.submit(user_input)
            click.echo(f"\nagent> {response}\n")

    asyncio.run(_loop())
    click.echo("Session ended.")


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
    click.echo(f"Project: {proj.name}")
    click.echo(f"Version: {proj.version}")
    click.echo(f"Main Scene: {proj.main_scene}")
    click.echo(f"Resolution: {proj.viewport_width}x{proj.viewport_height}")
    click.echo(f"Autoloads: {len(proj.autoloads)}")
    for name, path in proj.autoloads.items():
        click.echo(f"  {name} -> {path}")


if __name__ == "__main__":
    main()

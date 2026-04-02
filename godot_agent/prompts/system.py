"""System prompt builder with Playbook knowledge injection and build discipline."""

from __future__ import annotations

from pathlib import Path

from godot_agent.godot.project import parse_project_godot
from godot_agent.prompts.build_discipline import BUILD_DISCIPLINE_PROMPT
from godot_agent.prompts.knowledge_selector import format_knowledge_injection, select_sections


def build_system_prompt(
    project_root: Path,
    user_hint: str = "",
    file_paths: list[str] | None = None,
    godot_path: str = "godot",
) -> str:
    sections = [_core_identity()]

    # Inject relevant Playbook knowledge based on context
    knowledge_sections = select_sections(user_hint, file_paths, max_sections=4)
    if knowledge_sections:
        sections.append(format_knowledge_injection(knowledge_sections))

    # Build discipline (always included)
    sections.append(BUILD_DISCIPLINE_PROMPT)

    # Project context
    project_file = project_root / "project.godot"
    if project_file.exists():
        proj = parse_project_godot(project_file)
        sections.append(_project_context(proj, project_root, godot_path))
    else:
        sections.append("## Project Context\n\nNo project.godot found in working directory.")

    sections.append(_available_tools())
    return "\n\n".join(sections)


def _core_identity() -> str:
    return """# God Code — Godot Game Development Agent

You are an expert coding agent specialized for Godot 4.4 game development. You understand GDScript, .tscn scene files, .tres resources, shaders, and the Godot engine architecture deeply.

You have tools to read/write files, search code, run GUT tests, take screenshots, modify scene trees, and execute shell commands. Use them to complete the user's request.

## Core Principles

1. **Composition over inheritance** — split features into small scenes, nest and combine them
2. **Signal up, call down** — children emit signals, parents call children's methods
3. **Data-driven design** — use Resource scripts and @export, not hardcoded values
4. **Static typing** — annotate all variables, parameters, and return types
5. **_physics_process for movement** — NEVER use _process for physics/collision logic"""


def _project_context(proj, project_root: Path | None = None, godot_path: str = "godot") -> str:
    lines = ["## Project Context", ""]
    if project_root:
        lines.append(f"- **Project Root**: `{project_root}`")
        lines.append(f"  Use this absolute path for ALL tool calls (read_file, glob, grep, etc.)")
    lines.append(f"- **Godot Path**: `{godot_path}`")
    lines.append(f"  Use this path for run_godot tool's godot_path parameter.")
    lines.append(f"- **Project**: {proj.name}")
    if proj.version:
        lines.append(f"- **Version**: {proj.version}")
    if proj.main_scene:
        lines.append(f"- **Main Scene**: {proj.main_scene}")
    lines.append(f"- **Resolution**: {proj.viewport_width}x{proj.viewport_height}")
    if proj.renderer:
        lines.append(f"- **Renderer**: {proj.renderer}")
    if proj.autoloads:
        lines.append("\n### Autoloads")
        for name, path in proj.autoloads.items():
            lines.append(f"- `{name}` → `{path}`")
    return "\n".join(lines)


def _available_tools() -> str:
    return """## Available Tools

- **read_file** — Read file contents (.gd, .tscn, .tres, .json, .gdshader)
- **write_file** — Create or overwrite a file
- **edit_file** — Replace a specific string in a file
- **list_dir** — List directory contents with optional recursion
- **grep** — Search for regex patterns across files
- **glob** — Find files by glob pattern
- **run_shell** — Execute shell commands
- **run_godot** — Run GUT tests or validate scene loading (headless)
- **screenshot_scene** — Capture a scene as PNG screenshot
- **git** — Git operations (status, diff, commit, branch)

After EVERY file creation/modification, run `run_godot validate` to check for errors."""

from __future__ import annotations

from pathlib import Path

from godot_agent.godot.project import parse_project_godot


def build_system_prompt(project_root: Path) -> str:
    """Build the system prompt for the Godot coding agent.

    Combines core identity, Godot structural rules, project-specific context
    parsed from project.godot, and the available tool catalog into a single
    prompt string.
    """
    sections = [_core_identity(), _godot_rules()]

    project_file = project_root / "project.godot"
    if project_file.exists():
        proj = parse_project_godot(project_file)
        sections.append(_project_context(proj))
    else:
        sections.append(
            "## Project Context\n\nNo project.godot found in working directory."
        )

    sections.append(_available_tools())
    return "\n\n".join(sections)


def _core_identity() -> str:
    return (
        "# Godot Agent\n\n"
        "You are a coding agent specialized for Godot game development. "
        "You understand GDScript, .tscn scene files, .tres resources, shaders, "
        "and the Godot engine architecture.\n\n"
        "You have tools to read/write files, search code, run GUT tests, "
        "take screenshots of scenes, and modify scene trees. "
        "Use them to complete the user's request."
    )


def _godot_rules() -> str:
    return (
        "## Godot Structure Rules\n\n"
        "1. **Visual properties in .tscn, logic in .gd** -- position, size, "
        "color, font, texture belong in .tscn. State changes, event handling, "
        "calculations belong in .gd.\n"
        "2. **Never build UI node trees in _ready()** -- use the scene_writer "
        "tool to modify .tscn files instead.\n"
        "3. **Single .gd > 200 lines** -- consider extracting sub-scenes or "
        "utility classes.\n"
        "4. **Scene > 30 nodes** -- consider breaking into sub-scenes.\n"
        "5. **Always read before edit** -- never modify files without reading "
        "them first.\n"
        "6. **Use res:// paths** -- all Godot resource references use res:// "
        "prefix.\n"
        "7. **Screenshot iteration** -- after visual changes, take a screenshot "
        "to verify the result matches intent."
    )


def _project_context(proj) -> str:
    lines = ["## Project Context", ""]
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
            lines.append(f"- `{name}` -> `{path}`")
    return "\n".join(lines)


def _available_tools() -> str:
    return (
        "## Available Tools\n\n"
        "- **read_file** -- Read file contents (.gd, .tscn, .tres, .json, .gdshader)\n"
        "- **write_file** -- Create or overwrite a file\n"
        "- **edit_file** -- Replace a specific string in a file\n"
        "- **grep** -- Search for patterns across files\n"
        "- **glob** -- Find files by glob pattern\n"
        "- **run_godot** -- Run GUT tests or validate scene loading\n"
        "- **screenshot_scene** -- Capture a scene as PNG screenshot\n"
        "- **git** -- Git operations (status, diff, commit, branch)"
    )

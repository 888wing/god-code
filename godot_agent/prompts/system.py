"""Compatibility wrapper around the prompt assembler."""

from __future__ import annotations

from pathlib import Path

from godot_agent.prompts.assembler import PromptAssembler, PromptContext


def build_system_prompt(
    project_root: Path,
    user_hint: str = "",
    file_paths: list[str] | None = None,
    godot_path: str = "godot",
    language: str = "en",
    verbosity: str = "normal",
    mode: str = "apply",
    extra_prompt: str = "",
) -> str:
    assembler = PromptAssembler(
        PromptContext(
            project_root=project_root,
            godot_path=godot_path,
            language=language,
            verbosity=verbosity,
            mode=mode,
            extra_prompt=extra_prompt,
        )
    )
    return assembler.build(
        user_hint=user_hint,
        file_paths=file_paths,
        active_tools=[
            "read_file",
            "write_file",
            "edit_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "add_scene_node",
            "write_scene_property",
            "add_scene_connection",
            "remove_scene_node",
            "list_dir",
            "grep",
            "glob",
            "run_shell",
            "run_godot",
            "validate_project",
            "check_consistency",
            "project_dependency_graph",
            "screenshot_scene",
            "generate_sprite",
            "web_search",
            "git",
        ],
    )

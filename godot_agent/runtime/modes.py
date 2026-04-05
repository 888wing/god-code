from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InteractionMode = Literal["apply", "plan", "explain", "review", "fix"]

_VALID_MODES = {"apply", "plan", "explain", "review", "fix"}


@dataclass(frozen=True)
class ModeSpec:
    name: InteractionMode
    label: str
    description: str
    prompt: str
    allowed_tools: set[str]


MODE_SPECS: dict[InteractionMode, ModeSpec] = {
    "apply": ModeSpec(
        name="apply",
        label="Apply",
        description="Make changes, validate them, and summarize the result.",
        prompt=(
            "## Interaction Mode\n\n"
            "You are in APPLY mode. Prefer direct execution: inspect the project, make the needed changes, "
            "run validation, and report the outcome succinctly."
        ),
        allowed_tools={
            "read_file", "write_file", "edit_file", "list_dir", "grep", "glob",
            "git", "run_shell", "run_godot", "screenshot_scene",
            "read_script", "edit_script", "lint_script",
            "read_scene", "scene_tree", "add_scene_node", "write_scene_property",
            "add_scene_connection", "remove_scene_node",
            "validate_project", "check_consistency", "project_dependency_graph", "analyze_impact",
            "plan_ui_layout", "validate_ui_layout", "scaffold_audio", "validate_audio_nodes",
            "read_design_memory", "update_design_memory",
            "get_runtime_snapshot", "run_playtest", "run_scripted_playtest", "list_scenarios", "list_contracts",
            "load_scene", "set_fixture", "press_action", "advance_ticks",
            "get_runtime_state", "get_events_since", "capture_viewport",
            "compare_baseline", "report_failure",
            "slice_sprite_sheet", "validate_sprite_imports",
            "generate_sprite", "web_search",
        },
    ),
    "plan": ModeSpec(
        name="plan",
        label="Plan",
        description="Inspect and propose a concrete implementation plan without editing files.",
        prompt=(
            "## Interaction Mode\n\n"
            "You are in PLAN mode. Inspect the project and produce a concrete implementation plan. "
            "Do not modify files or run mutating commands unless the user explicitly overrides this mode."
        ),
        allowed_tools={
            "read_file", "list_dir", "grep", "glob", "run_godot", "screenshot_scene",
            "read_script", "lint_script", "read_scene", "scene_tree",
            "validate_project", "check_consistency", "project_dependency_graph", "analyze_impact",
            "plan_ui_layout", "validate_ui_layout", "scaffold_audio", "validate_audio_nodes",
            "read_design_memory", "get_runtime_snapshot", "run_playtest", "run_scripted_playtest", "list_scenarios", "list_contracts",
            "load_scene", "set_fixture", "press_action", "advance_ticks",
            "get_runtime_state", "get_events_since", "capture_viewport",
            "compare_baseline", "report_failure", "validate_sprite_imports",
        },
    ),
    "explain": ModeSpec(
        name="explain",
        label="Explain",
        description="Inspect existing code and explain how it works.",
        prompt=(
            "## Interaction Mode\n\n"
            "You are in EXPLAIN mode. Prioritize understanding and explanation. "
            "Inspect files as needed, but do not modify the project."
        ),
        allowed_tools={
            "read_file", "list_dir", "grep", "glob", "run_godot", "screenshot_scene",
            "read_script", "lint_script", "read_scene", "scene_tree",
            "validate_project", "check_consistency", "project_dependency_graph", "analyze_impact",
            "plan_ui_layout", "validate_ui_layout", "scaffold_audio", "validate_audio_nodes",
            "read_design_memory", "get_runtime_snapshot", "run_playtest", "run_scripted_playtest", "list_scenarios", "list_contracts",
            "load_scene", "set_fixture", "press_action", "advance_ticks",
            "get_runtime_state", "get_events_since", "capture_viewport",
            "compare_baseline", "report_failure", "validate_sprite_imports",
        },
    ),
    "review": ModeSpec(
        name="review",
        label="Review",
        description="Inspect for bugs, regressions, and missing validation before suggesting fixes.",
        prompt=(
            "## Interaction Mode\n\n"
            "You are in REVIEW mode. Focus on findings, risks, and missing tests first. "
            "Do not modify files unless the user asks for a fix after the review."
        ),
        allowed_tools={
            "read_file", "list_dir", "grep", "glob", "run_godot", "screenshot_scene",
            "read_script", "lint_script", "read_scene", "scene_tree",
            "validate_project", "check_consistency", "project_dependency_graph", "analyze_impact",
            "plan_ui_layout", "validate_ui_layout", "scaffold_audio", "validate_audio_nodes",
            "read_design_memory", "get_runtime_snapshot", "run_playtest", "run_scripted_playtest", "list_scenarios", "list_contracts",
            "load_scene", "set_fixture", "press_action", "advance_ticks",
            "get_runtime_state", "get_events_since", "capture_viewport",
            "compare_baseline", "report_failure", "validate_sprite_imports",
        },
    ),
    "fix": ModeSpec(
        name="fix",
        label="Fix Build",
        description="Focus on reproducing, fixing, and validating errors quickly.",
        prompt=(
            "## Interaction Mode\n\n"
            "You are in FIX BUILD mode. Reproduce failures, identify the smallest viable repair, "
            "apply it, and re-run validation until the errors are cleared."
        ),
        allowed_tools={
            "read_file", "write_file", "edit_file", "list_dir", "grep", "glob",
            "git", "run_shell", "run_godot", "screenshot_scene",
            "read_script", "edit_script", "lint_script",
            "read_scene", "scene_tree", "add_scene_node", "write_scene_property",
            "add_scene_connection", "remove_scene_node",
            "validate_project", "check_consistency", "project_dependency_graph", "analyze_impact",
            "plan_ui_layout", "validate_ui_layout", "scaffold_audio", "validate_audio_nodes",
            "read_design_memory", "update_design_memory",
            "get_runtime_snapshot", "run_playtest", "run_scripted_playtest", "list_scenarios", "list_contracts",
            "load_scene", "set_fixture", "press_action", "advance_ticks",
            "get_runtime_state", "get_events_since", "capture_viewport",
            "compare_baseline", "report_failure",
            "slice_sprite_sheet", "validate_sprite_imports",
            "generate_sprite", "web_search",
        },
    ),
}


def normalize_mode(mode: str) -> InteractionMode:
    value = mode.strip().lower()
    if value not in _VALID_MODES:
        raise ValueError(f"Unknown mode: {mode}")
    return value  # type: ignore[return-value]


def get_mode_spec(mode: str) -> ModeSpec:
    return MODE_SPECS[normalize_mode(mode)]


def mode_prompt(mode: str) -> str:
    return get_mode_spec(mode).prompt


def allowed_tools_for_mode(mode: str) -> set[str]:
    return set(get_mode_spec(mode).allowed_tools)


def mode_choices() -> list[str]:
    return sorted(_VALID_MODES)

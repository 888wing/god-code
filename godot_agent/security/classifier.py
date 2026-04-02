"""Risk classifier for tool invocations."""

from __future__ import annotations

import enum
import re
from pathlib import Path
from pydantic import BaseModel

from godot_agent.tools.base import BaseTool


class OperationRisk(enum.Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_READ_ONLY_TOOLS = {
    "read_file",
    "read_script",
    "read_scene",
    "scene_tree",
    "list_dir",
    "grep",
    "glob",
    "lint_script",
    "validate_project",
    "check_consistency",
    "project_dependency_graph",
    "analyze_impact",
    "read_design_memory",
    "get_runtime_snapshot",
    "run_playtest",
    "screenshot_scene",
}

_SCENE_MUTATION_TOOLS = {
    "add_scene_node",
    "write_scene_property",
    "add_scene_connection",
    "remove_scene_node",
}


def classify_operation(tool: BaseTool, input: BaseModel) -> OperationRisk:
    name = tool.name
    path = getattr(input, "path", None) or getattr(input, "project_path", None)

    if name in _READ_ONLY_TOOLS or tool.is_read_only():
        return OperationRisk.SAFE

    if name == "run_godot":
        command = getattr(input, "command", "")
        return OperationRisk.LOW if command in {"validate", "gut"} else OperationRisk.HIGH

    if name == "run_shell":
        command = getattr(input, "command", "")
        if any(pattern in command for pattern in ("rm -rf", "git reset --hard", "git clean -f", "--export")):
            return OperationRisk.CRITICAL
        if any(pattern in command for pattern in ("git push", "curl ", "wget ", "sed -i", "mv ")):
            return OperationRisk.HIGH
        return OperationRisk.MEDIUM

    if name == "git":
        command = getattr(input, "command", "")
        if re.search(r"\b(push|reset|clean)\b", command):
            return OperationRisk.CRITICAL
        if re.search(r"\b(commit|checkout|branch|merge|rebase)\b", command):
            return OperationRisk.HIGH
        return OperationRisk.LOW

    if name in _SCENE_MUTATION_TOOLS:
        return OperationRisk.MEDIUM

    if path:
        suffix = Path(path).suffix
        if str(path).endswith("project.godot"):
            return OperationRisk.HIGH
        if suffix == ".tscn" and name in {"write_file", "edit_file"}:
            return OperationRisk.HIGH
        if suffix in {".gd", ".tscn", ".tres"}:
            return OperationRisk.MEDIUM

    return OperationRisk.LOW

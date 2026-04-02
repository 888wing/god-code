"""Pre/post execution hooks for tool governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from godot_agent.tools.base import BaseTool, ToolResult


@dataclass
class HookResult:
    permission_behavior: str | None = None  # allow / ask / deny
    updated_input: BaseModel | None = None
    blocking_error: str | None = None
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "HookResult") -> None:
        if other.permission_behavior == "deny":
            self.permission_behavior = "deny"
        elif other.permission_behavior == "ask" and self.permission_behavior != "deny":
            self.permission_behavior = "ask"
        elif other.permission_behavior == "allow" and self.permission_behavior is None:
            self.permission_behavior = "allow"
        if other.updated_input is not None:
            self.updated_input = other.updated_input
        if other.blocking_error:
            self.blocking_error = other.blocking_error
        self.notes.extend(other.notes)


class ToolHook:
    async def pre_execute(self, tool: BaseTool, parsed_input: BaseModel, context) -> HookResult | None:
        return None

    async def post_execute(self, tool: BaseTool, parsed_input: BaseModel, result: ToolResult, context) -> ToolResult:
        return result


class RequireReadBeforeWriteHook(ToolHook):
    _MUTATING_WITH_PATH = {
        "edit_file",
        "edit_script",
        "add_scene_node",
        "write_scene_property",
        "add_scene_connection",
        "remove_scene_node",
    }

    async def pre_execute(self, tool: BaseTool, parsed_input: BaseModel, context) -> HookResult | None:
        if tool.name not in self._MUTATING_WITH_PATH:
            return None
        path = getattr(parsed_input, "path", "")
        if not path:
            return None
        target = Path(path).resolve()
        if not target.exists():
            return None
        changeset = getattr(context, "changeset", None)
        read_files = getattr(changeset, "read_files", set()) if changeset is not None else set()
        modified_files = getattr(changeset, "modified_files", set()) if changeset is not None else set()
        if str(target) in read_files or str(target) in modified_files:
            return None
        return HookResult(
            blocking_error=f"Must read {path} before mutating it.",
            permission_behavior="deny",
        )


class BlockRawSceneMutationHook(ToolHook):
    async def pre_execute(self, tool: BaseTool, parsed_input: BaseModel, context) -> HookResult | None:
        if tool.name not in {"write_file", "edit_file"}:
            return None
        path = getattr(parsed_input, "path", "")
        if path.endswith(".tscn"):
            return HookResult(
                blocking_error="Use structured scene tools instead of raw text mutation for .tscn files.",
                permission_behavior="deny",
            )
        return None


class ProtectedPathHook(ToolHook):
    async def pre_execute(self, tool: BaseTool, parsed_input: BaseModel, context) -> HookResult | None:
        path = getattr(parsed_input, "path", None) or getattr(parsed_input, "project_path", None)
        if not path or tool.is_read_only():
            return None
        protected_paths = getattr(context, "protected_paths", None)
        reason = protected_paths.reason_for(path) if protected_paths is not None else None
        if reason is None:
            return None
        if tool.name in {"write_file", "edit_file", "run_shell"}:
            return HookResult(
                blocking_error=f"{path} is a protected {reason}. Use a dedicated workflow or explicit approval.",
                permission_behavior="ask",
            )
        return HookResult(permission_behavior="ask", notes=[f"Protected path: {reason}"])


class HookManager:
    def __init__(self, hooks: Iterable[ToolHook] | None = None):
        self._hooks = list(hooks or [])

    def add_hook(self, hook: ToolHook) -> None:
        self._hooks.append(hook)

    async def run_pre_hooks(self, tool: BaseTool, parsed_input: BaseModel, context) -> HookResult:
        aggregate = HookResult()
        current_input = parsed_input
        for hook in self._hooks:
            result = await hook.pre_execute(tool, current_input, context)
            if result is None:
                continue
            aggregate.merge(result)
            if result.updated_input is not None:
                current_input = result.updated_input
            if aggregate.blocking_error:
                break
        if current_input is not parsed_input and aggregate.updated_input is None:
            aggregate.updated_input = current_input
        return aggregate

    async def run_post_hooks(self, tool: BaseTool, parsed_input: BaseModel, result: ToolResult, context) -> ToolResult:
        current = result
        for hook in self._hooks:
            current = await hook.post_execute(tool, parsed_input, current, context)
        return current


def default_hooks() -> HookManager:
    return HookManager(
        hooks=[
            RequireReadBeforeWriteHook(),
            BlockRawSceneMutationHook(),
            ProtectedPathHook(),
        ]
    )

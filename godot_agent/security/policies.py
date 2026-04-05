"""Permission resolution for tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from godot_agent.security.classifier import OperationRisk
from godot_agent.security.protected_paths import ProtectedPathSet, discover_protected_paths
from godot_agent.tools.base import BaseTool


EventCallback = Callable[[str, str, dict[str, Any]], None]


@dataclass
class ToolExecutionContext:
    mode: str = "apply"
    project_root: Path | None = None
    allowed_tools: set[str] | None = None
    changeset: Any = None
    protected_paths: ProtectedPathSet = field(default_factory=ProtectedPathSet)
    emit_event: EventCallback | None = None
    llm_client: Any = None  # LLMClient instance for tools that need API access

    def refresh_protected_paths(self) -> None:
        self.protected_paths = discover_protected_paths(self.project_root)


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str = ""
    requires_approval: bool = False


def _emit(context: ToolExecutionContext, kind: str, message: str, **data: Any) -> None:
    if context.emit_event:
        context.emit_event(kind, message, data)


class PermissionPolicyFramework:
    def evaluate(
        self,
        *,
        tool: BaseTool,
        parsed_input: BaseModel,
        context: ToolExecutionContext,
        risk: OperationRisk,
        hook_result,
    ) -> PermissionDecision:
        if context.allowed_tools is not None and tool.name not in context.allowed_tools:
            return PermissionDecision(False, f"Tool '{tool.name}' is not allowed in {context.mode} mode.")

        if hook_result.permission_behavior == "deny":
            return PermissionDecision(False, hook_result.blocking_error or f"Blocked by hook for {tool.name}.")

        path = getattr(parsed_input, "path", None) or getattr(parsed_input, "project_path", None)
        protected_reason = context.protected_paths.reason_for(path) if path else None

        if context.mode in {"plan", "review", "explain"} and not tool.is_read_only():
            return PermissionDecision(False, f"{tool.name} is not allowed in {context.mode} mode.")

        if hook_result.permission_behavior == "ask":
            return PermissionDecision(
                False,
                hook_result.blocking_error or f"{tool.name} requires explicit approval in this context.",
                requires_approval=True,
            )

        if risk == OperationRisk.CRITICAL:
            return PermissionDecision(False, f"{tool.name} was classified as CRITICAL risk.")

        if protected_reason and tool.name in {"write_file", "edit_file", "run_shell", "git"}:
            return PermissionDecision(
                False,
                f"{path} is a protected {protected_reason}; raw mutation commands are blocked.",
            )

        if protected_reason and context.mode not in {"apply", "fix"}:
            return PermissionDecision(False, f"{path} is protected and cannot be modified in {context.mode} mode.")

        if risk == OperationRisk.HIGH and context.mode not in {"apply", "fix"}:
            return PermissionDecision(False, f"{tool.name} is too risky for {context.mode} mode.")

        _emit(context, "policy_allowed", f"Allowed tool {tool.name}", tool_name=tool.name, risk=risk.value)
        return PermissionDecision(True)

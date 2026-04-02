"""Governed execution pipeline for tool invocations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from godot_agent.security.classifier import classify_operation
from godot_agent.security.hooks import HookManager, default_hooks
from godot_agent.security.policies import PermissionPolicyFramework, ToolExecutionContext
from godot_agent.tools.base import BaseTool, ToolResult


@dataclass
class ToolExecutionPipeline:
    hooks: HookManager
    policies: PermissionPolicyFramework

    @classmethod
    def create_default(cls) -> "ToolExecutionPipeline":
        return cls(hooks=default_hooks(), policies=PermissionPolicyFramework())

    async def execute(self, tool: BaseTool, arguments: dict, context: ToolExecutionContext) -> ToolResult:
        try:
            parsed_input = tool.Input.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(error=f"Input validation failed: {exc}")

        validation_error = tool.validate_input(parsed_input)
        if validation_error:
            return ToolResult(error=validation_error)

        risk = classify_operation(tool, parsed_input)
        hook_result = await self.hooks.run_pre_hooks(tool, parsed_input, context)
        if hook_result.blocking_error and hook_result.permission_behavior == "deny":
            return ToolResult(error=hook_result.blocking_error, metadata={"risk": risk.value, "hook_notes": hook_result.notes})

        final_input = hook_result.updated_input or parsed_input
        decision = self.policies.evaluate(
            tool=tool,
            parsed_input=final_input,
            context=context,
            risk=risk,
            hook_result=hook_result,
        )
        if not decision.allowed:
            return ToolResult(
                error=decision.reason,
                metadata={
                    "risk": risk.value,
                    "requires_approval": decision.requires_approval,
                    "hook_notes": hook_result.notes,
                },
            )

        try:
            result = await tool.execute(final_input)
        except Exception as exc:
            return ToolResult(error=str(exc), metadata={"risk": risk.value})

        if result.metadata is None:
            result.metadata = {}
        result.metadata.setdefault("risk", risk.value)
        if hook_result.notes:
            result.metadata.setdefault("hook_notes", hook_result.notes)
        result = await self.hooks.run_post_hooks(tool, final_input, result, context)
        _update_context_after_success(tool, final_input, result, context)
        return result


def _update_context_after_success(tool: BaseTool, parsed_input, result: ToolResult, context: ToolExecutionContext) -> None:
    if result.error:
        return
    path = getattr(parsed_input, "path", None)
    changeset = getattr(context, "changeset", None)
    if not path or changeset is None:
        return
    resolved = str(Path(path).resolve())
    if tool.is_read_only():
        if hasattr(changeset, "read_files"):
            changeset.read_files.add(resolved)
    else:
        if hasattr(changeset, "read_files"):
            changeset.read_files.add(resolved)
        if hasattr(changeset, "modified_files"):
            changeset.modified_files.add(resolved)

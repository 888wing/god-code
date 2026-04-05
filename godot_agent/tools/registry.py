from __future__ import annotations

from pathlib import Path

from godot_agent.security.policies import ToolExecutionContext
from godot_agent.security.tool_pipeline import ToolExecutionPipeline
from godot_agent.tools.base import BaseTool, ToolResult


class ToolRegistry:
    def __init__(
        self,
        *,
        pipeline: ToolExecutionPipeline | None = None,
        execution_context: ToolExecutionContext | None = None,
    ):
        self._tools: dict[str, BaseTool] = {}
        self.pipeline = pipeline or ToolExecutionPipeline.create_default()
        self.execution_context = execution_context or ToolExecutionContext()

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def configure_execution_context(
        self,
        *,
        mode: str | None = None,
        project_root: str | Path | None = None,
        allowed_tools: set[str] | None = None,
        changeset=None,
        emit_event=None,
        llm_client=None,
    ) -> None:
        if mode is not None:
            self.execution_context.mode = mode
        if project_root is not None:
            self.execution_context.project_root = Path(project_root).resolve()
            self.execution_context.refresh_protected_paths()
        if allowed_tools is not None:
            self.execution_context.allowed_tools = set(allowed_tools)
        if changeset is not None:
            self.execution_context.changeset = changeset
        if emit_event is not None:
            self.execution_context.emit_event = emit_event
        if llm_client is not None:
            self.execution_context.llm_client = llm_client

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_openai_tools(self, enabled_names: set[str] | None = None, strict: bool = False) -> list[dict]:
        tools = self._tools.values()
        if enabled_names is not None:
            tools = [tool for tool in tools if tool.name in enabled_names]
        return [tool.to_openai_schema(strict=strict) for tool in tools]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(error=f"Unknown tool: {name}")
        return await self.pipeline.execute(tool, arguments, self.execution_context)

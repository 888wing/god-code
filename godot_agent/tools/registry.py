from __future__ import annotations
from godot_agent.tools.base import BaseTool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_openai_tools(self) -> list[dict]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(error=f"Unknown tool: {name}")
        try:
            parsed_input = tool.Input.model_validate(arguments)
            return await tool.execute(parsed_input)
        except Exception as e:
            return ToolResult(error=str(e))

import pytest
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.registry import ToolRegistry
from pydantic import BaseModel, Field


class MockInput(BaseModel):
    message: str = Field(description="A test message")


class MockOutput(BaseModel):
    reply: str


class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool for testing"
    Input = MockInput
    Output = MockOutput

    async def execute(self, input: MockInput) -> ToolResult:
        return ToolResult(output=MockOutput(reply=f"echo: {input.message}"))


class TestToolRegistry:
    def test_register_and_lookup(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        tool = registry.get("mock_tool")
        assert tool is not None
        assert tool.name == "mock_tool"

    def test_lookup_missing_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_generate_schemas(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        schemas = registry.to_openai_tools()
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert "message" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        result = await registry.execute("mock_tool", {"message": "hello"})
        assert result.output.reply == "echo: hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("unknown", {})
        assert result.error is not None

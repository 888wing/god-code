from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    name: str
    description: str
    Input: type[BaseModel]
    Output: type[BaseModel]

    @abstractmethod
    async def execute(self, input: BaseModel) -> ToolResult:
        ...

    def is_read_only(self) -> bool:
        """Fail-closed default: assume tool may modify state."""
        return False

    def is_destructive(self) -> bool:
        """Fail-closed default: assume tool can be destructive."""
        return True

    def is_concurrency_safe(self) -> bool:
        """Fail-closed default: assume tool is not concurrency safe."""
        return False

    def validate_input(self, input: BaseModel) -> str | None:
        """Optional business-level validation after schema parsing."""
        return None

    def to_openai_schema(self, strict: bool = False) -> dict:
        schema: dict = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.Input.model_json_schema(),
            },
        }
        if strict:
            schema["function"]["strict"] = True
            # Structured outputs requires additionalProperties: false
            params = schema["function"]["parameters"]
            if "additionalProperties" not in params:
                params["additionalProperties"] = False
        return schema

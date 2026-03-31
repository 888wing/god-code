from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    output: Any = None
    error: str | None = None


class BaseTool(ABC):
    name: str
    description: str
    Input: type[BaseModel]
    Output: type[BaseModel]

    @abstractmethod
    async def execute(self, input: BaseModel) -> ToolResult:
        ...

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.Input.model_json_schema(),
            },
        }

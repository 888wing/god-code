from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from godot_agent.runtime.providers import canonical_model_name


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def cost_estimate(self, model: str = "") -> float:
        inp_rate, out_rate = _pricing_for_model(model)
        return (self.prompt_tokens * inp_rate + self.completion_tokens * out_rate) / 1_000_000


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Message:
    role: str
    content: Any = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def user_with_images(cls, text: str, images_b64: list[str]) -> Message:
        content = [{"type": "text", "text": text}]
        for img in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img}"},
            })
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str | None = None, tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        tool_calls = None
        raw_tool_calls = data.get("tool_calls") or []
        if raw_tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=tc.get("function", {}).get("arguments", ""),
                )
                for tc in raw_tool_calls
            ]
        return cls(
            role=data.get("role", "user"),
            content=data.get("content"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            data["content"] = self.content
        if self.tool_calls:
            data["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        return data


@dataclass
class ChatResponse:
    message: Message
    usage: TokenUsage


@dataclass
class ComputerUseCall:
    call_id: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    pending_safety_checks: list[dict[str, Any]] = field(default_factory=list)
    status: str = ""


@dataclass
class ComputerUseResponse:
    response_id: str
    output_text: str = ""
    computer_calls: list[ComputerUseCall] = field(default_factory=list)
    output_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    provider: str = "openai"
    model: str = "gpt-5.4"
    reasoning_effort: str = "high"
    oauth_token: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    computer_use: bool = False
    computer_use_environment: str = "browser"
    computer_use_display_width: int = 1024
    computer_use_display_height: int = 768
    backend_url: str = ""
    backend_api_key: str = ""
    backend_provider_keys: dict[str, str] = field(default_factory=dict)


def _pricing_for_model(model: str) -> tuple[float, float]:
    canonical = canonical_model_name(model)

    exact = {
        "gpt-5.4": (2.50, 15.00),
        "gpt-5.4-mini": (0.75, 4.50),
        "gpt-5.4-nano": (0.20, 1.25),
        "claude-opus-4.6": (5.00, 25.00),
        "claude-sonnet-4.6": (3.00, 15.00),
        "claude-haiku-4.5": (1.00, 5.00),
        "gemini-3.1-pro": (2.00, 12.00),
        "gemini-3-flash": (0.50, 3.00),
        "gemini-3.1-flash-lite": (0.25, 1.50),
        "grok-4.20-reasoning": (2.00, 6.00),
        "grok-4.20-non-reasoning": (2.00, 6.00),
        "grok-4-1-fast-reasoning": (0.20, 0.50),
        "glm-5": (0.90, 2.80),
        "glm-4.7-flash": (0.10, 0.30),
        "glm-4.5": (0.10, 0.30),
        "minimax-m2.7": (0.15, 0.60),
        "minimax-m2.5": (0.15, 0.60),
        "abab 6.5s": (0.15, 0.60),
    }
    if canonical in exact:
        return exact[canonical]

    if canonical.startswith("gpt-5.4-mini"):
        return (0.75, 4.50)
    if canonical.startswith("gpt-5.4-nano"):
        return (0.20, 1.25)
    if canonical.startswith("gpt-5.4"):
        return (2.50, 15.00)
    if canonical.startswith("claude-opus-4.6"):
        return (5.00, 25.00)
    if canonical.startswith("claude-sonnet-4.6"):
        return (3.00, 15.00)
    if canonical.startswith("claude-haiku-4.5"):
        return (1.00, 5.00)
    if canonical.startswith("gemini-3.1-pro"):
        return (2.00, 12.00)
    if canonical.startswith("gemini-3-flash"):
        return (0.50, 3.00)
    if canonical.startswith("gemini-3.1-flash-lite"):
        return (0.25, 1.50)
    if canonical.startswith("grok-4"):
        return (2.00, 6.00)
    if canonical.startswith("glm-5"):
        return (0.90, 2.80)
    if canonical.startswith("glm-4.7-flash") or canonical.startswith("glm-4.5"):
        return (0.10, 0.30)
    if canonical.startswith("minimax") or canonical.startswith("abab"):
        return (0.15, 0.60)
    if canonical.startswith("gpt-4o"):
        return (2.50, 10.00)
    if canonical.startswith("gpt-4o-mini"):
        return (0.15, 0.60)
    return (2.50, 10.00)

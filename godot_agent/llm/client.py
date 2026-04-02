from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any
import httpx

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


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

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4"
    oauth_token: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._http = httpx.AsyncClient(timeout=120.0)

    def _build_headers(self) -> dict[str, str]:
        token = self.config.oauth_token or self.config.api_key
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _build_request_body(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> dict:
        # gpt-5+ models use max_completion_tokens instead of max_tokens
        model = self.config.model
        token_key = "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
        body: dict[str, Any] = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            token_key: self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            body["tools"] = tools
        return body

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        import asyncio as _asyncio
        body = self._build_request_body(messages, tools)
        url = f"{self.config.base_url}/chat/completions"
        headers = self._build_headers()

        for attempt in range(5):
            resp = await self._http.post(url, headers=headers, json=body)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 2, 30)
                log.warning("Rate limited, retrying in %ds (attempt %d/5)", wait, attempt + 1)
                await _asyncio.sleep(wait)
                continue
            if resp.status_code == 400:
                error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_body.get("error", {}).get("message", resp.text[:200])
                if "content filtering" in error_msg.lower() or "content_filter" in error_msg.lower():
                    if attempt < 4:
                        log.warning("Content filter triggered, retrying (attempt %d/5): %s", attempt + 1, error_msg[:100])
                        await _asyncio.sleep(1)
                        continue
                    # Final attempt — return a safe fallback message
                    return Message.assistant(content=f"[Response blocked by API content filter. Try rephrasing your request or using a different model provider.]")
                resp.raise_for_status()
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]
        tool_calls = None
        if "tool_calls" in choice and choice["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in choice["tool_calls"]
            ]
        return Message.assistant(content=choice.get("content"), tool_calls=tool_calls)

    async def close(self):
        await self._http.aclose()

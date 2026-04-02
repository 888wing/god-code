"""Streaming chat completions with tool call assembly."""

from __future__ import annotations

import json
from typing import Callable

from godot_agent.llm.client import ChatResponse, LLMClient, Message, ToolCall, TokenUsage


async def stream_chat_with_callback(
    client: LLMClient,
    messages: list[Message],
    tools: list[dict] | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> ChatResponse:
    """Stream a chat completion, calling on_chunk for each text delta.

    Returns the complete ChatResponse with assembled tool calls and usage.
    """
    body = client._build_request_body(messages, tools)
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}

    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
    usage = TokenUsage()

    async with client._http.stream(
        "POST",
        client._build_url(),
        headers=client._build_headers(),
        json=body,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break

            chunk = json.loads(data_str)

            # Usage info (comes in final chunk)
            if "usage" in chunk and chunk["usage"]:
                u = chunk["usage"]
                usage = TokenUsage(
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    total_tokens=u.get("total_tokens", 0),
                )

            if not chunk.get("choices"):
                continue
            delta = chunk["choices"][0].get("delta", {})

            # Text content
            if "content" in delta and delta["content"]:
                text = delta["content"]
                content_parts.append(text)
                if on_chunk:
                    on_chunk(text)

            # Tool calls (streamed incrementally)
            if "tool_calls" in delta:
                for tc_delta in delta["tool_calls"]:
                    idx = tc_delta["index"]
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc_delta.get("id", ""),
                            "name": tc_delta.get("function", {}).get("name", ""),
                            "arguments": "",
                        }
                    if "id" in tc_delta and tc_delta["id"]:
                        tool_calls_acc[idx]["id"] = tc_delta["id"]
                    func = tc_delta.get("function", {})
                    if "name" in func and func["name"]:
                        tool_calls_acc[idx]["name"] = func["name"]
                    if "arguments" in func:
                        tool_calls_acc[idx]["arguments"] += func["arguments"]

    # Assemble final message
    content = "".join(content_parts) if content_parts else None
    tool_calls = None
    if tool_calls_acc:
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
            for tc in sorted(tool_calls_acc.values(), key=lambda x: x["id"])
        ]

    msg = Message.assistant(content=content, tool_calls=tool_calls)
    return ChatResponse(message=msg, usage=usage)

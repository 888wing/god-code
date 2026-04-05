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
    route_metadata: dict | None = None,
) -> ChatResponse:
    """Stream a chat completion, calling on_chunk for each text delta.

    Returns the complete ChatResponse with assembled tool calls and usage.
    When backend is configured and route_metadata provided, streams via backend.
    """
    if client._use_backend and route_metadata:
        return await _stream_via_backend(client, messages, tools, on_chunk, route_metadata)
    return await _stream_direct(client, messages, tools, on_chunk)


async def _stream_direct(
    client: LLMClient,
    messages: list[Message],
    tools: list[dict] | None,
    on_chunk: Callable[[str], None] | None,
) -> ChatResponse:
    """Stream directly from provider API."""
    body = client._build_request_body(messages, tools)
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}

    return await _consume_sse_stream(
        client, client._build_url(), client._build_headers(), body, on_chunk
    )


async def _stream_via_backend(
    client: LLMClient,
    messages: list[Message],
    tools: list[dict] | None,
    on_chunk: Callable[[str], None] | None,
    route_metadata: dict,
) -> ChatResponse:
    """Stream via backend orchestration API."""
    body: dict = {
        "messages": [m.to_dict() for m in messages],
        "metadata": route_metadata,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    if client.config.backend_provider_keys:
        body["provider_keys"] = client.config.backend_provider_keys

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if client.config.backend_api_key:
        headers["Authorization"] = f"Bearer {client.config.backend_api_key}"

    url = f"{client._backend_url}/v1/orchestrate"
    return await _consume_sse_stream(client, url, headers, body, on_chunk)


async def _consume_sse_stream(
    client: LLMClient,
    url: str,
    headers: dict[str, str],
    body: dict,
    on_chunk: Callable[[str], None] | None,
) -> ChatResponse:
    """Consume an SSE stream and assemble the final ChatResponse."""
    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
    usage = TokenUsage()

    async with client._http.stream("POST", url, headers=headers, json=body) as resp:
        if resp.status_code >= 400:
            # Read error body before raise_for_status for useful error messages
            error_text = ""
            async for chunk in resp.aiter_bytes():
                error_text += chunk.decode("utf-8", errors="replace")
                if len(error_text) > 500:
                    break
            import logging
            log = logging.getLogger(__name__)
            log.error("Stream request failed %d: %s", resp.status_code, error_text[:300])
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

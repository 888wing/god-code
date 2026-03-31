from __future__ import annotations
import json
from typing import AsyncIterator
from godot_agent.llm.client import LLMClient, Message


async def stream_chat(
    client: LLMClient,
    messages: list[Message],
    tools: list[dict] | None = None,
) -> AsyncIterator[dict]:
    body = client._build_request_body(messages, tools)
    body["stream"] = True
    async with client._http.stream(
        "POST",
        f"{client.config.base_url}/chat/completions",
        headers=client._build_headers(),
        json=body,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                yield json.loads(data)

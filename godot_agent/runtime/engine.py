"""Conversation engine with tool calling loop and context management."""

from __future__ import annotations

import json
import logging

from godot_agent.llm.client import LLMClient, Message
from godot_agent.runtime.context_manager import compact_messages, estimate_tokens
from godot_agent.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

# Compact when message history exceeds this token estimate
_COMPACT_THRESHOLD = 80000


class ConversationEngine:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        system_prompt: str,
        max_tool_rounds: int = 20,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[Message] = [Message.system(system_prompt)]

    async def _maybe_compact(self) -> None:
        """Compact conversation history if it's getting too large."""
        total = sum(estimate_tokens(str(m.content or "")) for m in self.messages)
        if total > _COMPACT_THRESHOLD:
            log.info("Compacting conversation: ~%d tokens", total)
            self.messages = compact_messages(self.messages, keep_recent=8)

    async def _run_loop(self, tools: list[dict] | None) -> str:
        for _ in range(self.max_tool_rounds + 1):
            await self._maybe_compact()
            response = await self.client.chat(self.messages, tools)
            self.messages.append(response)

            if not response.tool_calls:
                return response.content or ""

            for tc in response.tool_calls:
                try:
                    args = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = await self.registry.execute(tc.name, args)
                if result.error:
                    content = json.dumps({"error": result.error})
                else:
                    content = json.dumps(result.output.model_dump() if result.output else {})
                self.messages.append(Message.tool_result(tool_call_id=tc.id, content=content))

        return "Tool call limit reached. Please simplify the request."

    async def submit(self, user_input: str) -> str:
        self.messages.append(Message.user(user_input))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools)

    async def submit_with_images(self, text: str, images_b64: list[str]) -> str:
        self.messages.append(Message.user_with_images(text, images_b64))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.close()

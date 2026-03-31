from __future__ import annotations

import json

from godot_agent.llm.client import LLMClient, Message
from godot_agent.tools.registry import ToolRegistry


class ConversationEngine:
    """Agentic conversation loop with automatic tool-call resolution.

    Maintains a growing message history (system + user + assistant + tool results)
    and iterates until the LLM produces a plain text response or the tool-call
    round limit is reached.
    """

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

    async def _run_loop(self, tools: list[dict] | None) -> str:
        """Execute the chat-then-resolve-tools loop until a text reply or limit."""
        for _ in range(self.max_tool_rounds + 1):
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
                    content = json.dumps(
                        result.output.model_dump() if result.output else {}
                    )

                self.messages.append(
                    Message.tool_result(tool_call_id=tc.id, content=content)
                )

        return "Tool call limit reached. Please simplify the request."

    async def submit(self, user_input: str) -> str:
        """Send a text message and return the final assistant reply."""
        self.messages.append(Message.user(user_input))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools)

    async def submit_with_images(self, text: str, images_b64: list[str]) -> str:
        """Send a message with base64-encoded images and return the final reply."""
        self.messages.append(Message.user_with_images(text, images_b64))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools)

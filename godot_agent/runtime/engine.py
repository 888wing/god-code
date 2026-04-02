"""Conversation engine with tool calling loop, context management, and error detection."""

from __future__ import annotations

import json
import logging

from godot_agent.llm.client import LLMClient, Message
from godot_agent.runtime.context_manager import compact_messages, estimate_tokens
from godot_agent.runtime.error_loop import format_validation_for_llm, validate_project
from godot_agent.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

_COMPACT_THRESHOLD = 80000

# Tools that modify files — trigger Godot validation after execution
_FILE_MUTATING_TOOLS = {"write_file", "edit_file"}


class ConversationEngine:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        system_prompt: str,
        max_tool_rounds: int = 20,
        project_path: str | None = None,
        godot_path: str = "godot",
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[Message] = [Message.system(system_prompt)]
        self.project_path = project_path
        self.godot_path = godot_path

    async def _maybe_compact(self) -> None:
        total = sum(estimate_tokens(str(m.content or "")) for m in self.messages)
        if total > _COMPACT_THRESHOLD:
            log.info("Compacting conversation: ~%d tokens", total)
            self.messages = compact_messages(self.messages, keep_recent=8)

    async def _post_tool_validate(self, tool_names: set[str]) -> str | None:
        """Run Godot validation after file-mutating tools. Returns error report or None."""
        if not self.project_path:
            return None
        if not tool_names & _FILE_MUTATING_TOOLS:
            return None
        try:
            result = await validate_project(self.project_path, self.godot_path, timeout=15)
            if not result.success:
                report = format_validation_for_llm(result)
                log.warning("Post-tool validation found errors:\n%s", report)
                return report
        except Exception as e:
            log.debug("Validation skipped: %s", e)
        return None

    async def _run_loop(self, tools: list[dict] | None) -> str:
        for _ in range(self.max_tool_rounds + 1):
            await self._maybe_compact()
            response = await self.client.chat(self.messages, tools)
            self.messages.append(response)

            if not response.tool_calls:
                return response.content or ""

            tool_names_used: set[str] = set()
            for tc in response.tool_calls:
                try:
                    args = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_names_used.add(tc.name)
                result = await self.registry.execute(tc.name, args)
                if result.error:
                    content = json.dumps({"error": result.error})
                else:
                    content = json.dumps(result.output.model_dump() if result.output else {})
                self.messages.append(Message.tool_result(tool_call_id=tc.id, content=content))

            # Auto-validate after file mutations
            validation_report = await self._post_tool_validate(tool_names_used)
            if validation_report:
                self.messages.append(Message.user(
                    f"[SYSTEM] Godot validation after your changes:\n{validation_report}\n"
                    f"Fix the errors before proceeding."
                ))

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
        await self.client.close()

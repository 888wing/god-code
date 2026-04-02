"""Conversation engine with tool calling loop, context management, and error detection."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from godot_agent.llm.client import ChatResponse, LLMClient, Message, TokenUsage
from godot_agent.runtime.context_manager import compact_messages, estimate_tokens
from godot_agent.runtime.error_loop import format_validation_for_llm, validate_project
from godot_agent.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

_COMPACT_THRESHOLD = 80000
_FILE_MUTATING_TOOLS = {"write_file", "edit_file"}


@dataclass
class TurnStats:
    usage: TokenUsage = field(default_factory=TokenUsage)
    api_calls: int = 0
    tools_called: list[str] = field(default_factory=list)


# Callback types
ToolStartCallback = Callable[[str, dict], None]  # (tool_name, args) -> None
ToolEndCallback = Callable[[str, bool, str], None]  # (tool_name, success, summary) -> None
DiffCallback = Callable[[str, str, str], None]  # (old_text, new_text, filename) -> None


class ConversationEngine:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        system_prompt: str,
        max_tool_rounds: int = 20,
        project_path: str | None = None,
        godot_path: str = "godot",
        auto_validate: bool = True,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[Message] = [Message.system(system_prompt)]
        self.project_path = project_path
        self.godot_path = godot_path
        self.auto_validate = auto_validate
        self.session_usage = TokenUsage()
        self.session_api_calls = 0
        self.last_turn: TurnStats | None = None

        self.auto_commit = False
        self.use_streaming = False

        # TUI callbacks
        self.on_tool_start: ToolStartCallback | None = None
        self.on_tool_end: ToolEndCallback | None = None
        self.on_diff: DiffCallback | None = None
        self.on_stream_chunk: Callable[[str], None] | None = None
        self.on_commit_suggest: Callable[[], None] | None = None

    def scan_project(self) -> str | None:
        """Auto-scan project for context. Returns summary or None."""
        if not self.project_path:
            return None
        root = Path(self.project_path)
        parts: list[str] = []

        # Read CLAUDE.md if exists
        for name in ["CLAUDE.md", "README.md"]:
            f = root / name
            if f.exists():
                text = f.read_text(errors="replace")[:2000]
                parts.append(f"--- {name} ---\n{text}")
                break

        # List project structure
        files: list[str] = []
        for ext in ["*.gd", "*.tscn", "*.tres", "*.json"]:
            files.extend(str(p.relative_to(root)) for p in root.rglob(ext) if ".godot" not in str(p))
        if files:
            parts.append(f"--- Project files ({len(files)}) ---\n" + "\n".join(sorted(files)[:50]))

        if parts:
            context = "\n\n".join(parts)
            self.messages.append(Message.user(
                f"[SYSTEM] Project scan results (auto-loaded):\n{context}"
            ))
            return f"Scanned {len(files)} files"
        return None

    async def _maybe_compact(self) -> None:
        total = sum(estimate_tokens(str(m.content or "")) for m in self.messages)
        if total > _COMPACT_THRESHOLD:
            log.info("Compacting conversation: ~%d tokens", total)
            self.messages = compact_messages(self.messages, keep_recent=8)

    async def _post_tool_validate(self, tool_names: set[str]) -> str | None:
        if not self.project_path or not self.auto_validate:
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

    def _summarize_args(self, name: str, args: dict) -> str:
        """Create a short summary of tool arguments for display."""
        if name in ("read_file", "write_file", "edit_file"):
            path = args.get("path", "")
            return path.split("/")[-1] if "/" in path else path
        if name == "grep":
            return f'"{args.get("pattern", "")}"'
        if name == "glob":
            return args.get("pattern", "")
        if name == "run_godot":
            return args.get("command", "")
        if name == "git":
            return args.get("command", "")[:30]
        if name == "run_shell":
            return args.get("command", "")[:40]
        return ""

    async def _run_loop(self, tools: list[dict] | None, use_streaming: bool = False) -> str:
        turn = TurnStats()

        for _ in range(self.max_tool_rounds + 1):
            await self._maybe_compact()

            # Use streaming for the final text response (no tool calls expected after tools done)
            if use_streaming and self.on_stream_chunk:
                from godot_agent.llm.streaming import stream_chat_with_callback
                chat_resp = await stream_chat_with_callback(
                    self.client, self.messages, tools,
                    on_chunk=self.on_stream_chunk,
                )
            else:
                chat_resp = await self.client.chat(self.messages, tools)
            response = chat_resp.message

            turn.usage = turn.usage + chat_resp.usage
            turn.api_calls += 1
            self.session_usage = self.session_usage + chat_resp.usage
            self.session_api_calls += 1

            self.messages.append(response)

            if not response.tool_calls:
                self.last_turn = turn
                return response.content or ""

            tool_names_used: set[str] = set()
            for tc in response.tool_calls:
                try:
                    args = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_names_used.add(tc.name)
                turn.tools_called.append(tc.name)
                summary = self._summarize_args(tc.name, args)

                # Callback: tool start
                if self.on_tool_start:
                    self.on_tool_start(tc.name, args)

                # For edit_file, capture old text for diff
                old_text = None
                if tc.name == "edit_file" and self.on_diff:
                    path = args.get("path", "")
                    try:
                        old_text = Path(path).read_text(errors="replace")
                    except Exception:
                        old_text = None

                result = await self.registry.execute(tc.name, args)

                # Callback: tool end
                if self.on_tool_end:
                    self.on_tool_end(tc.name, result.error is None, result.error or "")

                # Callback: diff for edit_file
                if tc.name == "edit_file" and old_text is not None and result.error is None and self.on_diff:
                    try:
                        new_text = Path(args.get("path", "")).read_text(errors="replace")
                        filename = args.get("path", "").split("/")[-1]
                        self.on_diff(old_text, new_text, filename)
                    except Exception:
                        pass

                if result.error:
                    content = json.dumps({"error": result.error})
                else:
                    content = json.dumps(result.output.model_dump() if result.output else {})
                self.messages.append(Message.tool_result(tool_call_id=tc.id, content=content))

            validation_report = await self._post_tool_validate(tool_names_used)
            if validation_report:
                self.messages.append(Message.user(
                    f"[SYSTEM] Godot validation after your changes:\n{validation_report}\n"
                    f"Fix the errors before proceeding."
                ))

            # Auto-commit suggestion after successful file mutations
            if self.auto_commit and (tool_names_used & _FILE_MUTATING_TOOLS) and not validation_report:
                if self.on_commit_suggest:
                    self.on_commit_suggest()

        self.last_turn = turn
        return "Tool call limit reached. Please simplify the request."

    async def submit(self, user_input: str) -> str:
        self.messages.append(Message.user(user_input))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools, use_streaming=self.use_streaming)

    async def submit_with_images(self, text: str, images_b64: list[str]) -> str:
        self.messages.append(Message.user_with_images(text, images_b64))
        tools = self.registry.to_openai_tools() or None
        return await self._run_loop(tools)

    async def close(self) -> None:
        await self.client.close()

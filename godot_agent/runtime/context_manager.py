"""Context window management for multi-file Godot projects.

Prevents context overflow by:
- Summarizing old conversation turns
- Selecting which files to include based on relevance
- Tracking token usage estimates
"""

from __future__ import annotations

from dataclasses import dataclass, field

from godot_agent.llm.client import Message


@dataclass
class ContextBudget:
    max_tokens: int = 128000
    system_prompt_tokens: int = 0
    message_tokens: int = 0
    reserved_for_response: int = 4096

    @property
    def available(self) -> int:
        return self.max_tokens - self.system_prompt_tokens - self.message_tokens - self.reserved_for_response

    @property
    def usage_ratio(self) -> float:
        used = self.system_prompt_tokens + self.message_tokens
        return used / self.max_tokens if self.max_tokens > 0 else 0.0

    @property
    def should_compact(self) -> bool:
        return self.usage_ratio > 0.7


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    return len(text) // 3  # Conservative estimate


def compact_messages(
    messages: list[Message],
    keep_recent: int = 6,
    keep_system: bool = True,
) -> list[Message]:
    """Compact conversation history by summarizing old turns.

    Keeps:
    - System message (always)
    - Last N messages (recent context)
    - Summarizes everything in between
    """
    if len(messages) <= keep_recent + 1:
        return messages  # Nothing to compact

    result: list[Message] = []

    # Keep system message
    if keep_system and messages and messages[0].role == "system":
        result.append(messages[0])
        rest = messages[1:]
    else:
        rest = messages

    if len(rest) <= keep_recent:
        return result + rest

    # Summarize old messages
    old = rest[:-keep_recent]
    recent = rest[-keep_recent:]

    summary_parts: list[str] = []
    for msg in old:
        if msg.role == "user":
            content = msg.content if isinstance(msg.content, str) else "[image+text message]"
            summary_parts.append(f"User asked: {content[:100]}...")
        elif msg.role == "assistant":
            if msg.tool_calls:
                tools = ", ".join(tc.name for tc in msg.tool_calls)
                summary_parts.append(f"Agent used tools: {tools}")
            elif msg.content:
                summary_parts.append(f"Agent replied: {msg.content[:100]}...")
        elif msg.role == "tool":
            summary_parts.append(f"Tool returned result")

    summary = "[Conversation history summary]\n" + "\n".join(summary_parts)
    result.append(Message.user(summary))
    result.extend(recent)

    return result


def select_relevant_files(
    all_files: list[str],
    user_prompt: str,
    max_files: int = 10,
) -> list[str]:
    """Select the most relevant files to include in context.

    Prioritizes:
    1. Files mentioned in the prompt
    2. Recently modified files
    3. Core files (project.godot, autoloads, main scene)
    """
    prompt_lower = user_prompt.lower()
    scored: list[tuple[float, str]] = []

    for f in all_files:
        score = 0.0
        fname = f.lower()

        # Direct mention in prompt
        basename = fname.split("/")[-1].replace(".gd", "").replace(".tscn", "")
        if basename in prompt_lower:
            score += 10.0

        # Core files always relevant
        if "project.godot" in fname:
            score += 5.0
        if "autoload" in fname or "manager" in fname:
            score += 3.0
        if "main" in fname or "game" in fname:
            score += 2.0

        # File type relevance
        if fname.endswith(".gd"):
            score += 1.0
        if fname.endswith(".tscn"):
            score += 0.5

        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:max_files]]

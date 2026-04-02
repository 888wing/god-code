"""Smart context window management for long Godot development sessions.

Implements tiered compression that preserves critical context while staying
within the model's token limit:

1. System prompt — NEVER compressed
2. Working memory — extracted key facts from old conversations
3. Recent turns — kept intact (last N messages)
4. Old turns — compressed into summaries

The key insight: in a coding agent, the most important context is
"what files did I read/modify and what decisions did I make", not
the full conversation history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from godot_agent.llm.client import Message

# Token estimation: ~3.5 chars per token (conservative for mixed en/zh content)
_CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Rough token estimate for mixed English/CJK text."""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def estimate_message_tokens(msg: Message) -> int:
    """Estimate tokens for a single message including role overhead."""
    content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
    base = estimate_tokens(content) + 4  # role + formatting overhead
    if msg.tool_calls:
        for tc in msg.tool_calls:
            base += estimate_tokens(tc.name) + estimate_tokens(tc.arguments) + 10
    return base


@dataclass
class ContextBudget:
    max_tokens: int = 1050000  # gpt-5.4: 1.05M context
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
        return self.usage_ratio > 0.75


@dataclass
class WorkingMemory:
    """Extracted key facts from compressed conversation turns."""
    files_read: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)

    def to_message(self) -> str:
        parts = ["[CONTEXT] Working memory from previous conversation:"]
        if self.files_modified:
            parts.append(f"Files modified: {', '.join(set(self.files_modified[-20:]))}")
        if self.files_read:
            parts.append(f"Files read: {', '.join(set(self.files_read[-20:]))}")
        if self.decisions:
            parts.append("Key decisions:\n" + "\n".join(f"  - {d}" for d in self.decisions[-10:]))
        if self.errors_encountered:
            parts.append("Errors fixed:\n" + "\n".join(f"  - {e}" for e in self.errors_encountered[-5:]))
        return "\n".join(parts)


def _extract_working_memory(messages: list[Message]) -> WorkingMemory:
    """Extract key facts from messages for working memory."""
    memory = WorkingMemory()

    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content or "")

        # Extract file paths from tool calls
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = tc.arguments
                # Extract "path" from JSON arguments
                path_match = re.search(r'"path"\s*:\s*"([^"]+)"', args_str)
                if path_match:
                    path = path_match.group(1)
                    short = path.split("/")[-1] if "/" in path else path
                    if tc.name in ("write_file", "edit_file"):
                        memory.files_modified.append(short)
                    elif tc.name == "read_file":
                        memory.files_read.append(short)

        # Extract error mentions from tool results
        if msg.role == "tool" and content:
            if '"error"' in content:
                error_match = re.search(r'"error"\s*:\s*"([^"]{1,100})"', content)
                if error_match:
                    memory.errors_encountered.append(error_match.group(1)[:80])

        # Extract decisions from assistant messages
        if msg.role == "assistant" and content:
            # Look for action statements
            for pattern in [
                r"I (?:will|'ll|have) (?:change|modify|update|fix|add|remove|create)\w* (.{10,60})",
                r"(?:Changed|Modified|Updated|Fixed|Added|Removed|Created) (.{10,60})",
            ]:
                for m in re.finditer(pattern, content):
                    memory.decisions.append(m.group(0)[:80])

    return memory


def smart_compact(
    messages: list[Message],
    keep_recent: int = 10,
    target_ratio: float = 0.60,
    max_tokens: int = 1050000  # gpt-5.4: 1.05M context,
) -> list[Message]:
    """Intelligently compact conversation history.

    Strategy:
    1. ALWAYS keep: system message (index 0)
    2. Extract working memory from old messages
    3. Keep recent N messages intact
    4. Replace everything in between with working memory summary

    This preserves:
    - Full system prompt (Godot knowledge, build discipline)
    - What files were modified and why (working memory)
    - Recent conversation context (for continuity)

    While discarding:
    - Old tool results (files can be re-read)
    - Old LLM explanations (decisions captured in memory)
    - Redundant back-and-forth
    """
    total = sum(estimate_message_tokens(m) for m in messages)
    if total < max_tokens * target_ratio:
        return messages  # No compaction needed

    if len(messages) <= keep_recent + 1:
        return messages  # Nothing to compact

    # Split: system | old | recent
    system = messages[0]  # Always a system message
    rest = messages[1:]

    if len(rest) <= keep_recent:
        return messages

    old = rest[:-keep_recent]
    recent = rest[-keep_recent:]

    # Extract working memory from old messages
    memory = _extract_working_memory(old)
    memory_text = memory.to_message()

    # Build compacted message list
    result = [system]

    # Add working memory as a user context message
    if memory_text.strip():
        result.append(Message.user(memory_text))

    # Add brief summary of how many turns were compressed
    turn_count = sum(1 for m in old if m.role == "user")
    result.append(Message.user(
        f"[CONTEXT] {turn_count} previous conversation turns were compressed. "
        f"Working memory above contains the key facts. "
        f"If you need file contents, read them again with the read_file tool."
    ))

    # Add recent messages intact
    result.extend(recent)

    return result


# Legacy aliases for backward compatibility
def compact_messages(
    messages: list[Message],
    keep_recent: int = 8,
    keep_system: bool = True,
) -> list[Message]:
    """Legacy compaction function. Delegates to smart_compact."""
    return smart_compact(messages, keep_recent=keep_recent)


def select_relevant_files(
    all_files: list[str],
    user_prompt: str,
    max_files: int = 10,
) -> list[str]:
    """Select the most relevant files to include in context."""
    prompt_lower = user_prompt.lower()
    scored: list[tuple[float, str]] = []

    for f in all_files:
        score = 0.0
        fname = f.lower()
        basename = fname.split("/")[-1].replace(".gd", "").replace(".tscn", "")
        if basename in prompt_lower:
            score += 10.0
        if "project.godot" in fname:
            score += 5.0
        if "autoload" in fname or "manager" in fname:
            score += 3.0
        if "main" in fname or "game" in fname:
            score += 2.0
        if fname.endswith(".gd"):
            score += 1.0
        if fname.endswith(".tscn"):
            score += 0.5
        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:max_files]]

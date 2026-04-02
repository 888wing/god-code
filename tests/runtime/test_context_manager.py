import pytest
from godot_agent.runtime.context_manager import (
    compact_messages, estimate_tokens, select_relevant_files, ContextBudget,
)
from godot_agent.llm.client import Message


class TestEstimateTokens:
    def test_basic(self):
        assert estimate_tokens("hello world") > 0

    def test_longer_text_more_tokens(self):
        assert estimate_tokens("a" * 300) > estimate_tokens("a" * 30)


class TestCompactMessages:
    def test_no_compact_needed(self):
        msgs = [Message.system("sys"), Message.user("hi"), Message.assistant(content="hello")]
        result = compact_messages(msgs, keep_recent=4)
        assert len(result) == 3  # unchanged

    def test_compact_old_messages(self):
        # Use small max_tokens to force compaction even with small messages
        from godot_agent.runtime.context_manager import smart_compact
        msgs = [Message.system("sys")]
        for i in range(20):
            msgs.append(Message.user(f"question {i}"))
            msgs.append(Message.assistant(content=f"answer {i}"))
        # Force compaction with a tiny max_tokens
        result = smart_compact(msgs, keep_recent=4, target_ratio=0.01, max_tokens=100)
        assert len(result) < len(msgs)
        assert result[0].role == "system"
        assert result[-1].content == "answer 19"


class TestSelectRelevantFiles:
    def test_mentioned_files_ranked_first(self):
        files = ["src/player.gd", "src/enemy.gd", "scenes/main.tscn"]
        result = select_relevant_files(files, "fix the player movement")
        assert result[0] == "src/player.gd"

    def test_core_files_ranked_high(self):
        files = ["random.gd", "project.godot", "utils.gd"]
        result = select_relevant_files(files, "check settings")
        assert "project.godot" in result[:2]

    def test_max_files_limit(self):
        files = [f"file_{i}.gd" for i in range(50)]
        result = select_relevant_files(files, "anything", max_files=5)
        assert len(result) == 5


class TestContextBudget:
    def test_usage_ratio(self):
        budget = ContextBudget(max_tokens=100000, system_prompt_tokens=20000, message_tokens=50000)
        assert 0.6 < budget.usage_ratio < 0.8

    def test_should_compact(self):
        budget = ContextBudget(max_tokens=100000, system_prompt_tokens=30000, message_tokens=50000)
        assert budget.should_compact is True

    def test_available(self):
        budget = ContextBudget(max_tokens=100000, system_prompt_tokens=10000, message_tokens=10000)
        assert budget.available > 0

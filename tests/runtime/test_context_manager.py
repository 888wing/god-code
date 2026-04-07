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


from godot_agent.runtime.context_manager import truncate_tool_result, prune_system_reports


def test_truncate_short_result_unchanged():
    text = "short result"
    assert truncate_tool_result(text) == text


def test_truncate_long_result():
    text = "A" * 5000
    result = truncate_tool_result(text, max_chars=2000)
    assert len(result) < 2500
    assert "[...truncated" in result
    assert result.startswith("A" * 100)
    assert result.endswith("A" * 100)


def test_truncate_preserves_json_structure():
    import json
    data = {"output": "x" * 5000, "metadata": {"risk": "low"}}
    text = json.dumps(data)
    result = truncate_tool_result(text, max_chars=2000)
    assert len(result) < 2500


def test_prune_keeps_latest_two_reports():
    from godot_agent.llm.types import Message
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Quality gate: report 1"),
        Message.user("normal user message"),
        Message.user("[SYSTEM] Quality gate: report 2"),
        Message.user("[SYSTEM] Quality gate: report 3"),
        Message.user("another user message"),
    ]
    pruned = prune_system_reports(messages, max_reports=2)
    system_reports = [m for m in pruned if m.content and "[SYSTEM]" in m.content]
    assert len(system_reports) == 2
    assert "report 2" in system_reports[0].content
    assert "report 3" in system_reports[1].content


def test_prune_keeps_all_when_under_limit():
    from godot_agent.llm.types import Message
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Quality gate: report 1"),
    ]
    pruned = prune_system_reports(messages, max_reports=2)
    assert len(pruned) == 2


def test_prune_system_reports_with_prefix_filter_only_prunes_matching():
    """Regression v1.0.1/T1+T4: prefix_filter scopes pruning so only the
    specified report type is affected. Other [SYSTEM] reports pass through
    untouched so quality gate / reviewer reports are not collateral damage
    when we prune planner blocks.
    """
    from godot_agent.llm.types import Message
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Planner pass before implementation:\nplan A"),
        Message.user("[SYSTEM] Quality gate: passed"),
        Message.user("[SYSTEM] Planner pass before implementation:\nplan B"),
        Message.user("[SYSTEM] Reviewer: PASS"),
        Message.user("[SYSTEM] Planner pass before implementation:\nplan C"),
    ]
    pruned = prune_system_reports(
        messages,
        max_reports=1,
        prefix_filter="[SYSTEM] Planner",
    )
    planner_reports = [
        m for m in pruned if isinstance(m.content, str) and m.content.startswith("[SYSTEM] Planner")
    ]
    other_reports = [
        m for m in pruned
        if isinstance(m.content, str)
        and m.content.startswith("[SYSTEM]")
        and not m.content.startswith("[SYSTEM] Planner")
    ]
    # Only the latest planner block remains
    assert len(planner_reports) == 1
    assert "plan C" in planner_reports[0].content
    # All non-planner [SYSTEM] reports are untouched
    assert len(other_reports) == 2


def test_prune_system_reports_prefix_filter_none_matches_all():
    """Backward compat: omitting prefix_filter preserves the original
    behavior of pruning any [SYSTEM]-prefixed message."""
    from godot_agent.llm.types import Message
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Planner: old plan"),
        Message.user("[SYSTEM] Quality gate: old report"),
        Message.user("[SYSTEM] Planner: new plan"),
        Message.user("[SYSTEM] Quality gate: new report"),
    ]
    pruned = prune_system_reports(messages, max_reports=2)  # no prefix_filter
    system_msgs = [m for m in pruned if isinstance(m.content, str) and m.content.startswith("[SYSTEM]")]
    assert len(system_msgs) == 2
    # Original behavior: keep the latest 2 regardless of sub-type
    assert "new plan" in system_msgs[0].content
    assert "new report" in system_msgs[1].content


def test_prune_system_reports_prefix_filter_under_limit_no_op():
    """When matching reports are already within the limit, pruning does
    nothing and returns the original list."""
    from godot_agent.llm.types import Message
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Planner: only plan"),
        Message.user("[SYSTEM] Quality gate: report"),
    ]
    pruned = prune_system_reports(
        messages,
        max_reports=2,
        prefix_filter="[SYSTEM] Planner",
    )
    assert len(pruned) == len(messages)


from godot_agent.runtime.context_manager import compress_step_messages

def test_compress_step_messages():
    from godot_agent.llm.types import Message
    messages = [
        Message.system("sys"),
        Message.user("do something earlier"),
        Message.user("[AUTO] Execute step 1: create boss.gd"),
        Message.assistant(content="I'll create the file", tool_calls=[]),
        Message.user('{"output": "' + 'x' * 3000 + '"}'),
        Message.user("[SYSTEM] Quality gate: passed"),
        Message.user("[AUTO] Execute step 2: modify spawner"),
    ]
    compressed = compress_step_messages(messages, completed_step_index=1, summary="created boss.gd +45 lines")
    assert len(compressed) < len(messages)
    step_summary = [m for m in compressed if "Step 1 done" in (m.content or "")]
    assert len(step_summary) == 1

from __future__ import annotations

from godot_agent.runtime.context_health import ContextHealth


def test_healthy_context():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=2)
    assert not h.should_pause
    assert not h.should_compact


def test_should_pause_on_errors():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=3, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_pause


def test_should_pause_on_low_success():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.2, rounds_since_compact=0)
    assert h.should_pause


def test_should_compact_on_high_usage():
    h = ContextHealth(token_usage_ratio=0.65, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_compact


def test_should_compact_on_many_rounds():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=6)
    assert h.should_compact


def test_should_pause_on_extreme_usage():
    h = ContextHealth(token_usage_ratio=0.92, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_pause

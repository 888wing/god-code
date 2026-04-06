from __future__ import annotations
from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan
from godot_agent.runtime.context_health import ContextHealth


def test_plan_approve_execute_roundtrip():
    """Verify plan creation → approve → step execution → completion."""
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"]),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"]),
    ], risk="low")
    for s in plan.steps:
        s.status = "approved"
    assert len(plan.approved_steps) == 2
    plan.steps[0].mark_done("+45 lines")
    assert plan.done_count == 1
    assert plan.current_step.index == 2


def test_plan_skip_step():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="approved"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="skipped"),
        PlanStep(index=3, action="create", target="C", files=["c.gd"], status="approved"),
    ], risk="low")
    assert plan.total_actionable == 2  # skipped not counted


def test_health_triggers_compact():
    h = ContextHealth(token_usage_ratio=0.65, rounds_since_compact=6)
    assert h.should_compact
    assert not h.should_pause


def test_serialization_full_cycle():
    plan = ExecutionPlan(title="Full", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done", summary="ok"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="approved"),
    ], risk="medium")
    data = plan.to_dict()
    restored = ExecutionPlan.from_dict(data)
    assert restored.done_count == 1
    assert len(restored.approved_steps) == 1


def test_plan_all_done():
    plan = ExecutionPlan(title="All Done", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done", summary="ok"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="done", summary="ok"),
    ], risk="low")
    assert plan.current_step is None
    assert plan.done_count == 2


def test_plan_failed_step():
    plan = ExecutionPlan(title="Fail", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done", summary="ok"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="failed", summary="error"),
    ], risk="medium")
    assert plan.done_count == 1
    assert plan.total_actionable == 2


def test_context_health_all_green():
    h = ContextHealth(token_usage_ratio=0.2, consecutive_errors=0, tool_success_rate=1.0, rounds_since_compact=1)
    assert not h.should_pause
    assert not h.should_compact


def test_truncation_and_pruning_imports():
    """Verify all context protection functions are importable."""
    from godot_agent.runtime.context_manager import (
        truncate_tool_result,
        prune_system_reports,
        compress_step_messages,
    )
    assert callable(truncate_tool_result)
    assert callable(prune_system_reports)
    assert callable(compress_step_messages)


def test_session_changeset_fields():
    """Verify SessionRecord has changeset fields."""
    from godot_agent.runtime.session import SessionRecord
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(SessionRecord)}
    assert "changeset_read" in field_names
    assert "changeset_modified" in field_names
    assert "completed_steps" in field_names
    assert "last_plan" in field_names

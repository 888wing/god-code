from __future__ import annotations
from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan

def test_plan_step_defaults():
    step = PlanStep(index=1, action="create", target="boss state machine", files=["src/boss.gd"])
    assert step.status == "pending"
    assert step.summary == ""

def test_execution_plan_approved_steps():
    plan = ExecutionPlan(title="Add boss", steps=[
        PlanStep(index=1, action="create", target="base class", files=["a.gd"], status="approved"),
        PlanStep(index=2, action="modify", target="spawner", files=["b.gd"], status="skipped"),
        PlanStep(index=3, action="create", target="scene", files=["c.tscn"], status="approved"),
    ], risk="medium")
    assert len(plan.approved_steps) == 2
    assert plan.pending_steps == []

def test_plan_step_mark_done():
    step = PlanStep(index=1, action="create", target="test", files=["a.gd"], status="approved")
    step.mark_done("created a.gd +45 lines")
    assert step.status == "done"
    assert step.summary == "created a.gd +45 lines"

def test_plan_serialization_roundtrip():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="file", files=["a.gd"], status="done", summary="ok"),
    ], risk="low")
    data = plan.to_dict()
    restored = ExecutionPlan.from_dict(data)
    assert restored.title == plan.title
    assert restored.steps[0].status == "done"

def test_plan_progress_display():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="a", files=["a.gd"], status="done"),
        PlanStep(index=2, action="modify", target="b", files=["b.gd"], status="running"),
        PlanStep(index=3, action="create", target="c", files=["c.gd"], status="pending"),
    ], risk="low")
    assert plan.done_count == 1
    assert plan.total_actionable == 3
    assert plan.current_step.index == 2

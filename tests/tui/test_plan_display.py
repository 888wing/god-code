from __future__ import annotations


def test_plan_panel_renders():
    from godot_agent.tui.display import ChatDisplay
    from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan

    d = ChatDisplay()
    plan = ExecutionPlan(title="Test Plan", steps=[
        PlanStep(index=1, action="create", target="file A", files=["a.gd"], status="done", summary="+45 lines"),
        PlanStep(index=2, action="modify", target="file B", files=["b.gd"], status="running"),
        PlanStep(index=3, action="create", target="file C", files=["c.gd"], status="pending"),
    ], risk="medium")
    d.plan_panel(plan)  # Should not crash


def test_plan_status_line():
    from godot_agent.tui.display import ChatDisplay
    from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan

    d = ChatDisplay()
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="running"),
    ], risk="low")
    line = d.plan_status_line(plan)
    assert "2" in line
    assert "B" in line

import pytest
from pathlib import Path
from godot_agent.godot.pattern_advisor import analyze_project


class TestPatternAdvisor:
    def test_detects_pool_need(self, tmp_path):
        gd = tmp_path / "spawner.gd"
        gd.write_text("""extends Node
var s = preload("res://b.tscn")
func f():
    s.instantiate()
    s.instantiate()
    s.instantiate()
func g():
    queue_free()
""")
        advice = analyze_project(tmp_path)
        assert any(a.pattern == "object_pool" for a in advice)

    def test_detects_component_need(self, tmp_path):
        gd = tmp_path / "entity.gd"
        # 150+ lines with health, movement, shooting, ai keywords
        lines = ["extends CharacterBody2D", "var hp = 100", "var velocity = Vector2.ZERO"]
        lines += ["var speed = 200", "func take_damage(n): hp -= n"]
        lines += ["func shoot(): pass", "func chase_target(): pass"]
        lines += [f"func _method_{i}(): pass" for i in range(30)]
        lines += ["# " + "x" * 50 for _ in range(100)]
        gd.write_text("\n".join(lines))
        advice = analyze_project(tmp_path)
        assert any(a.pattern == "component" for a in advice)

    def test_detects_state_machine_need(self, tmp_path):
        gd = tmp_path / "boss.gd"
        gd.write_text("""extends Node
var phase = 0
func f():
    match phase:
        0: pass
        1: pass
        2: pass
    if phase == 0: pass
    if phase == 1: pass
    if phase == 2: pass
""")
        advice = analyze_project(tmp_path)
        assert any(a.pattern == "state_machine" for a in advice)

    def test_no_advice_for_clean_project(self, tmp_path):
        gd = tmp_path / "small.gd"
        gd.write_text("extends Node\nfunc _ready():\n\tpass\n")
        advice = analyze_project(tmp_path)
        assert len(advice) == 0

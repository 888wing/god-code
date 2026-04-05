from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.design_memory import DesignMemory, GameplayIntentProfile
from godot_agent.runtime.gameplay_reviewer import review_gameplay_constraints
from godot_agent.runtime.playtest_harness import PlaytestReport, ScenarioResult
from godot_agent.testing.scenario_runner import make_runtime_snapshot


def test_gameplay_reviewer_flags_missing_runtime_input_evidence(tmp_path):
    report = review_gameplay_constraints(
        project_root=tmp_path,
        changed_files={str(tmp_path / "player.gd")},
        design_memory=DesignMemory(control_rules=["move_left and move_right should always work"]),
        intent_profile=GameplayIntentProfile(),
        impact_report=ImpactAnalysisReport(input_actions=["move_left", "move_right"]),
        runtime_snapshot=None,
        playtest_report=None,
    )

    assert report.verdict == "PARTIAL"
    assert any("input-sensitive" in check.description.lower() for check in report.checks)


def test_gameplay_reviewer_fails_on_runtime_errors(tmp_path):
    report = review_gameplay_constraints(
        project_root=tmp_path,
        changed_files={str(tmp_path / "hud.gd")},
        design_memory=DesignMemory(scene_ownership={"res://hud.tscn": "HUD shell"}),
        intent_profile=GameplayIntentProfile(),
        impact_report=ImpactAnalysisReport(),
        runtime_snapshot=make_runtime_snapshot(node_paths=["Main/Hud"], errors=["Null instance"]),
        playtest_report=PlaytestReport(scenarios=[ScenarioResult(id="hud_feedback", title="HUD Feedback", status="FAIL", observations=["Runtime errors present"])])
    )

    assert report.verdict == "FAIL"


def test_gameplay_reviewer_warns_for_demo_quality_without_visual_evidence(tmp_path):
    report = review_gameplay_constraints(
        project_root=tmp_path,
        changed_files={str(tmp_path / "enemy.gd")},
        design_memory=DesignMemory(quality_target="demo"),
        intent_profile=GameplayIntentProfile(genre="bullet_hell", testing_focus=["wave_timing", "boss_phase_clear"]),
        impact_report=ImpactAnalysisReport(),
        runtime_snapshot=make_runtime_snapshot(event_names=["wave_started"]),
        playtest_report=PlaytestReport(scenarios=[ScenarioResult(id="bullet_hell_wave_progression", title="Wave Progression", status="PASS", observations=["wave timing ok"])]),
    )

    assert report.verdict == "PARTIAL"
    assert any(check.status == "WARN" for check in report.checks)

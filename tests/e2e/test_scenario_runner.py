from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.testing.scenario_runner import make_runtime_snapshot, run_scenario_report


def test_scenario_runner_executes_player_movement_report(tmp_path):
    report = run_scenario_report(
        project_root=tmp_path,
        changed_files={str(tmp_path / "player_controller.gd")},
        runtime_snapshot=make_runtime_snapshot(
            event_names=["player_moved"],
            input_actions=["move_left", "move_right"],
        ),
        impact_report=ImpactAnalysisReport(affected_files=["res://scripts/player_controller.gd"]),
    )

    assert report.verdict == "PASS"

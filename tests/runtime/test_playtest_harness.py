from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.playtest_harness import format_playtest_report, run_playtest_harness
from godot_agent.testing.scenario_runner import make_runtime_snapshot


def test_playtest_harness_passes_matching_runtime_snapshot(tmp_path):
    report = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "player_controller.gd")},
        impact_report=ImpactAnalysisReport(affected_files=["res://scripts/player_controller.gd"]),
        runtime_snapshot=make_runtime_snapshot(
            event_names=["player_moved"],
            input_actions=["move_left", "move_right"],
        ),
    )

    assert report.verdict == "PASS"
    assert "Playtest VERDICT: PASS" in format_playtest_report(report)


def test_playtest_harness_fails_when_runtime_errors_present(tmp_path):
    report = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "hud.gd")},
        runtime_snapshot=make_runtime_snapshot(node_paths=["Main/Hud"], errors=["Null instance"]),
    )

    assert report.verdict == "FAIL"

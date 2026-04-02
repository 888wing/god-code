from godot_agent.godot.impact_analysis import analyze_change_impact, format_impact_report, infer_request_impact


def test_analyze_change_impact_tracks_dependencies_and_validation_focus(tmp_path):
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="ImpactGame"\nrun/main_scene="res://scenes/main.tscn"\n\n[autoload]\nBus="*res://autoload/event_bus.gd"\n'
    )
    (tmp_path / "autoload").mkdir()
    (tmp_path / "autoload" / "event_bus.gd").write_text("extends Node\n")
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://scripts/player.gd" id="1"]\n'
        '[node name="Main" type="Node2D"]\n'
        'script = ExtResource("1")\n'
    )
    (tmp_path / "scripts").mkdir()
    player = tmp_path / "scripts" / "player.gd"
    player.write_text(
        'extends CharacterBody2D\n\nfunc _process(_delta: float) -> void:\n\tif Input.is_action_pressed("move_left"):\n\t\tpass\n'
    )

    report = analyze_change_impact(tmp_path, {str(player)})

    assert "res://scripts/player.gd" in report.requested_files
    assert "res://scenes/main.tscn" in report.affected_scenes
    assert "move_left" in report.input_actions
    assert any("gameplay scripts" in item.lower() for item in report.validation_focus)
    assert "Change Impact Analysis" in format_impact_report(report)


def test_infer_request_impact_matches_task_to_file(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="ImpactGame"\n')
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hud_controller.gd").write_text("extends Node\n")

    report = infer_request_impact(tmp_path, "Fix the hud controller feedback")

    assert any(path.endswith("hud_controller.gd") for path in report.requested_files)

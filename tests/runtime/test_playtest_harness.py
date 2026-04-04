import json
from pathlib import Path

from PIL import Image

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.design_memory import GameplayIntentProfile
from godot_agent.runtime.playtest_harness import format_playtest_report, generate_scenario_specs, run_playtest_harness
from godot_agent.runtime.runtime_bridge import clear_runtime_snapshot
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


def test_playtest_harness_runs_step_based_scenario(tmp_path):
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "tests" / "baselines" / "ui" / "inventory_open.png"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(actual, "PNG")
    Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(baseline, "PNG")

    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "inventory.json").write_text(json.dumps({
        "id": "inventory_ui",
        "title": "Inventory UI",
        "description": "Verify inventory flow and baseline screenshot.",
        "path_contains": ["inventory"],
        "required_scene": "res://ui/inventory.tscn",
        "fixtures": {"inventory": {"selected": "potion"}},
        "steps": [
            {"title": "Load scene", "action": "load_scene", "args": {"scene_path": "res://ui/inventory.tscn"}},
            {
                "title": "Open inventory",
                "action": "advance_ticks",
                "ticks": 2,
                "args": {
                    "state_updates": {"selected_item": "potion"},
                    "events": [{"name": "inventory_opened"}],
                },
                "expect_scene": "res://ui/inventory.tscn",
                "expect_state": {"selected_item": "potion"},
                "expect_events": ["inventory_opened"],
            },
            {
                "title": "Capture inventory",
                "action": "capture_viewport",
                "args": {"actual_path": str(actual)},
                "visual_asserts": [{"baseline_id": "ui/inventory_open"}],
            },
        ],
    }), encoding="utf-8")

    try:
        report = run_playtest_harness(
            project_root=tmp_path,
            changed_files={str(tmp_path / "inventory_panel.gd")},
            directory=scenario_dir,
        )
        assert report.verdict == "PASS"
        assert "Baseline matched for ui/inventory_open." in format_playtest_report(report)
    finally:
        clear_runtime_snapshot()


def test_playtest_harness_writes_failure_bundle_for_visual_mismatch(tmp_path):
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "tests" / "baselines" / "ui" / "inventory_open.png"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(actual, "PNG")
    Image.new("RGBA", (8, 8), (40, 50, 60, 255)).save(baseline, "PNG")

    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "inventory.json").write_text(json.dumps({
        "id": "inventory_ui",
        "title": "Inventory UI",
        "description": "Mismatch case.",
        "path_contains": ["inventory"],
        "steps": [
            {"title": "Capture inventory", "action": "capture_viewport", "args": {"actual_path": str(actual)}, "visual_asserts": [{"baseline_id": "ui/inventory_open"}]},
        ],
    }), encoding="utf-8")

    try:
        report = run_playtest_harness(
            project_root=tmp_path,
            changed_files={str(tmp_path / "inventory_panel.gd")},
            directory=scenario_dir,
        )
        assert report.verdict == "FAIL"
        assert report.scenarios[0].failure_bundle
        assert Path(report.scenarios[0].failure_bundle).exists()
    finally:
        clear_runtime_snapshot()


def test_playtest_harness_can_select_scenarios_from_gameplay_profile(tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "bullet_hell.json").write_text(json.dumps({
        "id": "bullet_hell_wave",
        "title": "Bullet Hell Wave",
        "description": "Profile-driven scenario.",
        "genres": ["bullet_hell"],
        "required_events": ["player_moved"],
        "required_inputs": ["move_left"],
    }), encoding="utf-8")

    report = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "unrelated_file.txt")},
        runtime_snapshot=make_runtime_snapshot(event_names=["player_moved"], input_actions=["move_left"]),
        directory=scenario_dir,
        intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
    )

    assert report.verdict == "PASS"
    assert report.profile_genre == "bullet_hell"


def test_generate_scenario_specs_detects_ui_and_skips_empty_scene(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="PlaytestGen"\n')
    (tmp_path / "hud.tscn").write_text(
        '[gd_scene format=3]\n\n'
        '[node name="Hud" type="CanvasLayer"]\n'
        '[node name="Panel" type="PanelContainer" parent="."]\n'
    )
    (tmp_path / "empty.tscn").write_text(
        '[gd_scene format=3]\n\n'
        '[node name="Empty" type="Node2D"]\n'
    )

    generated = generate_scenario_specs(tmp_path)

    assert any(spec.id == "auto_hud" for spec in generated)
    assert all(spec.id != "auto_empty" for spec in generated)


def test_generated_scenario_requires_authoritative_evidence_for_full_pass(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="GeneratedHarness"\n')
    (tmp_path / "player.tscn").write_text(
        '[gd_scene format=3]\n\n'
        '[node name="Player" type="CharacterBody2D"]\n'
        '[node name="Sprite" type="AnimatedSprite2D" parent="."]\n'
        '[node name="CollisionShape" type="CollisionShape2D" parent="."]\n'
        '[connection signal="body_entered" from="." to="." method="_on_body_entered"]\n'
    )

    synthetic = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "player_controller.gd")},
        runtime_snapshot=make_runtime_snapshot(
            active_scene="res://player.tscn",
            node_paths=["Player", "Player/Sprite", "Player/CollisionShape"],
            event_names=["player_moved", "collision_detected"],
            input_actions=["move_left", "move_right", "jump"],
        ),
    )
    authoritative = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "player_controller.gd")},
        runtime_snapshot=make_runtime_snapshot(
            active_scene="res://player.tscn",
            node_paths=["Player", "Player/Sprite", "Player/CollisionShape"],
            event_names=["player_moved", "collision_detected"],
            input_actions=["move_left", "move_right", "jump"],
            source="live_editor",
            evidence_level="high",
            bridge_connected=True,
        ),
    )

    assert synthetic.verdict == "PARTIAL"
    assert "synthetic-only evidence" in format_playtest_report(synthetic)
    assert authoritative.verdict == "PASS"

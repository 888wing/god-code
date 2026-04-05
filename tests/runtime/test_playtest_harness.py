import json
from pathlib import Path

from PIL import Image

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.design_memory import DesignMemory, GameplayIntentProfile
from godot_agent.runtime.playtest_harness import (
    AuthoritativePlaytestEvidence,
    SCENARIO_DIR,
    _snapshot_from_authoritative_summary,
    format_playtest_report,
    generate_scenario_specs,
    list_contracts,
    list_scenario_specs,
    run_playtest_harness,
    run_scripted_playtest,
)
from godot_agent.runtime.runtime_bridge import clear_runtime_snapshot, runtime_contract_state
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


def test_playtest_harness_selects_demo_quality_scenarios(tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "demo_feedback.json").write_text(json.dumps({
        "id": "demo_feedback",
        "title": "Demo Combat Feedback",
        "description": "Quality-target-driven scenario.",
        "quality_targets": ["demo"],
        "required_events": ["hit_feedback"],
    }), encoding="utf-8")

    report = run_playtest_harness(
        project_root=tmp_path,
        changed_files={str(tmp_path / "enemy.gd")},
        runtime_snapshot=make_runtime_snapshot(event_names=["hit_feedback"], source="live_editor", evidence_level="high"),
        directory=scenario_dir,
        design_memory=DesignMemory(quality_target="demo"),
    )

    assert report.verdict == "PASS"
    assert any(scenario.id == "demo_feedback" for scenario in report.scenarios)


def test_playtest_harness_runs_scripted_route_with_sample_asserts(tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "bullet_hell_route.json").write_text(json.dumps({
        "id": "bullet_hell_route",
        "title": "Bullet Hell Route",
        "description": "Deterministic combat route for bullet-hell validation.",
        "path_contains": ["enemy", "boss"],
        "steps": [
            {
                "title": "Replay combat route",
                "action": "scripted_route",
                "segments": [
                    {
                        "press": ["move_right", "fire"],
                        "ticks": 180,
                        "state_updates": {"enemy_bullets": 7, "lives": 3, "player_bullets": 18},
                        "events": [{"name": "wave_started"}],
                        "capture_as": "sample_a",
                    },
                    {
                        "release": ["move_right"],
                        "press": ["move_left"],
                        "ticks": 180,
                        "state_updates": {"enemy_bullets": 36, "enemies": 3, "lives": 3, "player_bullets": 21},
                        "events": [{"name": "wave_pressure"}],
                        "capture_as": "sample_b",
                    },
                ],
                "sample_asserts": [
                    {
                        "label": "enemy density ramps",
                        "left_sample": "sample_b",
                        "left_key": "enemy_bullets",
                        "op": ">",
                        "right_sample": "sample_a",
                        "right_key": "enemy_bullets",
                    },
                    {
                        "label": "player survives route",
                        "left_sample": "sample_b",
                        "left_key": "lives",
                        "op": ">=",
                        "value": 1,
                    },
                    {
                        "label": "player projectile output persists",
                        "left_sample": "sample_b",
                        "left_key": "player_bullets",
                        "op": ">",
                        "right_sample": "sample_a",
                        "right_key": "player_bullets",
                    },
                ],
            },
        ],
    }), encoding="utf-8")

    try:
        report = run_playtest_harness(
            project_root=tmp_path,
            changed_files={str(tmp_path / "enemy.gd")},
            directory=scenario_dir,
        )
        assert report.verdict == "PASS"
        assert "Captured sample sample_a at tick 180." in format_playtest_report(report)
        assert "Sample assertion passed: enemy density ramps" in format_playtest_report(report)
    finally:
        clear_runtime_snapshot()


def test_playtest_harness_fails_scripted_route_sample_assertions(tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "boss_transition.json").write_text(json.dumps({
        "id": "boss_transition",
        "title": "Boss Transition",
        "description": "Fail when transition cleanup does not reduce bullets.",
        "path_contains": ["boss"],
        "steps": [
            {
                "title": "Replay boss transition",
                "action": "scripted_route",
                "route_segments": [
                    {
                        "press": ["fire"],
                        "ticks": 120,
                        "state_updates": {"enemy_bullets": 14},
                        "events": [{"name": "boss_phase_1"}],
                        "capture_as": "before_clear",
                    },
                    {
                        "ticks": 30,
                        "state_updates": {"enemy_bullets": 12},
                        "events": [{"name": "boss_transition"}],
                        "capture_as": "after_clear",
                    },
                ],
                "sample_asserts": [
                    {
                        "label": "boss transition clears bullets",
                        "left_sample": "after_clear",
                        "left_key": "enemy_bullets",
                        "op": "==",
                        "value": 0,
                    },
                ],
            },
        ],
    }), encoding="utf-8")

    try:
        report = run_playtest_harness(
            project_root=tmp_path,
            changed_files={str(tmp_path / "boss.gd")},
            directory=scenario_dir,
        )
        assert report.verdict == "FAIL"
        assert report.scenarios[0].failure_bundle
        assert Path(report.scenarios[0].failure_bundle).exists()
        assert "Sample assertion failed: boss transition clears bullets" in format_playtest_report(report)
    finally:
        clear_runtime_snapshot()


def test_builtin_bullet_hell_scenarios_use_scripted_route_contracts(tmp_path):
    try:
        report = run_playtest_harness(
            project_root=tmp_path,
            changed_files={str(tmp_path / "boss_enemy_controller.gd")},
            directory=SCENARIO_DIR,
            intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
            design_memory=DesignMemory(quality_target="demo"),
            auto_generate=False,
        )
        scenarios = {scenario.id: scenario for scenario in report.scenarios}

        assert "bullet_hell_wave_progression" in scenarios
        assert "bullet_hell_phase_transition" in scenarios
        assert "demo_boss_transition" in scenarios
        assert scenarios["bullet_hell_wave_progression"].status == "PARTIAL"
        assert any(
            observation.startswith("Captured sample sample_a")
            for observation in scenarios["bullet_hell_wave_progression"].observations
        )
        assert any(
            "Sample assertion passed: transition clears enemy bullets"
            in observation
            for observation in scenarios["bullet_hell_phase_transition"].observations
        )
    finally:
        clear_runtime_snapshot()


def test_builtin_topdown_and_platformer_scenario_packs_are_selectable():
    topdown_specs = list_scenario_specs(
        directory=SCENARIO_DIR,
        intent_profile=GameplayIntentProfile(genre="topdown_shooter", enemy_model="reactive_ai"),
    )
    platformer_contracts = list_contracts(
        directory=SCENARIO_DIR,
        intent_profile=GameplayIntentProfile(genre="platformer_enemy", enemy_model="state_machine"),
    )

    assert any(spec["id"] == "topdown_shooter_pressure" for spec in topdown_specs)
    assert any(contract["id"] == "platformer_enemy_patrol_response" for contract in platformer_contracts)


def test_bullet_hell_profile_does_not_mark_other_genre_packs_relevant():
    specs = list_scenario_specs(
        directory=SCENARIO_DIR,
        intent_profile=GameplayIntentProfile(
            genre="bullet_hell",
            enemy_model="scripted_patterns",
            testing_focus=["wave_timing", "pattern_readability", "boss_phase_clear"],
        ),
        quality_target="demo",
    )
    by_id = {spec["id"]: spec for spec in specs}

    assert by_id["bullet_hell_wave_progression"]["relevant"] is True
    assert by_id["demo_boss_transition"]["relevant"] is True
    assert by_id["platformer_enemy_patrol_response"]["relevant"] is False
    assert by_id["topdown_shooter_pressure"]["relevant"] is False


def test_run_scripted_playtest_can_run_all_built_in_step_scenarios(tmp_path):
    report = run_scripted_playtest(
        project_root=tmp_path,
        changed_files=set(),
        design_memory=DesignMemory(quality_target="demo"),
        intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
        run_all=True,
    )

    assert any(scenario.id == "bullet_hell_wave_progression" for scenario in report.scenarios)
    assert any(scenario.id == "topdown_shooter_pressure" for scenario in report.scenarios)


def test_run_scripted_playtest_prefers_authoritative_headless_evidence(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "boss_transition.json").write_text(json.dumps({
        "id": "boss_transition",
        "title": "Boss Transition",
        "description": "Authoritative runner should satisfy this scenario.",
        "genres": ["bullet_hell"],
        "authoritative_assertions": ["boss_transitions_clear_bullets"],
        "steps": [{"title": "Fallback route", "action": "scripted_route", "route_segments": [{"ticks": 1}]}],
    }), encoding="utf-8")

    evidence = AuthoritativePlaytestEvidence(
        scene_path="res://scenes/playtests/scripted_combat_playtest.tscn",
        summary_path=str(tmp_path / "summary.json"),
        summary={},
        assertions={
            "boss_transitions_clear_bullets": {
                "name": "boss_transitions_clear_bullets",
                "passed": True,
                "details": {"transition_clears": [True, True]},
            }
        },
        snapshot=make_runtime_snapshot(
            active_scene="res://scenes/playtests/scripted_combat_playtest.tscn",
            source="headless",
            evidence_level="high",
        ),
    )
    Path(evidence.summary_path).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "godot_agent.runtime.playtest_harness._run_authoritative_headless_playtest",
        lambda project_root: evidence,
    )

    report = run_scripted_playtest(
        project_root=tmp_path,
        changed_files=set(),
        directory=scenario_dir,
        intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
    )

    assert report.verdict == "PASS"
    assert report.scenarios[0].evidence_source == "headless"
    assert "Authoritative assertion passed: boss_transitions_clear_bullets." in format_playtest_report(report)


def test_authoritative_summary_promotes_visual_evidence_into_snapshot(tmp_path):
    screenshot_path = tmp_path / "boss_phase_banner.png"
    screenshot_path.write_bytes(b"png")
    summary = {
        "wave": {
            "samples": [
                {"enemy_bullets": 6, "player_bullets": 2, "enemies": 9, "lives": 3},
                {"enemy_bullets": 18, "player_bullets": 4, "enemies": 4, "lives": 2},
            ]
        },
        "visual": {
            "screenshots": [
                {
                    "path": str(screenshot_path),
                    "label": "Boss phase banner",
                    "tags": ["phase_banner", "screen_flash"],
                }
            ],
            "observations": [
                "Pattern readability screenshot captured during wave pressure.",
                "Phase banner visible during demo transition.",
                "hit_feedback screen_flash cue recorded during player damage.",
                "enemy_defeated burst and score popup visible.",
            ],
            "cues": {
                "phase_banner_visible": True,
                "screen_flash": True,
                "hit_feedback": True,
                "enemy_defeated": True,
            },
        },
        "assertions": [
            {"name": "wave_enemy_density_ramps", "passed": True},
            {"name": "boss_transitions_clear_bullets", "passed": True},
        ],
    }

    snapshot = _snapshot_from_authoritative_summary(
        scene_path="res://scenes/playtests/scripted_combat_playtest.tscn",
        summary_path=str(tmp_path / "summary.json"),
        summary=summary,
    )

    assert snapshot.screenshot_paths == [str(screenshot_path)]
    contract_state = runtime_contract_state(snapshot)
    assert contract_state["phase_banner_visible"] is True
    assert contract_state["screen_flash"] == 1
    event_names = {event.name for event in snapshot.events}
    assert "hit_feedback" in event_names
    assert "enemy_defeated" in event_names


def test_run_scripted_playtest_fails_when_authoritative_assertion_fails(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenario_specs"
    scenario_dir.mkdir()
    (scenario_dir / "boss_transition.json").write_text(json.dumps({
        "id": "boss_transition",
        "title": "Boss Transition",
        "description": "Authoritative failure should produce a failure bundle.",
        "genres": ["bullet_hell"],
        "authoritative_assertions": ["boss_transitions_clear_bullets"],
        "steps": [{"title": "Fallback route", "action": "scripted_route", "route_segments": [{"ticks": 1}]}],
    }), encoding="utf-8")

    evidence = AuthoritativePlaytestEvidence(
        scene_path="res://scenes/playtests/scripted_combat_playtest.tscn",
        summary_path=str(tmp_path / "summary.json"),
        summary={},
        assertions={
            "boss_transitions_clear_bullets": {
                "name": "boss_transitions_clear_bullets",
                "passed": False,
                "details": {"transition_clears": [False, False]},
            }
        },
        snapshot=make_runtime_snapshot(
            active_scene="res://scenes/playtests/scripted_combat_playtest.tscn",
            source="headless",
            evidence_level="high",
        ),
    )
    Path(evidence.summary_path).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "godot_agent.runtime.playtest_harness._run_authoritative_headless_playtest",
        lambda project_root: evidence,
    )

    report = run_scripted_playtest(
        project_root=tmp_path,
        changed_files=set(),
        directory=scenario_dir,
        intent_profile=GameplayIntentProfile(genre="bullet_hell", enemy_model="scripted_patterns"),
    )

    assert report.verdict == "FAIL"
    assert report.scenarios[0].failure_bundle
    assert Path(report.scenarios[0].failure_bundle).exists()


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

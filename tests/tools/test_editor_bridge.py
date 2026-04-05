import asyncio

from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot, clear_runtime_snapshot, update_runtime_snapshot
from godot_agent.runtime.playtest_harness import AuthoritativePlaytestEvidence
from godot_agent.tools.editor_bridge import (
    GetRuntimeSnapshotTool,
    ListContractsTool,
    ListScenariosTool,
    RunPlaytestTool,
    RunScriptedPlaytestTool,
)
from godot_agent.tools.file_ops import clear_project_root, set_project_root


def test_get_runtime_snapshot_tool_reads_current_snapshot(tmp_path):
    set_project_root(tmp_path)
    update_runtime_snapshot(
        RuntimeSnapshot(
            active_scene="res://scenes/main.tscn",
            nodes=[RuntimeNodeState(path="Main/Hud", type="CanvasLayer")],
            events=[RuntimeEvent(name="player_moved")],
        )
    )
    try:
        tool = GetRuntimeSnapshotTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path))))
        assert "Runtime Snapshot" in result.output.report
        assert result.output.snapshot["active_scene"] == "res://scenes/main.tscn"
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_playtest_tool_uses_runtime_snapshot(tmp_path):
    set_project_root(tmp_path)
    update_runtime_snapshot(
        RuntimeSnapshot(
            nodes=[RuntimeNodeState(path="Main/Player", type="CharacterBody2D")],
            events=[RuntimeEvent(name="player_moved")],
            input_actions=["move_left", "move_right"],
        )
    )
    try:
        tool = RunPlaytestTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(project_path=str(tmp_path), changed_files=[str(tmp_path / "player_controller.gd")])
            )
        )
        assert result.output.verdict == "PASS"
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_list_scenarios_and_contracts_tools_return_profile_matches(tmp_path):
    set_project_root(tmp_path)
    (tmp_path / ".god_code").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".god_code" / "design_memory.json").write_text(
        '{"gameplay_intent":{"genre":"bullet_hell","enemy_model":"scripted_patterns","confirmed":true},"quality_target":"demo"}',
        encoding="utf-8",
    )
    try:
        scenarios_tool = ListScenariosTool()
        scenarios = asyncio.run(scenarios_tool.execute(scenarios_tool.Input(project_path=str(tmp_path))))
        assert any(item["id"] == "bullet_hell_wave_progression" for item in scenarios.output.scenarios)

        contracts_tool = ListContractsTool()
        contracts = asyncio.run(contracts_tool.execute(contracts_tool.Input(project_path=str(tmp_path), scenario_id="bullet_hell_wave_progression")))
        assert contracts.output.contracts[0]["id"] == "bullet_hell_wave_progression"
        assert contracts.output.contracts[0]["steps"][0]["action"] == "scripted_route"
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_scripted_playtest_tool_executes_contracts(tmp_path):
    set_project_root(tmp_path)
    (tmp_path / ".god_code").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".god_code" / "design_memory.json").write_text(
        '{"gameplay_intent":{"genre":"bullet_hell","enemy_model":"scripted_patterns","confirmed":true},"quality_target":"demo"}',
        encoding="utf-8",
    )
    try:
        tool = RunScriptedPlaytestTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    scenario_ids=["bullet_hell_phase_transition"],
                )
            )
        )
        assert result.output.verdict in {"PARTIAL", "PASS"}
        assert any(scenario["id"] == "bullet_hell_phase_transition" for scenario in result.output.scenarios)
        assert result.output.gameplay_review_verdict in {"PARTIAL", "PASS"}
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_scripted_playtest_tool_filters_to_matching_genre_pack(tmp_path):
    set_project_root(tmp_path)
    (tmp_path / ".god_code").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".god_code" / "design_memory.json").write_text(
        (
            '{"gameplay_intent":{"genre":"bullet_hell","enemy_model":"scripted_patterns",'
            '"testing_focus":["wave_timing","boss_phase_clear","pattern_readability"],"confirmed":true},'
            '"quality_target":"demo"}'
        ),
        encoding="utf-8",
    )
    try:
        tool = RunScriptedPlaytestTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path))))
        scenario_ids = {scenario["id"] for scenario in result.output.scenarios}

        assert "bullet_hell_wave_progression" in scenario_ids
        assert "demo_boss_transition" in scenario_ids
        assert "platformer_enemy_patrol_response" not in scenario_ids
        assert "topdown_shooter_pressure" not in scenario_ids
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_scripted_playtest_tool_uses_headless_authoritative_evidence(monkeypatch, tmp_path):
    set_project_root(tmp_path)
    (tmp_path / ".god_code").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".god_code" / "design_memory.json").write_text(
        '{"gameplay_intent":{"genre":"bullet_hell","enemy_model":"scripted_patterns","confirmed":true},"quality_target":"prototype"}',
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("{}", encoding="utf-8")
    evidence = AuthoritativePlaytestEvidence(
        scene_path="res://scenes/playtests/scripted_combat_playtest.tscn",
        summary_path=str(summary_path),
        summary={},
        assertions={
            "boss_phase_1_reached": {
                "name": "boss_phase_1_reached",
                "passed": True,
                "details": {"expected": 1, "actual": 1},
            },
            "boss_phase_2_reached": {
                "name": "boss_phase_2_reached",
                "passed": True,
                "details": {"expected": 2, "actual": 2},
            },
            "boss_transitions_clear_bullets": {
                "name": "boss_transitions_clear_bullets",
                "passed": True,
                "details": {},
            }
        },
        snapshot=RuntimeSnapshot(
            active_scene="res://scenes/playtests/scripted_combat_playtest.tscn",
            source="headless",
            evidence_level="high",
        ),
    )
    monkeypatch.setattr(
        "godot_agent.runtime.playtest_harness._run_authoritative_headless_playtest",
        lambda project_root: evidence,
    )
    try:
        tool = RunScriptedPlaytestTool()
        result = asyncio.run(
            tool.execute(
                tool.Input(
                    project_path=str(tmp_path),
                    scenario_ids=["bullet_hell_phase_transition"],
                )
            )
        )
        assert result.output.verdict == "PASS"
        assert any(scenario["evidence_source"] == "headless" for scenario in result.output.scenarios)
    finally:
        clear_runtime_snapshot()
        clear_project_root()


def test_run_scripted_playtest_tool_promotes_visual_authoritative_evidence_to_gameplay_pass(monkeypatch, tmp_path):
    set_project_root(tmp_path)
    (tmp_path / ".god_code").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".god_code" / "design_memory.json").write_text(
        (
            '{"gameplay_intent":{"genre":"bullet_hell","enemy_model":"scripted_patterns",'
            '"testing_focus":["wave_timing","pattern_readability","boss_phase_clear"],"confirmed":true},'
            '"quality_target":"demo","pillars":["readable danmaku","telegraphed boss phases"],'
            '"control_rules":["focus dodge lane"]}'
        ),
        encoding="utf-8",
    )
    screenshot_path = tmp_path / "boss_phase_banner.png"
    screenshot_path.write_bytes(b"png")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("{}", encoding="utf-8")
    evidence = AuthoritativePlaytestEvidence(
        scene_path="res://scenes/playtests/scripted_combat_playtest.tscn",
        summary_path=str(summary_path),
        summary={
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
                    "Screen flash telegraph captured during demo transition.",
                    "hit_feedback screen_flash cue recorded during player damage.",
                    "enemy_defeated burst and score popup visible.",
                ],
                "cues": {
                    "phase_banner_visible": True,
                    "screen_flash": True,
                    "hit_feedback": True,
                    "enemy_defeated": True,
                },
            }
        },
        assertions={
            "boss_phase_1_reached": {
                "name": "boss_phase_1_reached",
                "passed": True,
                "details": {"expected": 1, "actual": 1},
            },
            "boss_phase_2_reached": {
                "name": "boss_phase_2_reached",
                "passed": True,
                "details": {"expected": 2, "actual": 2},
            },
            "boss_transitions_clear_bullets": {
                "name": "boss_transitions_clear_bullets",
                "passed": True,
                "details": {},
            },
            "wave_enemy_density_ramps": {
                "name": "wave_enemy_density_ramps",
                "passed": True,
                "details": {},
            },
            "wave_player_survives_scripted_route": {
                "name": "wave_player_survives_scripted_route",
                "passed": True,
                "details": {},
            },
            "wave_enemy_presence_visible": {
                "name": "wave_enemy_presence_visible",
                "passed": True,
                "details": {},
            },
        },
        snapshot=RuntimeSnapshot(
            active_scene="res://scenes/playtests/scripted_combat_playtest.tscn",
            source="headless",
            evidence_level="high",
            screenshot_paths=[str(screenshot_path)],
            state={"phase_banner_visible": True, "screen_flash": 1},
            events=[RuntimeEvent(name="hit_feedback"), RuntimeEvent(name="enemy_defeated")],
        ),
    )
    monkeypatch.setattr(
        "godot_agent.runtime.playtest_harness._run_authoritative_headless_playtest",
        lambda project_root: evidence,
    )
    try:
        tool = RunScriptedPlaytestTool()
        result = asyncio.run(tool.execute(tool.Input(project_path=str(tmp_path))))
        assert result.output.verdict == "PASS"
        assert result.output.gameplay_review_verdict == "PASS"
    finally:
        clear_runtime_snapshot()
        clear_project_root()

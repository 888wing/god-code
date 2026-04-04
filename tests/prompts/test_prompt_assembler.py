from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.design_memory import DesignMemory
from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.playtest_harness import PlaytestReport, ScenarioResult
from godot_agent.runtime.quality_gate import QualityCheck, QualityGateReport
from godot_agent.runtime.runtime_bridge import RuntimeEvent, RuntimeNodeState, RuntimeSnapshot
from godot_agent.runtime.reviewer import ReviewCheck, ReviewReport


def test_prompt_assembler_includes_dynamic_context(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="AssemblerGame"\n')

    assembler = PromptAssembler(
        PromptContext(project_root=tmp_path, godot_path="godot", language="en", mode="apply")
    )

    prompt = assembler.build(
        user_hint="Fix the player movement",
        file_paths=["scripts/player.gd", "scenes/main.tscn"],
        active_tools=["read_script", "edit_script", "validate_project"],
        project_scan="--- README.md ---\nsmall project",
    )

    assert "AssemblerGame" in prompt
    assert "Fix the player movement" in prompt
    assert "scripts/player.gd" in prompt
    assert "validate_project" in prompt
    assert "Active Skills" in prompt
    assert "Physics Gameplay" in prompt


def test_prompt_assembler_includes_quality_and_review_reports(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="VerifierGame"\n')
    assembler = PromptAssembler(PromptContext(project_root=tmp_path))

    quality = QualityGateReport(
        changed_files=["scripts/player.gd"],
        checks=[QualityCheck(name="gdscript-lint", command="lint", status="warning", summary="1 warning")],
    )
    review = ReviewReport(
        checks=[ReviewCheck(description="Lint file", command="lint", observed_output="1 warning", status="PARTIAL")]
    )

    prompt = assembler.build(user_hint="Review gameplay script", quality_report=quality, review_report=review)

    assert "Quality gate verdict" in prompt
    assert "Reviewer VERDICT" in prompt


def test_prompt_assembler_includes_design_memory_impact_runtime_and_playtest(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="MemoryGame"\n')
    assembler = PromptAssembler(PromptContext(project_root=tmp_path))

    prompt = assembler.build(
        design_memory=DesignMemory(game_title="MemoryGame", pillars=["Responsive movement"]),
        impact_report=ImpactAnalysisReport(affected_files=["res://scripts/player.gd"], validation_focus=["Re-test movement"]),
        runtime_snapshot=RuntimeSnapshot(
            active_scene="res://scenes/main.tscn",
            nodes=[RuntimeNodeState(path="Main/Player", type="CharacterBody2D")],
            events=[RuntimeEvent(name="player_moved")],
        ),
        playtest_report=PlaytestReport(scenarios=[ScenarioResult(id="player_movement", title="Player Movement", status="PASS", observations=["Scenario expectations satisfied."])]),
    )

    assert "Project Design Memory" in prompt
    assert "Change Impact Analysis" in prompt
    assert "Runtime Snapshot" in prompt
    assert "Playtest VERDICT: PASS" in prompt


def test_prompt_assembler_includes_collision_skill_when_relevant(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="CollisionGame"\n')
    assembler = PromptAssembler(PromptContext(project_root=tmp_path))

    prompt = assembler.build(
        user_hint="fix collision masks for enemy bullets",
        file_paths=["scenes/bullet.tscn"],
    )

    assert "Collision Architecture" in prompt


def test_prompt_assembler_respects_manual_skill_override(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="SkillOverrideGame"\n')
    assembler = PromptAssembler(PromptContext(project_root=tmp_path))

    prompt = assembler.build(
        user_hint="inspect the player scene",
        skill_mode="manual",
        enabled_skills=["collision"],
    )

    assert "Collision Architecture" in prompt

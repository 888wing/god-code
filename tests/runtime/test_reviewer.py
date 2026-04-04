from pathlib import Path

import pytest

from godot_agent.runtime.quality_gate import QualityCheck, QualityGateReport
from godot_agent.runtime.reviewer import format_review_report, review_changes


@pytest.mark.asyncio
async def test_reviewer_passes_clean_change(tmp_path: Path):
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="ReviewGame"\n\n[autoload]\nPlayer="*res://player.gd"\n'
    )
    script = tmp_path / "player.gd"
    script.write_text(
        "extends Node\n\nvar hp: int = 10\n\nfunc _ready() -> void:\n\tpass\n"
    )

    report = await review_changes(
        project_root=tmp_path,
        changed_files={str(script)},
        godot_path="true",
        quality_report=QualityGateReport(changed_files=["player.gd"], checks=[]),
    )

    assert report.verdict == "PASS"
    assert "Reviewer VERDICT: PASS" in format_review_report(report)


@pytest.mark.asyncio
async def test_reviewer_fails_missing_scene_resource(tmp_path: Path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="ReviewGame"\n')
    scene = tmp_path / "main.tscn"
    scene.write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Texture2D" path="res://missing.png" id="1"]\n'
        '[node name="Main" type="Node2D"]\n'
    )

    report = await review_changes(
        project_root=tmp_path,
        changed_files={str(scene)},
        godot_path="true",
        quality_report=QualityGateReport(
            changed_files=["main.tscn"],
            checks=[QualityCheck(name="scene-resources", command="validate_resources", status="error", summary="missing")],
        ),
    )

    assert report.verdict == "FAIL"


@pytest.mark.asyncio
async def test_reviewer_reports_ui_warnings_as_partial(tmp_path: Path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="ReviewGame"\n')
    scene = tmp_path / "menu.tscn"
    scene.write_text(
        '[gd_scene format=3]\n\n'
        '[node name="Menu" type="Control"]\n'
        '[node name="PlayButton" type="Button" parent="."]\n'
        'custom_minimum_size = Vector2(100, 24)\n'
    )

    report = await review_changes(
        project_root=tmp_path,
        changed_files={str(scene)},
        godot_path="true",
        quality_report=QualityGateReport(changed_files=["menu.tscn"], checks=[]),
    )

    assert report.verdict == "PARTIAL"
    assert any("UI layout" in check.description for check in report.checks)

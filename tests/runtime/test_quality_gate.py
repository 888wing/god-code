from pathlib import Path

import pytest

from godot_agent.runtime.quality_gate import format_quality_gate_report, run_quality_gate


@pytest.mark.asyncio
async def test_quality_gate_passes_for_clean_script(tmp_path: Path):
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="GateGame"\n\n[autoload]\nPlayer="*res://player.gd"\n'
    )
    script = tmp_path / "player.gd"
    script.write_text(
        "extends CharacterBody2D\n\nvar speed: float = 100.0\n\nfunc _ready() -> void:\n\tpass\n"
    )

    report = await run_quality_gate(project_root=tmp_path, changed_files={str(script)}, godot_path="true")

    assert report.verdict == "pass"
    assert "player.gd" in format_quality_gate_report(report)


@pytest.mark.asyncio
async def test_quality_gate_fails_for_missing_scene_resource(tmp_path: Path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="GateGame"\n')
    scene = tmp_path / "main.tscn"
    scene.write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Texture2D" path="res://missing.png" id="1"]\n'
        '[node name="Main" type="Node2D"]\n'
    )

    report = await run_quality_gate(project_root=tmp_path, changed_files={str(scene)}, godot_path="true")

    assert report.verdict == "fail"
    assert any(check.name == "scene-resources" for check in report.errors)

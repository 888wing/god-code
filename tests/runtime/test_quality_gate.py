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


@pytest.mark.asyncio
async def test_quality_gate_reports_ui_and_audio_warnings(tmp_path: Path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="GateGame"\n')
    scene = tmp_path / "menu.tscn"
    scene.write_text(
        '[gd_scene format=3]\n\n'
        '[node name="Menu" type="Control"]\n'
        '[node name="PlayButton" type="Button" parent="."]\n'
        'custom_minimum_size = Vector2(100, 24)\n'
        '[node name="ClickAudio" type="AudioStreamPlayer" parent="."]\n'
    )

    report = await run_quality_gate(project_root=tmp_path, changed_files={str(scene)}, godot_path="true")

    assert any(check.name == "ui-layout" for check in report.warnings)
    assert any(check.name == "audio-nodes" for check in report.warnings)


@pytest.mark.asyncio
async def test_quality_gate_accepts_validation_suite():
    """run_quality_gate can accept a pre-run ValidationSuite."""
    from godot_agent.runtime.quality_gate import run_quality_gate
    import inspect
    sig = inspect.signature(run_quality_gate)
    assert "validation_suite" in sig.parameters

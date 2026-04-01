import pytest
from pathlib import Path
from godot_agent.godot.resource_validator import validate_resources

SCENE_WITH_REFS = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://src/player.gd" id="1_script"]
[ext_resource type="Texture2D" path="res://assets/icon.png" id="2_tex"]

[node name="Root" type="Node2D"]
script = ExtResource("1_script")
"""

SCENE_NO_REFS = """[gd_scene load_steps=1 format=3]

[node name="Root" type="Node2D"]
"""


class TestResourceValidator:
    def test_valid_references(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "player.gd").write_text("extends Node2D\n")
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "icon.png").write_bytes(b"PNG")
        (tmp_path / "scene.tscn").write_text(SCENE_WITH_REFS)
        issues = validate_resources(tmp_path / "scene.tscn", project_root=tmp_path)
        assert len(issues) == 0

    def test_missing_reference(self, tmp_path):
        (tmp_path / "scene.tscn").write_text(SCENE_WITH_REFS)
        issues = validate_resources(tmp_path / "scene.tscn", project_root=tmp_path)
        assert len(issues) == 2
        assert any("player.gd" in i for i in issues)

    def test_partial_missing(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "player.gd").write_text("extends Node2D\n")
        (tmp_path / "scene.tscn").write_text(SCENE_WITH_REFS)
        issues = validate_resources(tmp_path / "scene.tscn", project_root=tmp_path)
        assert len(issues) == 1
        assert "icon.png" in issues[0]

    def test_no_ext_resources(self, tmp_path):
        (tmp_path / "scene.tscn").write_text(SCENE_NO_REFS)
        issues = validate_resources(tmp_path / "scene.tscn", project_root=tmp_path)
        assert len(issues) == 0

    def test_issue_message_contains_path(self, tmp_path):
        (tmp_path / "scene.tscn").write_text(SCENE_WITH_REFS)
        issues = validate_resources(tmp_path / "scene.tscn", project_root=tmp_path)
        for issue in issues:
            assert "res://" in issue
            assert "Missing resource" in issue

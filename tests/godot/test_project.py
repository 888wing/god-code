import pytest
from pathlib import Path
from godot_agent.godot.project import parse_project_godot, GodotProject

SAMPLE_PROJECT = """; Engine configuration file.
config_version=5

[application]
config/name="CardForge"
config/version="0.1.0"
run/main_scene="res://scenes/ui/main_menu.tscn"
config/features=PackedStringArray("4.4", "GL Compatibility")

[autoload]
GameManager="*res://src/autoload/game_manager.gd"
AudioManager="*res://src/autoload/audio_manager.gd"
BattleVFX="*res://src/autoload/battle_vfx.gd"

[display]
window/size/viewport_width=1920
window/size/viewport_height=1080
"""


class TestParseProjectGodot:
    def test_parse_name(self, tmp_path):
        (tmp_path / "project.godot").write_text(SAMPLE_PROJECT)
        proj = parse_project_godot(tmp_path / "project.godot")
        assert proj.name == "CardForge"

    def test_parse_version(self, tmp_path):
        (tmp_path / "project.godot").write_text(SAMPLE_PROJECT)
        proj = parse_project_godot(tmp_path / "project.godot")
        assert proj.version == "0.1.0"

    def test_parse_main_scene(self, tmp_path):
        (tmp_path / "project.godot").write_text(SAMPLE_PROJECT)
        proj = parse_project_godot(tmp_path / "project.godot")
        assert proj.main_scene == "res://scenes/ui/main_menu.tscn"

    def test_parse_autoloads(self, tmp_path):
        (tmp_path / "project.godot").write_text(SAMPLE_PROJECT)
        proj = parse_project_godot(tmp_path / "project.godot")
        assert len(proj.autoloads) == 3
        assert proj.autoloads["GameManager"] == "res://src/autoload/game_manager.gd"

    def test_parse_resolution(self, tmp_path):
        (tmp_path / "project.godot").write_text(SAMPLE_PROJECT)
        proj = parse_project_godot(tmp_path / "project.godot")
        assert proj.viewport_width == 1920
        assert proj.viewport_height == 1080

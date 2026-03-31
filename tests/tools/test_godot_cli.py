import pytest
from godot_agent.tools.godot_cli import (
    parse_godot_output,
    GodotOutputReport,
    build_gut_command,
    build_screenshot_script,
)


class TestParseGodotOutput:
    def test_parse_errors(self):
        output = """
Godot Engine v4.4.stable
ERROR: res://src/battle/broken.gd:45 - Invalid operands
WARNING: res://scenes/ui/menu.gd:12 - Unused variable 'x'
Scene loaded successfully
ERROR: res://data/cards.json - Parse error
"""
        report = parse_godot_output(output)
        assert len(report.errors) == 2
        assert len(report.warnings) == 1
        assert report.errors[0].file == "res://src/battle/broken.gd"
        assert report.errors[0].line == 45

    def test_parse_clean_output(self):
        output = "Godot Engine v4.4.stable\nScene loaded successfully\n"
        report = parse_godot_output(output)
        assert len(report.errors) == 0
        assert len(report.warnings) == 0

    def test_parse_error_without_line_number(self):
        output = "ERROR: res://data/cards.json - Parse error\n"
        report = parse_godot_output(output)
        assert len(report.errors) == 1
        assert report.errors[0].file == "res://data/cards.json"
        assert report.errors[0].line is None
        assert report.errors[0].message == "Parse error"

    def test_parse_warning_with_line_number(self):
        output = "WARNING: res://scenes/ui/menu.gd:12 - Unused variable 'x'\n"
        report = parse_godot_output(output)
        assert len(report.warnings) == 1
        assert report.warnings[0].file == "res://scenes/ui/menu.gd"
        assert report.warnings[0].line == 12
        assert report.warnings[0].message == "Unused variable 'x'"

    def test_raw_output_preserved(self):
        output = "Some raw output\n"
        report = parse_godot_output(output)
        assert report.raw_output == output

    def test_empty_output(self):
        report = parse_godot_output("")
        assert len(report.errors) == 0
        assert len(report.warnings) == 0
        assert report.raw_output == ""


class TestBuildGutCommand:
    def test_default_command(self):
        cmd = build_gut_command(godot_path="/usr/bin/godot")
        assert "/usr/bin/godot" in cmd
        assert "--headless" in cmd
        assert any("gut_cmdln.gd" in c for c in cmd)

    def test_specific_test(self):
        cmd = build_gut_command(godot_path="godot", test_script="res://tests/test_battle.gd")
        assert any("test_battle.gd" in c for c in cmd)

    def test_default_godot_path(self):
        cmd = build_gut_command()
        assert cmd[0] == "godot"

    def test_no_test_script_omits_gtest_flag(self):
        cmd = build_gut_command(godot_path="godot")
        assert not any("-gtest=" in c for c in cmd)

    def test_test_script_includes_gtest_flag(self):
        cmd = build_gut_command(godot_path="godot", test_script="res://tests/test_foo.gd")
        gtest_args = [c for c in cmd if c.startswith("-gtest=")]
        assert len(gtest_args) == 1
        assert gtest_args[0] == "-gtest=res://tests/test_foo.gd"

    def test_gexit_flag_present(self):
        cmd = build_gut_command()
        assert "-gexit" in cmd


class TestBuildScreenshotScript:
    def test_generates_valid_gdscript(self):
        script = build_screenshot_script(
            scene_path="res://scenes/battle/battle_scene.tscn",
            output_path="/tmp/screenshot.png",
            delay_ms=500,
        )
        assert "extends SceneTree" in script
        assert "battle_scene.tscn" in script
        assert "screenshot.png" in script

    def test_delay_conversion(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
            delay_ms=2000,
        )
        assert "2.0" in script

    def test_default_delay(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert "1.0" in script

    def test_contains_save_png(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert "save_png" in script

    def test_contains_quit(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert "quit()" in script

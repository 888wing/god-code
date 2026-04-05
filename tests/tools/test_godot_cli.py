import pytest
from godot_agent.tools.godot_cli import (
    build_import_command,
    parse_godot_output,
    GodotOutputReport,
    GodotCommandResult,
    build_gut_command,
    build_screenshot_script,
    resolve_godot_path,
    run_godot_import,
)
from godot_agent.runtime.config import AgentConfig


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

    def test_parse_ansi_wrapped_error(self):
        output = "\x1b[1;31mERROR:\x1b[0;91m res://assets/sprites/player.png - Missing resource\n"
        report = parse_godot_output(output)
        assert len(report.errors) == 1
        assert report.errors[0].file == "res://assets/sprites/player.png"
        assert report.errors[0].message == "Missing resource"

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


class TestBuildImportCommand:
    def test_default_import_command(self):
        cmd = build_import_command()
        assert cmd == ["godot", "--import", "--quit"]

    def test_custom_import_command(self):
        cmd = build_import_command("/Applications/Godot")
        assert cmd == ["/Applications/Godot", "--import", "--quit"]


def test_resolve_godot_path_prefers_configured_path(monkeypatch):
    monkeypatch.setattr(
        "godot_agent.tools.godot_cli.load_config",
        lambda path: AgentConfig(godot_path="/Applications/Godot.app/Contents/MacOS/Godot"),
    )

    assert resolve_godot_path("godot") == "/Applications/Godot.app/Contents/MacOS/Godot"


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

    def test_uses_deferred_capture(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert 'call_deferred("_capture")' in script
        assert "func _capture() -> void:" in script

    def test_waits_for_renderable_frame(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert "await process_frame" in script
        assert "texture = root.get_viewport().get_texture()" in script

    def test_handles_load_failure(self):
        script = build_screenshot_script(
            scene_path="res://missing_scene.tscn",
            output_path="/tmp/out.png",
        )
        assert 'push_error("Failed to load scene: res://missing_scene.tscn")' in script
        assert "quit(1)" in script

    def test_handles_missing_viewport_texture(self):
        script = build_screenshot_script(
            scene_path="res://scenes/test.tscn",
            output_path="/tmp/out.png",
        )
        assert "Viewport texture is unavailable" in script
        assert "quit(2)" in script


@pytest.mark.asyncio
async def test_run_godot_import_uses_import_command(monkeypatch, tmp_path):
    class _DummyProcess:
        returncode = 0

        async def communicate(self):
            return b"import ok\n", b""

    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _DummyProcess()

    monkeypatch.setattr(
        "godot_agent.tools.godot_cli.asyncio.create_subprocess_exec",
        fake_exec,
    )

    result = await run_godot_import(tmp_path, godot_path="/Applications/Godot")

    assert isinstance(result, GodotCommandResult)
    assert result.exit_code == 0
    assert result.stdout.strip() == "import ok"
    assert calls[0][0] == ("/Applications/Godot", "--import", "--quit")
    assert calls[0][1]["cwd"] == str(tmp_path)

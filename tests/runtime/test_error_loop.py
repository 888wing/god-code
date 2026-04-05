from pathlib import Path

import pytest

from godot_agent.runtime.error_loop import (
    GodotError,
    ValidationResult,
    format_validation_for_llm,
    parse_godot_output,
    validate_project,
)


class TestParseGodotOutput:
    def test_parse_error_with_line(self):
        output = "ERROR: res://scripts/player.gd:45 - Invalid operands"
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert errors[0].file == "res://scripts/player.gd"
        assert errors[0].line == 45

    def test_parse_warning(self):
        output = "WARNING: res://scenes/ui.gd:10 - Unused variable"
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert errors[0].level == "WARNING"

    def test_parse_resource_error(self):
        output = 'ERROR: Failed loading resource [Resource file res://bad.tscn:27]'
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert "bad.tscn" in errors[0].file

    def test_clean_output(self):
        output = "Godot Engine v4.4\nScene loaded OK\n"
        errors = parse_godot_output(output)
        assert len(errors) == 0

    def test_parse_script_error(self):
        output = "SCRIPT ERROR: Parse Error: Something broke"
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert errors[0].level == "ERROR"
        assert "Parse Error" in errors[0].message

    def test_parse_quoted_script_path(self):
        output = 'ERROR: Failed to load script "res://scripts/enemy.gd" with error "Parse error".'
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert errors[0].file == "res://scripts/enemy.gd"
        assert "Failed to load script" in errors[0].message

    def test_parse_ansi_wrapped_error(self):
        output = (
            "\x1b[1;31mERROR:\x1b[0;91m res://scenes/bullet.tscn:13 - "
            "Parse Error: [ext_resource] referenced non-existent resource at: "
            "res://assets/sprites/bullet.png.\n"
        )
        errors = parse_godot_output(output)
        assert len(errors) == 1
        assert errors[0].file == "res://scenes/bullet.tscn"
        assert errors[0].line == 13
        assert "Parse Error" in errors[0].message


class TestFormatValidation:
    def test_success(self):
        result = ValidationResult(success=True)
        text = format_validation_for_llm(result)
        assert "PASSED" in text

    def test_success_with_scene_smoke(self):
        result = ValidationResult(success=True, smoke_checked_scenes=["res://scenes/game.tscn"])
        text = format_validation_for_llm(result)
        assert "Scene smoke checked" in text

    def test_failure(self):
        result = ValidationResult(
            success=False,
            errors=[GodotError("ERROR", "res://x.gd", 5, "bad", "script")],
            suggestion="Fix x.gd line 5",
        )
        text = format_validation_for_llm(result)
        assert "FAILED" in text
        assert "x.gd" in text
        assert "Fix" in text


class _DummyProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self._stdout = stdout.encode()
        self._stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_validate_project_smoke_checks_main_scene(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "project.godot").write_text(
        '[application]\nrun/main_scene="res://scenes/game.tscn"\n',
        encoding="utf-8",
    )

    calls = []
    processes = iter(
        [
            _DummyProcess(stdout="Godot Engine v4.4\n", returncode=0),
            _DummyProcess(
                stdout='ERROR: Failed to load script "res://scripts/enemy.gd" with error "Parse error".\n',
                returncode=1,
            ),
        ]
    )

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return next(processes)

    monkeypatch.setattr(
        "godot_agent.runtime.error_loop.asyncio.create_subprocess_exec",
        fake_exec,
    )

    result = await validate_project(
        str(project_root),
        godot_path="godot",
        timeout=5,
    )

    assert len(calls) == 2
    assert result.success is False
    assert result.smoke_checked_scenes == ["res://scenes/game.tscn"]
    assert any(error.file == "res://scripts/enemy.gd" for error in result.errors)

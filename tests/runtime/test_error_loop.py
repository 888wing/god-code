import pytest
from godot_agent.runtime.error_loop import parse_godot_output, format_validation_for_llm, ValidationResult, GodotError


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


class TestFormatValidation:
    def test_success(self):
        result = ValidationResult(success=True)
        text = format_validation_for_llm(result)
        assert "PASSED" in text

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

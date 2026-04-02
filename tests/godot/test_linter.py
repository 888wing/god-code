import pytest
from godot_agent.godot.gdscript_linter import lint_gdscript


class TestLinter:
    def test_missing_type_annotation(self):
        code = "extends Node\nvar x = 5\n"
        issues = lint_gdscript(code)
        assert any("type-annotation" in i.rule for i in issues)

    def test_pascal_case_function(self):
        code = "extends Node\nfunc DoStuff():\n\tpass\n"
        issues = lint_gdscript(code)
        assert any("func-naming" in i.rule for i in issues)

    def test_hardcoded_key(self):
        code = 'extends Node\nfunc _process(d):\n\tif Input.is_key_pressed(KEY_SPACE):\n\t\tpass\n'
        issues = lint_gdscript(code)
        assert any("input-map" in i.rule for i in issues)

    def test_clean_code_minimal_issues(self):
        code = 'extends Node2D\n\nconst SPEED: float = 200.0\n\nvar hp: int = 100\n\nfunc _ready() -> void:\n\tpass\n'
        issues = lint_gdscript(code)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_code_ordering(self):
        code = "extends Node\nfunc _ready():\n\tpass\nsignal died\n"
        issues = lint_gdscript(code)
        assert any("code-order" in i.rule for i in issues)

    def test_bool_operators(self):
        code = "extends Node\nfunc f():\n\tif x && y:\n\t\tpass\n"
        issues = lint_gdscript(code)
        assert any("bool-operators" in i.rule for i in issues)

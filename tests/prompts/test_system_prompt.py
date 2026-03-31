import pytest
from pathlib import Path
from godot_agent.prompts.system import build_system_prompt


class TestSystemPrompt:
    def test_includes_project_name(self, tmp_path):
        (tmp_path / "project.godot").write_text(
            'config_version=5\n\n[application]\nconfig/name="TestGame"\n'
        )
        prompt = build_system_prompt(project_root=tmp_path)
        assert "TestGame" in prompt

    def test_includes_autoloads(self, tmp_path):
        (tmp_path / "project.godot").write_text(
            'config_version=5\n\n[autoload]\nMyManager="*res://autoload/my.gd"\n'
        )
        prompt = build_system_prompt(project_root=tmp_path)
        assert "MyManager" in prompt

    def test_includes_structure_rules(self, tmp_path):
        (tmp_path / "project.godot").write_text("config_version=5\n")
        prompt = build_system_prompt(project_root=tmp_path)
        assert ".tscn" in prompt
        assert ".gd" in prompt

    def test_includes_tool_list(self, tmp_path):
        (tmp_path / "project.godot").write_text("config_version=5\n")
        prompt = build_system_prompt(project_root=tmp_path)
        assert "read_file" in prompt
        assert "screenshot" in prompt.lower()

    def test_no_project_godot(self, tmp_path):
        prompt = build_system_prompt(project_root=tmp_path)
        assert "No project.godot found" in prompt

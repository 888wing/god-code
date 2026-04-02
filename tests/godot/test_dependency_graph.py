import pytest
from pathlib import Path
from godot_agent.godot.dependency_graph import build_dependency_graph


class TestDependencyGraph:
    def test_basic_graph(self, tmp_path):
        (tmp_path / "project.godot").write_text(
            'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n'
            '[autoload]\nGM="*res://gm.gd"\n'
        )
        (tmp_path / "main.tscn").write_text(
            '[gd_scene format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n'
            '[node name="M" type="Node"]\n'
        )
        (tmp_path / "main.gd").write_text('extends Node\nvar b = preload("res://bullet.tscn")\n')
        (tmp_path / "bullet.tscn").write_text('[gd_scene format=3]\n[node name="B" type="Area2D"]\n')
        (tmp_path / "gm.gd").write_text("extends Node\n")

        graph = build_dependency_graph(tmp_path)
        assert graph.main_scene == "res://main.tscn"
        assert "GM" in graph.autoloads
        assert len(graph.nodes) >= 4

    def test_orphan_detection(self, tmp_path):
        (tmp_path / "project.godot").write_text('config_version=5\n')
        (tmp_path / "unused.gd").write_text("extends Node\n")
        graph = build_dependency_graph(tmp_path)
        assert "res://unused.gd" in graph.orphans()

    def test_format_summary(self, tmp_path):
        (tmp_path / "project.godot").write_text('config_version=5\n[application]\nrun/main_scene="res://m.tscn"\n')
        (tmp_path / "m.tscn").write_text('[gd_scene format=3]\n[node name="M" type="Node"]\n')
        graph = build_dependency_graph(tmp_path)
        summary = graph.format_summary()
        assert "Main Scene" in summary

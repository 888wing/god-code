import pytest
from pathlib import Path
from godot_agent.godot.consistency_checker import check_consistency, scan_project


class TestConsistencyChecker:
    def test_missing_preload_resource(self, tmp_path):
        gd = tmp_path / "player.gd"
        gd.write_text('extends Node\nvar scene = preload("res://missing.tscn")\n')
        issues = check_consistency(tmp_path)
        assert any("missing.tscn" in str(i) for i in issues)

    def test_valid_preload(self, tmp_path):
        (tmp_path / "bullet.tscn").write_text("[gd_scene format=3]\n")
        gd = tmp_path / "player.gd"
        gd.write_text('extends Node\nvar scene = preload("res://bullet.tscn")\n')
        issues = check_consistency(tmp_path)
        resource_errors = [i for i in issues if i.severity == "error"]
        assert len(resource_errors) == 0

    def test_group_not_added(self, tmp_path):
        gd = tmp_path / "game.gd"
        gd.write_text('extends Node\nfunc f():\n\tget_tree().call_group("ghosts", "hide")\n')
        issues = check_consistency(tmp_path)
        assert any("ghosts" in str(i) for i in issues)

    def test_scan_collision_from_tscn(self, tmp_path):
        tscn = tmp_path / "player.tscn"
        tscn.write_text('[gd_scene format=3]\n[node name="P" type="Area2D"]\ncollision_layer = 1\ncollision_mask = 8\n')
        scan = scan_project(tmp_path)
        assert len(scan.collision_configs) == 1

import pytest
from godot_agent.godot.tscn_validator import validate_tscn, validate_and_fix


class TestValidateTscn:
    def test_valid_scene(self):
        tscn = '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="x.gd" id="1"]\n[node name="R" type="Node"]\n'
        issues = validate_tscn(tscn)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_sub_resource_after_node(self):
        tscn = '[gd_scene format=3]\n[node name="R" type="Node"]\n[sub_resource type="X" id="1"]\n'
        issues = validate_tscn(tscn)
        errors = [i for i in issues if i.severity == "error"]
        assert any("after first node" in i.message for i in errors)

    def test_ext_resource_after_node(self):
        tscn = '[gd_scene format=3]\n[node name="R" type="Node"]\n[ext_resource type="X" path="y" id="1"]\n'
        issues = validate_tscn(tscn)
        errors = [i for i in issues if i.severity == "error"]
        assert any("after first node" in i.message for i in errors)

    def test_duplicate_node_names(self):
        tscn = '[gd_scene format=3]\n[node name="R" type="Node"]\n[node name="A" type="Node" parent="."]\n[node name="A" type="Node" parent="."]\n'
        issues = validate_tscn(tscn)
        assert any("Duplicate" in i.message for i in issues)

    def test_load_steps_mismatch(self):
        tscn = '[gd_scene load_steps=5 format=3]\n[ext_resource type="X" path="y" id="1"]\n[node name="R" type="Node"]\n'
        issues = validate_tscn(tscn)
        assert any("load_steps" in i.message for i in issues)

    def test_undeclared_ext_resource_ref(self):
        tscn = '[gd_scene format=3]\n[node name="R" type="Node"]\nscript = ExtResource("missing_id")\n'
        issues = validate_tscn(tscn)
        assert any("not declared" in i.message for i in issues)


class TestValidateAndFix:
    def test_auto_fix_ordering(self):
        bad = '[gd_scene format=3]\n[node name="R" type="Node"]\n[sub_resource type="X" id="1"]\nradius = 5\n'
        fixed, remaining = validate_and_fix(bad)
        errors = [i for i in remaining if i.severity == "error"]
        assert len(errors) == 0
        assert fixed.index("[sub_resource") < fixed.index("[node")

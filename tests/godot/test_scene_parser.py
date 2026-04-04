import pytest
from godot_agent.godot.scene_parser import parse_tscn, TscnScene

SAMPLE_TSCN = """[gd_scene load_steps=2 format=3 uid="uid://bbattlescene"]

[ext_resource type="Script" path="res://scenes/battle/battle_scene.gd" id="1_script"]

[node name="BattleScene" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
script = ExtResource("1_script")

[node name="Background" type="ColorRect" parent="."]
layout_mode = 1
color = Color(0.1, 0.1, 0.1, 1)

[node name="HPLabel" type="Label" parent="Background"]
text = "HP: 100"

[connection signal="ready" from="." to="." method="_on_ready"]
"""


class TestParseTscn:
    def test_parse_header(self):
        scene = parse_tscn(SAMPLE_TSCN)
        assert scene.format == 3
        assert scene.load_steps == 2

    def test_parse_ext_resources(self):
        scene = parse_tscn(SAMPLE_TSCN)
        assert len(scene.ext_resources) == 1
        assert scene.ext_resources[0].type == "Script"
        assert "battle_scene.gd" in scene.ext_resources[0].path

    def test_parse_nodes(self):
        scene = parse_tscn(SAMPLE_TSCN)
        assert len(scene.nodes) == 3
        assert scene.nodes[0].name == "BattleScene"
        assert scene.nodes[0].type == "Control"
        assert scene.nodes[1].name == "Background"
        assert scene.nodes[1].parent == "."
        assert scene.nodes[2].name == "HPLabel"
        assert scene.nodes[2].parent == "Background"

    def test_parse_node_properties(self):
        scene = parse_tscn(SAMPLE_TSCN)
        bg = scene.nodes[1]
        assert bg.properties["color"] == "Color(0.1, 0.1, 0.1, 1)"
        assert bg.property_value("color", typed=True) == {
            "__type__": "Color",
            "r": 0.1,
            "g": 0.1,
            "b": 0.1,
            "a": 1,
        }

    def test_parse_connections(self):
        scene = parse_tscn(SAMPLE_TSCN)
        assert len(scene.connections) == 1
        assert scene.connections[0].signal == "ready"

    def test_node_tree_paths(self):
        scene = parse_tscn(SAMPLE_TSCN)
        paths = scene.node_paths()
        assert "BattleScene" in paths
        assert "BattleScene/Background" in paths
        assert "BattleScene/Background/HPLabel" in paths

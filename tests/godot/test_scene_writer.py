import pytest
from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.godot.scene_writer import add_node, set_node_property, remove_node, add_connection

SIMPLE_SCENE = """[gd_scene format=3]

[node name="Root" type="Control"]

[node name="Label" type="Label" parent="."]
text = "Hello"
"""


class TestAddNode:
    def test_add_child_node(self):
        result = add_node(SIMPLE_SCENE, parent=".", name="Button", type="Button")
        scene = parse_tscn(result)
        names = [n.name for n in scene.nodes]
        assert "Button" in names

    def test_add_node_with_properties(self):
        result = add_node(SIMPLE_SCENE, parent=".", name="Sprite", type="Sprite2D",
                          properties={"position": "Vector2(100, 200)"})
        scene = parse_tscn(result)
        sprite = [n for n in scene.nodes if n.name == "Sprite"][0]
        assert sprite.properties["position"] == "Vector2(100, 200)"


class TestSetNodeProperty:
    def test_modify_existing_property(self):
        result = set_node_property(SIMPLE_SCENE, node_name="Label", key="text", value='"World"')
        scene = parse_tscn(result)
        label = [n for n in scene.nodes if n.name == "Label"][0]
        assert label.properties["text"] == '"World"'

    def test_add_new_property(self):
        result = set_node_property(SIMPLE_SCENE, node_name="Label", key="visible", value="false")
        assert "visible = false" in result


class TestRemoveNode:
    def test_remove_node(self):
        result = remove_node(SIMPLE_SCENE, node_name="Label")
        scene = parse_tscn(result)
        names = [n.name for n in scene.nodes]
        assert "Label" not in names
        assert "Root" in names


class TestAddConnection:
    def test_add_signal_connection(self):
        result = add_connection(SIMPLE_SCENE, signal_name="pressed", from_node="Button",
                                to_node=".", method="_on_button_pressed")
        scene = parse_tscn(result)
        assert len(scene.connections) == 1
        assert scene.connections[0].signal == "pressed"

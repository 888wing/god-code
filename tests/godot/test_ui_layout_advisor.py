from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.godot.ui_layout_advisor import LAYOUT_PRESETS, plan_ui_layout, validate_ui_layout


def test_plan_ui_layout_returns_known_preset():
    config = plan_ui_layout("pause_menu")

    assert config is not None
    assert config.root_type == "CenterContainer"
    nodes = config.to_tscn_nodes()
    assert nodes[0]["name"] == "PauseMenu"
    assert any(node["name"] == "ResumeBtn" for node in nodes)


def test_validate_ui_layout_flags_small_buttons_and_missing_theme():
    scene = parse_tscn(
        '[gd_scene format=3]\n\n'
        '[node name="UIRoot" type="Control"]\n'
        '[node name="VBox" type="VBoxContainer" parent="."]\n'
        '[node name="TinyButton" type="Button" parent="VBox"]\n'
        'custom_minimum_size = Vector2(120, 24)\n'
    )

    warnings = validate_ui_layout(scene)

    assert any("bare Control" in warning for warning in warnings)
    assert any("no Theme" in warning for warning in warnings)
    assert any("below 44px" in warning for warning in warnings)


def test_all_layout_presets_can_describe_themselves():
    for name, config in LAYOUT_PRESETS.items():
        assert name in config.describe()
        assert config.to_tscn_nodes()

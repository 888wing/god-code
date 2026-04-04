from godot_agent.godot.variant_codec import parse_variant, serialize_variant


def test_parse_variant_supports_common_godot_values():
    assert parse_variant("true") is True
    assert parse_variant("42") == 42
    assert parse_variant("3.5") == 3.5
    assert parse_variant('"Play"') == "Play"
    assert parse_variant('&"Music"') == {"__type__": "StringName", "value": "Music"}
    assert parse_variant("Vector2(12, 44)") == {"__type__": "Vector2", "x": 12, "y": 44}


def test_serialize_variant_supports_typed_helpers():
    assert serialize_variant({"__type__": "String", "value": "Resume"}) == '"Resume"'
    assert serialize_variant({"__type__": "StringName", "value": "UI"}) == '&"UI"'
    assert serialize_variant({"__type__": "Vector2", "x": 200, "y": 44}) == "Vector2(200, 44)"
    assert serialize_variant({"__type__": "Color", "r": 1, "g": 0.5, "b": 0, "a": 1}) == "Color(1, 0.5, 0, 1)"


def test_serialize_variant_preserves_existing_raw_literals():
    assert serialize_variant('"World"') == '"World"'
    assert serialize_variant("Vector2(10, 20)") == "Vector2(10, 20)"
    assert serialize_variant("PROCESS_MODE_ALWAYS") == "PROCESS_MODE_ALWAYS"

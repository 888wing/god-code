from godot_agent.godot.audio_scaffolder import AUDIO_PRESETS, scaffold_audio_nodes, validate_audio_nodes
from godot_agent.godot.scene_parser import parse_tscn


def test_scaffold_audio_nodes_emits_expected_nodes():
    nodes = scaffold_audio_nodes("standard")

    assert len(nodes) == len(AUDIO_PRESETS["standard"])
    assert any(node["name"] == "BGMPlayer" for node in nodes)
    assert nodes[0]["properties"]["bus"] == {"__type__": "StringName", "value": "Music"}


def test_validate_audio_nodes_flags_unknown_bus_and_missing_stream(tmp_path):
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="AudioGame"\n\n[audio]\nbuses/default_bus_layout="res://default_bus_layout.tres"\n'
    )
    (tmp_path / "default_bus_layout.tres").write_text(
        '[gd_resource type="AudioBusLayout" format=3]\n'
        '[bus name="Master" volume_db=0.0 send=""]\n'
        '[bus name="Music" volume_db=0.0 send="Master"]\n'
    )
    scene = parse_tscn(
        '[gd_scene format=3]\n\n'
        '[node name="BGM" type="AudioStreamPlayer"]\n'
        'bus = &"UnknownBus"\n'
    )

    warnings = validate_audio_nodes(scene, tmp_path)

    assert any("unknown bus" in warning.lower() for warning in warnings)
    assert any("no stream" in warning.lower() for warning in warnings)

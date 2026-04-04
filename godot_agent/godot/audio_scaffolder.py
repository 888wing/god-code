"""Audio node scaffolding and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godot_agent.godot.project import available_audio_buses
from godot_agent.godot.scene_parser import TscnScene


@dataclass(frozen=True)
class AudioNodeConfig:
    name: str
    node_type: str
    bus: str
    autoplay: bool
    stream_path: str | None
    properties: dict[str, Any]

    def to_tscn_properties(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "bus": {"__type__": "StringName", "value": self.bus},
        }
        if self.autoplay:
            payload["autoplay"] = True
        if self.stream_path:
            payload["stream"] = self.stream_path
        payload.update(self.properties)
        return payload


AUDIO_PRESETS: dict[str, list[AudioNodeConfig]] = {
    "minimal": [
        AudioNodeConfig("BGMPlayer", "AudioStreamPlayer", "Music", True, None, {"volume_db": -6.0}),
        AudioNodeConfig("SFXPlayer", "AudioStreamPlayer", "SFX", False, None, {}),
    ],
    "standard": [
        AudioNodeConfig("BGMPlayer", "AudioStreamPlayer", "Music", True, None, {"volume_db": -6.0}),
        AudioNodeConfig("SFXPlayer", "AudioStreamPlayer", "SFX", False, None, {}),
        AudioNodeConfig("UIPlayer", "AudioStreamPlayer", "UI", False, None, {"volume_db": -3.0}),
        AudioNodeConfig("AmbientPlayer", "AudioStreamPlayer", "Music", False, None, {"volume_db": -12.0}),
    ],
    "positional": [
        AudioNodeConfig("SFX2D", "AudioStreamPlayer2D", "SFX", False, None, {"max_distance": 500.0}),
    ],
}


def scaffold_audio_nodes(pattern: str = "standard", parent_node: str = ".") -> list[dict[str, Any]]:
    preset = AUDIO_PRESETS.get(pattern, AUDIO_PRESETS["minimal"])
    return [
        {
            "parent": parent_node,
            "name": cfg.name,
            "type": cfg.node_type,
            "properties": cfg.to_tscn_properties(),
        }
        for cfg in preset
    ]


def _bus_name(value: object) -> str:
    if isinstance(value, dict) and value.get("__type__") == "StringName":
        return str(value.get("value", ""))
    if isinstance(value, str):
        return value.strip('"')
    return ""


def validate_audio_nodes(scene: TscnScene, project_root: Path) -> list[str]:
    warnings: list[str] = []
    audio_nodes = [node for node in scene.nodes if "AudioStreamPlayer" in (node.type or "")]
    if not audio_nodes:
        return warnings

    buses = available_audio_buses(project_root)
    for node in audio_nodes:
        if "bus" not in node.properties:
            warnings.append(f"Audio node '{node.name}' has no explicit bus assignment.")
        else:
            bus_name = _bus_name(node.property_value("bus", typed=True))
            if bus_name and bus_name not in buses:
                warnings.append(f"Audio node '{node.name}' references unknown bus '{bus_name}'.")

        if "stream" not in node.properties:
            warnings.append(f"Audio node '{node.name}' has no stream assigned.")

    return warnings

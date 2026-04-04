from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_AUDIO_BUSES = ["Master", "Music", "SFX", "UI"]


@dataclass
class GodotProject:
    name: str = ""
    version: str = ""
    main_scene: str = ""
    godot_version: str = ""
    autoloads: dict[str, str] = field(default_factory=dict)
    viewport_width: int = 1920
    viewport_height: int = 1080
    renderer: str = ""
    audio_bus_layout: str = ""
    audio_buses: list[str] = field(default_factory=lambda: list(DEFAULT_AUDIO_BUSES))
    raw_sections: dict[str, dict[str, str]] = field(default_factory=dict)


def _parse_bus_layout(path: Path) -> list[str]:
    if not path.exists():
        return list(DEFAULT_AUDIO_BUSES)
    buses: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r'^\[bus\s+name="([^"]+)"', line.strip())
        if match:
            buses.append(match.group(1))
    return buses or list(DEFAULT_AUDIO_BUSES)


def parse_project_godot(path: Path) -> GodotProject:
    text = path.read_text(encoding="utf-8", errors="replace")
    proj = GodotProject()
    current_section = ""
    section_data: dict[str, dict[str, str]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        section_match = re.match(r"^\[(\w+)\]", line)
        if section_match:
            current_section = section_match.group(1)
            section_data.setdefault(current_section, {})
            continue
        kv_match = re.match(r'^(.+?)=(.+)$', line)
        if kv_match:
            key = kv_match.group(1).strip()
            val = kv_match.group(2).strip().strip('"')
            section_data.setdefault(current_section, {})[key] = val

    proj.raw_sections = section_data
    app = section_data.get("application", {})
    proj.name = app.get("config/name", "")
    proj.version = app.get("config/version", "")
    proj.main_scene = app.get("run/main_scene", "")

    for key, val in section_data.get("autoload", {}).items():
        proj.autoloads[key] = val.lstrip("*")

    display = section_data.get("display", {})
    if "window/size/viewport_width" in display:
        proj.viewport_width = int(display["window/size/viewport_width"])
    if "window/size/viewport_height" in display:
        proj.viewport_height = int(display["window/size/viewport_height"])

    rendering = section_data.get("rendering", {})
    proj.renderer = rendering.get("renderer/rendering_method", "")

    audio = section_data.get("audio", {})
    proj.audio_bus_layout = audio.get("buses/default_bus_layout", "")
    if proj.audio_bus_layout.startswith("res://"):
        bus_layout_path = path.parent / proj.audio_bus_layout.removeprefix("res://")
        proj.audio_buses = _parse_bus_layout(bus_layout_path)
    else:
        default_bus_layout = path.parent / "default_bus_layout.tres"
        proj.audio_buses = _parse_bus_layout(default_bus_layout)
    return proj


def available_audio_buses(project_root: Path) -> set[str]:
    project_file = project_root / "project.godot"
    if not project_file.exists():
        return set(DEFAULT_AUDIO_BUSES)
    project = parse_project_godot(project_file)
    return set(project.audio_buses or DEFAULT_AUDIO_BUSES)

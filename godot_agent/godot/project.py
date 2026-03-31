from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


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
    raw_sections: dict[str, dict[str, str]] = field(default_factory=dict)


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
    return proj

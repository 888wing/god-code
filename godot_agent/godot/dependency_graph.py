"""Builds a dependency graph of a Godot project.

Scans .tscn, .gd, and project.godot to map:
- Scene → Script attachments
- Scene → Sub-scene instances
- Script → preload/load references
- Autoload declarations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DepNode:
    path: str
    type: str  # "scene", "script", "resource", "autoload"
    depends_on: list[str] = field(default_factory=list)
    depended_by: list[str] = field(default_factory=list)


@dataclass
class DependencyGraph:
    nodes: dict[str, DepNode] = field(default_factory=dict)
    autoloads: dict[str, str] = field(default_factory=dict)
    main_scene: str = ""

    def get_or_create(self, path: str, node_type: str) -> DepNode:
        if path not in self.nodes:
            self.nodes[path] = DepNode(path=path, type=node_type)
        return self.nodes[path]

    def add_dependency(self, from_path: str, to_path: str, from_type: str, to_type: str) -> None:
        src = self.get_or_create(from_path, from_type)
        dst = self.get_or_create(to_path, to_type)
        if to_path not in src.depends_on:
            src.depends_on.append(to_path)
        if from_path not in dst.depended_by:
            dst.depended_by.append(from_path)

    def orphans(self) -> list[str]:
        """Files that nothing depends on and aren't autoloads or main scene."""
        protected = set(self.autoloads.values()) | {self.main_scene}
        return [
            path for path, node in self.nodes.items()
            if not node.depended_by and path not in protected
        ]

    def format_summary(self) -> str:
        lines = ["## Project Dependency Graph", ""]

        if self.main_scene:
            lines.append(f"**Main Scene**: {self.main_scene}")

        if self.autoloads:
            lines.append("\n**Autoloads**:")
            for name, path in self.autoloads.items():
                lines.append(f"  - {name} → {path}")

        lines.append(f"\n**Files**: {len(self.nodes)} total")
        scenes = [n for n in self.nodes.values() if n.type == "scene"]
        scripts = [n for n in self.nodes.values() if n.type == "script"]
        lines.append(f"  - {len(scenes)} scenes, {len(scripts)} scripts")

        # Show dependency chains
        lines.append("\n**Dependencies**:")
        for path, node in sorted(self.nodes.items()):
            if node.depends_on:
                deps = ", ".join(node.depends_on)
                lines.append(f"  {path} → [{deps}]")

        orphans = self.orphans()
        if orphans:
            lines.append(f"\n**Orphans** (unreferenced files): {', '.join(orphans)}")

        return "\n".join(lines)


def build_dependency_graph(project_root: Path) -> DependencyGraph:
    """Scan project and build complete dependency graph."""
    graph = DependencyGraph()

    # Parse project.godot for autoloads and main scene
    project_file = project_root / "project.godot"
    if project_file.exists():
        _parse_project_godot(project_file, graph)

    # Scan .tscn files
    for tscn in project_root.rglob("*.tscn"):
        if ".godot" in str(tscn):
            continue
        rel = "res://" + str(tscn.relative_to(project_root))
        _parse_tscn(tscn, rel, graph)

    # Scan .gd files
    for gd in project_root.rglob("*.gd"):
        if ".godot" in str(gd):
            continue
        rel = "res://" + str(gd.relative_to(project_root))
        _parse_gdscript(gd, rel, graph)

    return graph


def _parse_project_godot(path: Path, graph: DependencyGraph) -> None:
    text = path.read_text(errors="replace")
    in_autoload = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[autoload]":
            in_autoload = True
            continue
        if stripped.startswith("[") and stripped != "[autoload]":
            in_autoload = False
            continue

        if in_autoload:
            m = re.match(r'^(\w+)="?\*?(res://[^"]+)"?', stripped)
            if m:
                graph.autoloads[m.group(1)] = m.group(2)
                graph.get_or_create(m.group(2), "autoload")

        ms = re.match(r'^run/main_scene="(res://[^"]+)"', stripped)
        if ms:
            graph.main_scene = ms.group(1)


def _parse_tscn(path: Path, res_path: str, graph: DependencyGraph) -> None:
    text = path.read_text(errors="replace")
    graph.get_or_create(res_path, "scene")

    # ext_resource references
    for m in re.finditer(r'\[ext_resource.*?path="(res://[^"]+)"', text):
        ref_path = m.group(1)
        ref_type = "script" if ref_path.endswith(".gd") else "scene" if ref_path.endswith(".tscn") else "resource"
        graph.add_dependency(res_path, ref_path, "scene", ref_type)

    # PackedScene instances
    for m in re.finditer(r'instance=ExtResource\("([^"]+)"\)', text):
        pass  # Already covered by ext_resource


def _parse_gdscript(path: Path, res_path: str, graph: DependencyGraph) -> None:
    text = path.read_text(errors="replace")
    graph.get_or_create(res_path, "script")

    for m in re.finditer(r'(?:preload|load)\s*\(\s*"(res://[^"]+)"', text):
        ref_path = m.group(1)
        ref_type = "scene" if ref_path.endswith(".tscn") else "script" if ref_path.endswith(".gd") else "resource"
        graph.add_dependency(res_path, ref_path, "script", ref_type)

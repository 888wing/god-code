from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ExtResource:
    type: str
    path: str
    id: str


@dataclass
class TscnNode:
    name: str
    type: str = ""
    parent: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    instance: str | None = None


@dataclass
class TscnConnection:
    signal: str
    from_node: str
    to_node: str
    method: str


@dataclass
class TscnScene:
    format: int = 0
    load_steps: int = 0
    uid: str = ""
    ext_resources: list[ExtResource] = field(default_factory=list)
    sub_resources: list[dict] = field(default_factory=list)
    nodes: list[TscnNode] = field(default_factory=list)
    connections: list[TscnConnection] = field(default_factory=list)
    raw_text: str = ""

    def node_paths(self) -> list[str]:
        paths = []
        root_name = self.nodes[0].name if self.nodes else ""
        for node in self.nodes:
            if node.parent is None:
                paths.append(root_name)
            elif node.parent == ".":
                paths.append(f"{root_name}/{node.name}")
            else:
                paths.append(f"{root_name}/{node.parent}/{node.name}")
        return paths


def _parse_header_attrs(text: str) -> dict[str, str]:
    attrs = {}
    for m in re.finditer(r'(\w+)=(".*?"|\S+)', text):
        key = m.group(1)
        val = m.group(2).strip('"')
        attrs[key] = val
    return attrs


def parse_tscn(text: str) -> TscnScene:
    scene = TscnScene(raw_text=text)
    current_node: TscnNode | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        bracket_match = re.match(r'^\[(\w+)(.*)\]$', stripped)
        if bracket_match:
            tag = bracket_match.group(1)
            attrs_str = bracket_match.group(2)
            attrs = _parse_header_attrs(attrs_str)

            if tag == "gd_scene":
                scene.format = int(attrs.get("format", "0"))
                scene.load_steps = int(attrs.get("load_steps", "0"))
                scene.uid = attrs.get("uid", "")
                current_node = None
            elif tag == "ext_resource":
                scene.ext_resources.append(ExtResource(
                    type=attrs.get("type", ""),
                    path=attrs.get("path", ""),
                    id=attrs.get("id", ""),
                ))
                current_node = None
            elif tag == "node":
                node = TscnNode(
                    name=attrs.get("name", ""),
                    type=attrs.get("type", ""),
                    parent=attrs.get("parent"),
                    instance=attrs.get("instance"),
                )
                scene.nodes.append(node)
                current_node = node
            elif tag == "connection":
                scene.connections.append(TscnConnection(
                    signal=attrs.get("signal", ""),
                    from_node=attrs.get("from", ""),
                    to_node=attrs.get("to", ""),
                    method=attrs.get("method", ""),
                ))
                current_node = None
            continue

        if current_node is not None:
            prop_match = re.match(r'^(\w+)\s*=\s*(.+)$', stripped)
            if prop_match:
                current_node.properties[prop_match.group(1)] = prop_match.group(2).strip()

    return scene

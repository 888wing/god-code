from __future__ import annotations
import re

from godot_agent.godot.variant_codec import serialize_variant


def _serialize_properties(properties: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key, value in properties.items():
        lines.append(f"{key} = {serialize_variant(value)}")
    return lines


def add_node(tscn_text: str, parent: str, name: str, type: str,
             properties: dict[str, object] | None = None) -> str:
    lines = [f'\n[node name="{name}" type="{type}" parent="{parent}"]']
    if properties:
        lines.extend(_serialize_properties(properties))
    lines.append("")
    node_block = "\n".join(lines)
    connection_match = re.search(r'\n\[connection ', tscn_text)
    if connection_match:
        pos = connection_match.start()
        return tscn_text[:pos] + node_block + tscn_text[pos:]
    return tscn_text.rstrip() + "\n" + node_block


def set_node_property(tscn_text: str, node_name: str, key: str, value: object) -> str:
    serialized = serialize_variant(value)
    lines = tscn_text.splitlines(keepends=True)
    in_target = False
    prop_found = False
    result = []

    for line in lines:
        node_match = re.match(r'\[node name="([^"]+)"', line)
        if node_match:
            if in_target and not prop_found:
                result.append(f"{key} = {serialized}\n")
                prop_found = True
            in_target = node_match.group(1) == node_name
        elif re.match(r'^\[', line.strip()) and not line.strip().startswith("[node"):
            if in_target and not prop_found:
                result.append(f"{key} = {serialized}\n")
                result.append("\n")
                prop_found = True
            in_target = False

        if in_target and re.match(rf'^{re.escape(key)}\s*=', line):
            result.append(f"{key} = {serialized}\n")
            prop_found = True
            continue

        result.append(line)

    if in_target and not prop_found:
        result.append(f"{key} = {serialized}\n")

    return "".join(result)


def remove_node(tscn_text: str, node_name: str) -> str:
    lines = tscn_text.splitlines(keepends=True)
    result = []
    skip = False

    for line in lines:
        connection_match = re.match(r'\[connection\s+.*from="([^"]+)".*to="([^"]+)".*\]', line.strip())
        if connection_match and node_name in {connection_match.group(1), connection_match.group(2)}:
            continue
        node_match = re.match(r'\[node name="([^"]+)"', line)
        if node_match:
            if node_match.group(1) == node_name:
                skip = True
                continue
            else:
                skip = False
        if skip and re.match(r'^\[', line.strip()):
            skip = False
        if not skip:
            result.append(line)

    return "".join(result)


def add_connection(tscn_text: str, signal_name: str, from_node: str,
                   to_node: str, method: str) -> str:
    conn_line = f'\n[connection signal="{signal_name}" from="{from_node}" to="{to_node}" method="{method}"]\n'
    return tscn_text.rstrip() + conn_line

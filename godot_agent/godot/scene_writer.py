from __future__ import annotations
import re


def add_node(tscn_text: str, parent: str, name: str, type: str,
             properties: dict[str, str] | None = None) -> str:
    lines = [f'\n[node name="{name}" type="{type}" parent="{parent}"]']
    if properties:
        for k, v in properties.items():
            lines.append(f"{k} = {v}")
    lines.append("")
    node_block = "\n".join(lines)
    connection_match = re.search(r'\n\[connection ', tscn_text)
    if connection_match:
        pos = connection_match.start()
        return tscn_text[:pos] + node_block + tscn_text[pos:]
    return tscn_text.rstrip() + "\n" + node_block


def set_node_property(tscn_text: str, node_name: str, key: str, value: str) -> str:
    lines = tscn_text.splitlines(keepends=True)
    in_target = False
    prop_found = False
    result = []

    for line in lines:
        node_match = re.match(r'\[node name="([^"]+)"', line)
        if node_match:
            if in_target and not prop_found:
                result.append(f"{key} = {value}\n")
                prop_found = True
            in_target = node_match.group(1) == node_name
        elif re.match(r'^\[', line.strip()) and not line.strip().startswith("[node"):
            if in_target and not prop_found:
                result.append(f"{key} = {value}\n")
                result.append("\n")
                prop_found = True
            in_target = False

        if in_target and re.match(rf'^{re.escape(key)}\s*=', line):
            result.append(f"{key} = {value}\n")
            prop_found = True
            continue

        result.append(line)

    if in_target and not prop_found:
        result.append(f"{key} = {value}\n")

    return "".join(result)


def remove_node(tscn_text: str, node_name: str) -> str:
    lines = tscn_text.splitlines(keepends=True)
    result = []
    skip = False

    for line in lines:
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

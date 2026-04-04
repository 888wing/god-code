"""Minimal Godot Variant parsing/serialization helpers.

This codec intentionally supports only the subset of Variant syntax needed by
god-code's structured scene tooling in v0.7. Unknown values fall back to raw
strings instead of attempting lossy parsing.
"""

from __future__ import annotations

import json
import re
from typing import Any


_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?(?:\d+\.\d+|\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")
_CALL_RE = re.compile(r"^(?P<name>[A-Za-z_]\w*)\((?P<body>.*)\)$")


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escape = False

    for char in text:
        if in_string:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            current.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(depth - 1, 0)
        if char == separator and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _parse_number(text: str) -> int | float | None:
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return None


def _dict_type(value: dict[str, Any]) -> str | None:
    explicit = str(value.get("__type__") or value.get("type") or value.get("__godot__") or "").strip()
    if explicit:
        return explicit

    keys = set(value)
    if {"x", "y"} <= keys and keys <= {"x", "y", "__type__", "type", "__godot__"}:
        return "Vector2"
    if {"r", "g", "b"} <= keys and keys <= {"r", "g", "b", "a", "__type__", "type", "__godot__"}:
        return "Color"
    return None


def _is_probably_godot_literal(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped in {"true", "false", "null"}:
        return True
    if stripped.startswith('"') and stripped.endswith('"'):
        return True
    if stripped.startswith('&"') and stripped.endswith('"'):
        return True
    if stripped.startswith("[") and stripped.endswith("]"):
        return True
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    if _parse_number(stripped) is not None:
        return True
    return bool(_CALL_RE.match(stripped))


def parse_variant(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    if stripped.startswith('&"') and stripped.endswith('"'):
        return {"__type__": "StringName", "value": stripped[2:-1]}
    if stripped.startswith('"') and stripped.endswith('"'):
        return json.loads(stripped)

    number = _parse_number(stripped)
    if number is not None:
        return number

    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [parse_variant(item) for item in _split_top_level(inner)]

    if stripped.startswith("{") and stripped.endswith("}"):
        inner = stripped[1:-1].strip()
        if not inner:
            return {}
        parsed: dict[str, Any] = {}
        for item in _split_top_level(inner):
            if ":" not in item:
                return stripped
            key_text, value_text = item.split(":", 1)
            key = key_text.strip().strip('"')
            parsed[key] = parse_variant(value_text.strip())
        return parsed

    match = _CALL_RE.match(stripped)
    if not match:
        return stripped

    name = match.group("name")
    args = _split_top_level(match.group("body"))
    if name == "Vector2" and len(args) == 2:
        return {"__type__": "Vector2", "x": parse_variant(args[0]), "y": parse_variant(args[1])}
    if name == "Color" and len(args) in {3, 4}:
        parsed = [parse_variant(arg) for arg in args]
        payload = {"__type__": "Color", "r": parsed[0], "g": parsed[1], "b": parsed[2]}
        if len(parsed) == 4:
            payload["a"] = parsed[3]
        return payload
    return stripped


def serialize_variant(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value if _is_probably_godot_literal(value) else json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(serialize_variant(item) for item in value) + "]"
    if isinstance(value, dict):
        dict_type = _dict_type(value)
        if dict_type == "String":
            return json.dumps(str(value.get("value", "")))
        if dict_type == "StringName":
            return f'&"{value.get("value", "")}"'
        if dict_type == "Vector2":
            return f'Vector2({serialize_variant(value.get("x", 0))}, {serialize_variant(value.get("y", 0))})'
        if dict_type == "Color":
            channels = [value.get("r", 0), value.get("g", 0), value.get("b", 0)]
            if "a" in value:
                channels.append(value.get("a", 1))
            return "Color(" + ", ".join(serialize_variant(channel) for channel in channels) + ")"
        body = ", ".join(
            f"{json.dumps(str(key))}: {serialize_variant(item)}"
            for key, item in value.items()
            if key not in {"__type__", "type", "__godot__"}
        )
        return "{" + body + "}"
    return str(value)

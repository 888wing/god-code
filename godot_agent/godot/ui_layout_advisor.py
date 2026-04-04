"""Structured UI layout presets and validators for Godot Control scenes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from godot_agent.godot.scene_parser import TscnNode, TscnScene


_CONTROL_TYPES = {
    "Control",
    "Label",
    "Button",
    "TextureRect",
    "ProgressBar",
    "RichTextLabel",
    "PanelContainer",
    "MarginContainer",
    "VBoxContainer",
    "HBoxContainer",
    "GridContainer",
    "CenterContainer",
    "ScrollContainer",
    "TabContainer",
    "CanvasLayer",
    "ColorRect",
}

_CONTAINER_TYPES = {
    "PanelContainer",
    "MarginContainer",
    "VBoxContainer",
    "HBoxContainer",
    "GridContainer",
    "CenterContainer",
    "ScrollContainer",
    "TabContainer",
}


def _is_control_type(node_type: str) -> bool:
    return node_type in _CONTROL_TYPES or node_type.endswith("Container")


def _is_container_type(node_type: str) -> bool:
    return node_type in _CONTAINER_TYPES or node_type.endswith("Container")


def _parent_node(node: TscnNode, scene: TscnScene) -> TscnNode | None:
    if not node.parent or node.parent == ".":
        return scene.nodes[0] if scene.nodes else None
    parent_name = node.parent.split("/")[-1]
    return next((candidate for candidate in scene.nodes if candidate.name == parent_name), None)


def _vector2_dict(value: object) -> dict[str, float]:
    if isinstance(value, dict) and value.get("__type__") == "Vector2":
        return {"x": float(value.get("x", 0)), "y": float(value.get("y", 0))}
    if isinstance(value, dict) and {"x", "y"} <= set(value):
        return {"x": float(value.get("x", 0)), "y": float(value.get("y", 0))}
    return {"x": 0.0, "y": 0.0}


@dataclass(frozen=True)
class UILayoutConfig:
    pattern: str
    root_name: str
    root_type: str
    root_anchor: dict[str, float] = field(default_factory=dict)
    root_margins: dict[str, float] = field(default_factory=dict)
    children: list[dict[str, Any]] = field(default_factory=list)
    theme_notes: str = ""
    process_mode: str | None = None

    def _root_properties(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
            f"anchor_{key}": value for key, value in self.root_anchor.items()
        }
        properties.update({f"offset_{key}": value for key, value in self.root_margins.items()})
        if self.process_mode:
            properties["process_mode"] = self.process_mode
        return properties

    def _flatten_child_specs(self, parent: str, children: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for child in children:
            properties = {
                key: value
                for key, value in child.items()
                if key not in {"name", "type", "children"}
            }
            nodes.append(
                {
                    "parent": parent,
                    "name": child["name"],
                    "type": child["type"],
                    "properties": properties,
                }
            )
            nodes.extend(self._flatten_child_specs(child["name"], child.get("children", [])))
        return nodes

    def to_tscn_nodes(self) -> list[dict[str, Any]]:
        root = {
            "parent": ".",
            "name": self.root_name,
            "type": self.root_type,
            "properties": self._root_properties(),
        }
        return [root, *self._flatten_child_specs(self.root_name, self.children)]

    def to_gdscript(self) -> str:
        lines = [
            f'var root := {self.root_type}.new()',
            f'root.name = "{self.root_name}"',
        ]
        for key, value in self._root_properties().items():
            lines.append(f'root.set("{key}", {value!r})')
        lines.append("add_child(root)")
        return "\n".join(lines)

    def describe(self) -> str:
        return (
            f"{self.pattern}: root {self.root_type} '{self.root_name}' with "
            f"{len(self.children)} direct child group(s). {self.theme_notes}"
        ).strip()


LAYOUT_PRESETS: dict[str, UILayoutConfig] = {
    "hud_overlay": UILayoutConfig(
        pattern="hud_overlay",
        root_name="HUD",
        root_type="MarginContainer",
        root_anchor={"left": 0, "top": 0, "right": 1, "bottom": 1},
        root_margins={"left": 16, "top": 8, "right": -16, "bottom": -8},
        children=[
            {"name": "TopBar", "type": "HBoxContainer", "size_flags_horizontal": 3},
            {"name": "BottomBar", "type": "HBoxContainer", "size_flags_horizontal": 3, "size_flags_vertical": 8},
        ],
        theme_notes="Set a Theme on the HUD root and let child controls inherit it.",
    ),
    "pause_menu": UILayoutConfig(
        pattern="pause_menu",
        root_name="PauseMenu",
        root_type="CenterContainer",
        root_anchor={"left": 0, "top": 0, "right": 1, "bottom": 1},
        children=[
            {
                "name": "Panel",
                "type": "PanelContainer",
                "children": [
                    {
                        "name": "VBox",
                        "type": "VBoxContainer",
                        "children": [
                            {"name": "Title", "type": "Label", "text": {"__type__": "String", "value": "PAUSED"}},
                            {"name": "ResumeBtn", "type": "Button", "text": {"__type__": "String", "value": "Resume"}, "custom_minimum_size": {"__type__": "Vector2", "x": 200, "y": 44}},
                            {"name": "SettingsBtn", "type": "Button", "text": {"__type__": "String", "value": "Settings"}, "custom_minimum_size": {"__type__": "Vector2", "x": 200, "y": 44}},
                            {"name": "QuitBtn", "type": "Button", "text": {"__type__": "String", "value": "Quit"}, "custom_minimum_size": {"__type__": "Vector2", "x": 200, "y": 44}},
                        ],
                    }
                ],
            }
        ],
        theme_notes="Use a centered PanelContainer with large touch-safe buttons.",
        process_mode="PROCESS_MODE_ALWAYS",
    ),
    "dialog_box": UILayoutConfig(
        pattern="dialog_box",
        root_name="DialogBox",
        root_type="MarginContainer",
        root_anchor={"left": 0, "top": 0.7, "right": 1, "bottom": 1},
        root_margins={"left": 32, "right": -32, "bottom": -16},
        children=[
            {
                "name": "Panel",
                "type": "PanelContainer",
                "children": [
                    {
                        "name": "VBox",
                        "type": "VBoxContainer",
                        "children": [
                            {"name": "SpeakerName", "type": "Label"},
                            {"name": "DialogText", "type": "RichTextLabel", "bbcode_enabled": True, "fit_content": True, "size_flags_vertical": 3},
                            {"name": "ContinueIndicator", "type": "TextureRect", "size_flags_horizontal": 8},
                        ],
                    }
                ],
            }
        ],
        theme_notes="Anchor to the lower portion of the viewport for dialog scenes.",
    ),
    "inventory_grid": UILayoutConfig(
        pattern="inventory_grid",
        root_name="Inventory",
        root_type="PanelContainer",
        root_anchor={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9},
        children=[
            {
                "name": "Margin",
                "type": "MarginContainer",
                "children": [
                    {
                        "name": "VBox",
                        "type": "VBoxContainer",
                        "children": [
                            {"name": "Header", "type": "HBoxContainer"},
                            {
                                "name": "Scroll",
                                "type": "ScrollContainer",
                                "size_flags_vertical": 3,
                                "children": [
                                    {"name": "Grid", "type": "GridContainer", "columns": 4, "size_flags_horizontal": 3}
                                ],
                            },
                            {"name": "Footer", "type": "HBoxContainer"},
                        ],
                    }
                ],
            }
        ],
        theme_notes="Inventory content should scroll and grid children should expand vertically.",
    ),
    "title_screen": UILayoutConfig(
        pattern="title_screen",
        root_name="TitleScreen",
        root_type="CenterContainer",
        root_anchor={"left": 0, "top": 0, "right": 1, "bottom": 1},
        children=[
            {
                "name": "VBox",
                "type": "VBoxContainer",
                "alignment": 1,
                "children": [
                    {"name": "Title", "type": "Label", "text": {"__type__": "String", "value": "GAME TITLE"}, "horizontal_alignment": 1},
                    {"name": "Spacer", "type": "Control", "custom_minimum_size": {"__type__": "Vector2", "x": 0, "y": 40}},
                    {"name": "StartBtn", "type": "Button", "text": {"__type__": "String", "value": "Start Game"}, "custom_minimum_size": {"__type__": "Vector2", "x": 240, "y": 48}},
                    {"name": "OptionsBtn", "type": "Button", "text": {"__type__": "String", "value": "Options"}, "custom_minimum_size": {"__type__": "Vector2", "x": 240, "y": 48}},
                    {"name": "QuitBtn", "type": "Button", "text": {"__type__": "String", "value": "Quit"}, "custom_minimum_size": {"__type__": "Vector2", "x": 240, "y": 48}},
                ],
            }
        ],
        theme_notes="Center the menu stack and keep call-to-action buttons aligned.",
    ),
    "health_bar": UILayoutConfig(
        pattern="health_bar",
        root_name="HealthBar",
        root_type="HBoxContainer",
        children=[
            {"name": "Icon", "type": "TextureRect", "custom_minimum_size": {"__type__": "Vector2", "x": 24, "y": 24}, "stretch_mode": 5},
            {"name": "Bar", "type": "ProgressBar", "custom_minimum_size": {"__type__": "Vector2", "x": 120, "y": 16}, "size_flags_horizontal": 3, "show_percentage": False},
            {"name": "ValueLabel", "type": "Label", "text": {"__type__": "String", "value": "100"}, "custom_minimum_size": {"__type__": "Vector2", "x": 48, "y": 0}},
        ],
        theme_notes="Expose min/max/value in script and keep the bar horizontally expandable.",
    ),
}


def plan_ui_layout(pattern: str) -> UILayoutConfig | None:
    return LAYOUT_PRESETS.get(pattern)


def validate_ui_layout(scene: TscnScene) -> list[str]:
    warnings: list[str] = []
    control_nodes = [node for node in scene.nodes if _is_control_type(node.type)]
    if not control_nodes:
        return warnings

    root_ui = control_nodes[0]
    if root_ui.type == "Control":
        warnings.append(f"Root UI node '{root_ui.name}' is bare Control; prefer a Container subtype.")

    if "theme" not in root_ui.properties and not any(resource.type == "Theme" for resource in scene.ext_resources):
        warnings.append(f"Root UI node '{root_ui.name}' has no Theme resource attached.")

    for node in control_nodes:
        parent = _parent_node(node, scene)
        if parent is not None and _is_container_type(parent.type) and "position" in node.properties:
            warnings.append(f"'{node.name}' uses manual position under Container '{parent.name}'.")

        if node.type == "Button":
            min_size = _vector2_dict(node.property_value("custom_minimum_size", typed=True))
            if 0 < min_size["y"] < 44:
                warnings.append(f"Button '{node.name}' minimum height {int(min_size['y'])}px is below 44px.")

        if node.type == "ScrollContainer":
            for child in [candidate for candidate in scene.nodes if candidate.parent == node.name]:
                flags = child.property_value("size_flags_vertical", 0, typed=True)
                if flags not in {2, 3}:
                    warnings.append(f"ScrollContainer child '{child.name}' should use vertical expand sizing.")

    return warnings

"""Godot-aware scene file tools."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.godot.scene_writer import (
    add_connection,
    add_node,
    remove_node,
    set_node_property,
)
from godot_agent.godot.tscn_validator import validate_and_fix
from godot_agent.tools.base import BaseTool, ToolResult
from godot_agent.tools.file_ops import _validate_path


def _render_tree(scene_text: str) -> str:
    scene = parse_tscn(scene_text)
    if not scene.nodes:
        return "(empty scene)"

    root_name = scene.nodes[0].name
    lines = [root_name]
    for node in scene.nodes[1:]:
        depth = 1 if node.parent in (None, ".") else node.parent.count("/") + 1
        node_type = f" [{node.type}]" if node.type else ""
        lines.append(f"{'  ' * depth}- {node.name}{node_type}")
    return "\n".join(lines)


def _write_scene_with_validation(path: Path, content: str) -> ToolResult | None:
    fixed_text, issues = validate_and_fix(content)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        details = "\n".join(str(issue) for issue in errors)
        return ToolResult(error=f"Scene validation failed before write:\n{details}")
    path.write_text(fixed_text, encoding="utf-8")
    return None


class ReadSceneTool(BaseTool):
    name = "read_scene"
    description = "Read a .tscn file and return a structured scene summary."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")

    class Output(BaseModel):
        tree: str
        nodes: list[dict]
        ext_resources: list[dict]
        connections: list[dict]

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "read_scene only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        scene = parse_tscn(text)
        return ToolResult(
            output=self.Output(
                tree=_render_tree(text),
                nodes=[
                    {
                        "name": node.name,
                        "type": node.type,
                        "parent": node.parent,
                        "properties": node.properties,
                    }
                    for node in scene.nodes
                ],
                ext_resources=[resource.__dict__ for resource in scene.ext_resources],
                connections=[connection.__dict__ for connection in scene.connections],
            )
        )


class SceneTreeTool(BaseTool):
    name = "scene_tree"
    description = "Render the node tree of a .tscn file."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")

    class Output(BaseModel):
        tree: str

    def is_read_only(self) -> bool:
        return True

    def is_destructive(self) -> bool:
        return False

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "scene_tree only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")
        return ToolResult(output=self.Output(tree=_render_tree(path.read_text(encoding="utf-8", errors="replace"))))


class AddSceneNodeTool(BaseTool):
    name = "add_scene_node"
    description = "Add a node to a .tscn scene."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")
        parent: str = Field(description='Parent path, e.g. "." for the root')
        name: str = Field(description="Node name")
        type: str = Field(description="Godot node type, e.g. Button or Area2D")
        properties: dict[str, str] = Field(default_factory=dict, description="Optional property assignments")

    class Output(BaseModel):
        node_added: str

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "add_scene_node only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        updated = add_node(
            path.read_text(encoding="utf-8", errors="replace"),
            parent=input.parent,
            name=input.name,
            type=input.type,
            properties=input.properties or None,
        )
        write_error = _write_scene_with_validation(path, updated)
        if write_error:
            return write_error
        return ToolResult(output=self.Output(node_added=input.name))


class WriteScenePropertyTool(BaseTool):
    name = "write_scene_property"
    description = "Update or add a property on a node inside a .tscn scene."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")
        node_name: str = Field(description="Target node name")
        key: str = Field(description="Property key")
        value: str = Field(description="Serialized Godot property value")

    class Output(BaseModel):
        updated: bool

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "write_scene_property only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        updated = set_node_property(
            path.read_text(encoding="utf-8", errors="replace"),
            node_name=input.node_name,
            key=input.key,
            value=input.value,
        )
        write_error = _write_scene_with_validation(path, updated)
        if write_error:
            return write_error
        return ToolResult(output=self.Output(updated=True))


class AddSceneConnectionTool(BaseTool):
    name = "add_scene_connection"
    description = "Add a [connection] entry to a .tscn file."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")
        signal_name: str = Field(description="Signal name")
        from_node: str = Field(description='Source node path such as "." or "Button"')
        to_node: str = Field(description='Target node path such as "."')
        method: str = Field(description="Method to call on the target")

    class Output(BaseModel):
        connected: bool

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "add_scene_connection only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        updated = add_connection(
            path.read_text(encoding="utf-8", errors="replace"),
            signal_name=input.signal_name,
            from_node=input.from_node,
            to_node=input.to_node,
            method=input.method,
        )
        write_error = _write_scene_with_validation(path, updated)
        if write_error:
            return write_error
        return ToolResult(output=self.Output(connected=True))


class RemoveSceneNodeTool(BaseTool):
    name = "remove_scene_node"
    description = "Remove a node from a .tscn scene."

    class Input(BaseModel):
        path: str = Field(description="Absolute path to the .tscn file")
        node_name: str = Field(description="Node name to remove")

    class Output(BaseModel):
        removed: bool

    def validate_input(self, input: Input) -> str | None:
        if not input.path.endswith(".tscn"):
            return "remove_scene_node only works on .tscn files"
        return None

    async def execute(self, input: Input) -> ToolResult:
        path, err = _validate_path(input.path)
        if err:
            return ToolResult(error=err)
        if not path.exists():
            return ToolResult(error=f"File not found: {input.path}")

        updated = remove_node(
            path.read_text(encoding="utf-8", errors="replace"),
            node_name=input.node_name,
        )
        write_error = _write_scene_with_validation(path, updated)
        if write_error:
            return write_error
        return ToolResult(output=self.Output(removed=True))

from pathlib import Path

import pytest

from godot_agent.tools.file_ops import clear_project_root, set_project_root
from godot_agent.tools.scene_tools import (
    AddSceneConnectionTool,
    AddSceneNodeTool,
    ReadSceneTool,
    RemoveSceneNodeTool,
    SceneTreeTool,
    WriteScenePropertyTool,
)


@pytest.fixture
def scene_project(tmp_path: Path) -> Path:
    set_project_root(tmp_path)
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="SceneTools"\n')
    (tmp_path / "main.tscn").write_text(
        '[gd_scene format=3]\n\n[node name="Root" type="Control"]\n\n[node name="Label" type="Label" parent="."]\ntext = "Hello"\n'
    )
    yield tmp_path
    clear_project_root()


@pytest.mark.asyncio
async def test_read_scene(scene_project: Path):
    tool = ReadSceneTool()
    result = await tool.execute(tool.Input(path=str(scene_project / "main.tscn")))
    assert result.error is None
    assert "Root" in result.output.tree
    assert len(result.output.nodes) == 2


@pytest.mark.asyncio
async def test_mutate_scene_tools(scene_project: Path):
    add_tool = AddSceneNodeTool()
    prop_tool = WriteScenePropertyTool()
    conn_tool = AddSceneConnectionTool()
    tree_tool = SceneTreeTool()
    remove_tool = RemoveSceneNodeTool()
    scene_path = str(scene_project / "main.tscn")

    add_result = await add_tool.execute(
        add_tool.Input(path=scene_path, parent=".", name="Button", type="Button")
    )
    assert add_result.error is None

    prop_result = await prop_tool.execute(
        prop_tool.Input(path=scene_path, node_name="Button", key="text", value='"Play"')
    )
    assert prop_result.error is None

    conn_result = await conn_tool.execute(
        conn_tool.Input(path=scene_path, signal_name="pressed", from_node="Button", to_node=".", method="_on_pressed")
    )
    assert conn_result.error is None

    tree_result = await tree_tool.execute(tree_tool.Input(path=scene_path))
    assert tree_result.error is None
    assert "Button" in tree_result.output.tree

    remove_result = await remove_tool.execute(remove_tool.Input(path=scene_path, node_name="Button"))
    assert remove_result.error is None
    assert "Button" not in (scene_project / "main.tscn").read_text()

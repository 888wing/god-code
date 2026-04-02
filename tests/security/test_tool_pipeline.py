from pathlib import Path

import pytest

from godot_agent.runtime.quality_gate import ChangeSet
from godot_agent.security.policies import ToolExecutionContext
from godot_agent.security.tool_pipeline import ToolExecutionPipeline
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool, clear_project_root, set_project_root
from godot_agent.tools.scene_tools import AddSceneNodeTool
from godot_agent.tools.script_tools import EditScriptTool


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    (tmp_path / "player.gd").write_text("extends Node\nvar hp: int = 10\n")
    (tmp_path / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


@pytest.mark.asyncio
async def test_pipeline_blocks_edit_without_prior_read(project_root: Path) -> None:
    tool = EditScriptTool()
    pipeline = ToolExecutionPipeline.create_default()
    context = ToolExecutionContext(mode="apply", project_root=project_root, changeset=ChangeSet())
    context.refresh_protected_paths()

    result = await pipeline.execute(
        tool,
        {
            "path": str(project_root / "player.gd"),
            "old_string": "var hp: int = 10",
            "new_string": "var hp: int = 20",
        },
        context,
    )

    assert result.error is not None
    assert "Must read" in result.error


@pytest.mark.asyncio
async def test_pipeline_updates_changeset_after_read(project_root: Path) -> None:
    tool = ReadFileTool()
    pipeline = ToolExecutionPipeline.create_default()
    changeset = ChangeSet()
    context = ToolExecutionContext(mode="apply", project_root=project_root, changeset=changeset)
    context.refresh_protected_paths()

    result = await pipeline.execute(
        tool,
        {"path": str(project_root / "player.gd")},
        context,
    )

    assert result.error is None
    assert str((project_root / "player.gd").resolve()) in changeset.read_files


@pytest.mark.asyncio
async def test_pipeline_allows_edit_after_read(project_root: Path) -> None:
    read_tool = ReadFileTool()
    edit_tool = EditScriptTool()
    pipeline = ToolExecutionPipeline.create_default()
    changeset = ChangeSet()
    context = ToolExecutionContext(mode="apply", project_root=project_root, changeset=changeset)
    context.refresh_protected_paths()

    await pipeline.execute(read_tool, {"path": str(project_root / "player.gd")}, context)
    result = await pipeline.execute(
        edit_tool,
        {
            "path": str(project_root / "player.gd"),
            "old_string": "var hp: int = 10",
            "new_string": "var hp: int = 20",
        },
        context,
    )

    assert result.error is None
    assert "var hp: int = 20" in (project_root / "player.gd").read_text()


@pytest.mark.asyncio
async def test_pipeline_blocks_raw_scene_mutation(project_root: Path) -> None:
    tool = WriteFileTool()
    pipeline = ToolExecutionPipeline.create_default()
    context = ToolExecutionContext(mode="apply", project_root=project_root, changeset=ChangeSet())
    context.refresh_protected_paths()

    result = await pipeline.execute(
        tool,
        {"path": str(project_root / "main.tscn"), "content": "broken"},
        context,
    )

    assert result.error is not None
    assert "structured scene tools" in result.error


@pytest.mark.asyncio
async def test_pipeline_allows_structured_scene_edit_on_unprotected_scene(project_root: Path) -> None:
    scene_path = project_root / "side_scene.tscn"
    scene_path.write_text('[gd_scene format=3]\n\n[node name="Side" type="Node2D"]\n')
    tool = AddSceneNodeTool()
    pipeline = ToolExecutionPipeline.create_default()
    changeset = ChangeSet()
    changeset.mark_read(str(scene_path))
    context = ToolExecutionContext(mode="apply", project_root=project_root, changeset=changeset)
    context.refresh_protected_paths()

    result = await pipeline.execute(
        tool,
        {"path": str(scene_path), "parent": ".", "name": "Hud", "type": "CanvasLayer"},
        context,
    )

    assert result.error is None
    assert "Hud" in scene_path.read_text()

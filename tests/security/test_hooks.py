from pathlib import Path

import pytest

from godot_agent.runtime.quality_gate import ChangeSet
from godot_agent.security.hooks import (
    BlockRawSceneMutationHook,
    ProtectedPathHook,
    RequireReadBeforeWriteHook,
)
from godot_agent.security.policies import ToolExecutionContext
from godot_agent.security.protected_paths import discover_protected_paths
from godot_agent.tools.file_ops import EditFileTool, WriteFileTool, clear_project_root, set_project_root
from godot_agent.tools.scene_tools import AddSceneNodeTool
from godot_agent.tools.script_tools import EditScriptTool


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nrun/main_scene="res://scenes/main.tscn"\n'
    )
    (tmp_path / "player.gd").write_text("extends Node\nvar hp: int = 10\n")
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "main.tscn").write_text(
        '[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n'
    )
    set_project_root(tmp_path)
    yield tmp_path
    clear_project_root()


@pytest.mark.asyncio
async def test_require_read_before_write_blocks_unread_script(project_root: Path) -> None:
    tool = EditScriptTool()
    path = project_root / "player.gd"
    context = ToolExecutionContext(mode="apply", changeset=ChangeSet())
    hook = RequireReadBeforeWriteHook()

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(path), old_string="var hp: int = 10", new_string="var hp: int = 20"),
        context,
    )

    assert result is not None
    assert result.permission_behavior == "deny"


@pytest.mark.asyncio
async def test_require_read_before_write_allows_after_read(project_root: Path) -> None:
    tool = EditScriptTool()
    path = project_root / "player.gd"
    changeset = ChangeSet()
    changeset.mark_read(str(path))
    context = ToolExecutionContext(mode="apply", changeset=changeset)
    hook = RequireReadBeforeWriteHook()

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(path), old_string="var hp: int = 10", new_string="var hp: int = 20"),
        context,
    )

    assert result is None


@pytest.mark.asyncio
async def test_block_raw_scene_mutation_denies_edit_file(project_root: Path) -> None:
    tool = EditFileTool()
    hook = BlockRawSceneMutationHook()
    scene_path = project_root / "scenes" / "main.tscn"

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(scene_path), old_string="Main", new_string="Root"),
        ToolExecutionContext(mode="apply"),
    )

    assert result is not None
    assert result.permission_behavior == "deny"


@pytest.mark.asyncio
async def test_protected_path_hook_flags_main_scene(project_root: Path) -> None:
    tool = AddSceneNodeTool()
    context = ToolExecutionContext(
        mode="apply",
        project_root=project_root,
        protected_paths=discover_protected_paths(project_root),
    )
    hook = ProtectedPathHook()
    scene_path = project_root / "scenes" / "main.tscn"

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(scene_path), parent=".", name="Hud", type="CanvasLayer"),
        context,
    )

    assert result is not None
    assert result.permission_behavior == "ask"


@pytest.mark.asyncio
async def test_protected_path_hook_asks_for_project_settings(project_root: Path) -> None:
    tool = WriteFileTool()
    context = ToolExecutionContext(
        mode="apply",
        project_root=project_root,
        protected_paths=discover_protected_paths(project_root),
    )
    hook = ProtectedPathHook()

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(project_root / "project.godot"), content="changed"),
        context,
    )

    assert result is not None
    assert result.permission_behavior == "ask"


@pytest.mark.asyncio
async def test_read_before_write_allows_in_auto_execute_mode(project_root: Path) -> None:
    tool = EditScriptTool()
    path = project_root / "player.gd"
    changeset = ChangeSet()
    # NOT read yet — changeset.read_files is empty
    context = ToolExecutionContext(mode="auto_execute", changeset=changeset)
    hook = RequireReadBeforeWriteHook()

    result = await hook.pre_execute(
        tool,
        tool.Input(path=str(path), old_string="var hp: int = 10", new_string="var hp: int = 20"),
        context,
    )

    # In auto_execute mode, should NOT block even though file was not read
    assert result is None

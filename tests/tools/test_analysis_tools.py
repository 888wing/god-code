from pathlib import Path

import pytest

from godot_agent.tools.analysis_tools import (
    CheckConsistencyTool,
    ProjectDependencyGraphTool,
    ValidateProjectTool,
)
from godot_agent.tools.file_ops import clear_project_root, set_project_root


@pytest.fixture
def analysis_project(tmp_path: Path) -> Path:
    set_project_root(tmp_path)
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="AnalysisTools"\nrun/main_scene="res://main.tscn"\n'
    )
    (tmp_path / "player.gd").write_text('extends Node\nvar scene = preload("res://missing.tscn")\n')
    (tmp_path / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
    yield tmp_path
    clear_project_root()


@pytest.mark.asyncio
async def test_validate_project_tool(analysis_project: Path):
    tool = ValidateProjectTool()
    result = await tool.execute(tool.Input(project_path=str(analysis_project), godot_path="true"))
    assert result.error is None
    assert result.output.success is True


@pytest.mark.asyncio
async def test_check_consistency_tool(analysis_project: Path):
    tool = CheckConsistencyTool()
    result = await tool.execute(tool.Input(project_path=str(analysis_project)))
    assert result.error is None
    assert result.output.issue_count == 1
    assert "missing.tscn" in result.output.report


@pytest.mark.asyncio
async def test_dependency_graph_tool(analysis_project: Path):
    tool = ProjectDependencyGraphTool()
    result = await tool.execute(tool.Input(project_path=str(analysis_project)))
    assert result.error is None
    assert "res://main.tscn" in result.output.summary

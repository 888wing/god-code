from pathlib import Path

import pytest

from godot_agent.tools.file_ops import clear_project_root, set_project_root
from godot_agent.tools.script_tools import EditScriptTool, LintScriptTool, ReadScriptTool


@pytest.fixture
def script_project(tmp_path: Path) -> Path:
    set_project_root(tmp_path)
    (tmp_path / "player.gd").write_text(
        "extends Node\n\nvar hp = 10\n\nfunc DoThing():\n\tpass\n"
    )
    yield tmp_path
    clear_project_root()


@pytest.mark.asyncio
async def test_read_script(script_project: Path):
    tool = ReadScriptTool()
    result = await tool.execute(tool.Input(path=str(script_project / "player.gd")))
    assert result.error is None
    assert "DoThing" in result.output.content


@pytest.mark.asyncio
async def test_edit_script(script_project: Path):
    tool = EditScriptTool()
    result = await tool.execute(
        tool.Input(
            path=str(script_project / "player.gd"),
            old_string="var hp = 10",
            new_string="var hp: int = 20",
        )
    )
    assert result.error is None
    assert "var hp: int = 20" in (script_project / "player.gd").read_text()


@pytest.mark.asyncio
async def test_lint_script(script_project: Path):
    tool = LintScriptTool()
    result = await tool.execute(tool.Input(path=str(script_project / "player.gd")))
    assert result.error is None
    assert result.output.issue_count > 0
    assert "func-naming" in result.output.report or "type-annotation" in result.output.report

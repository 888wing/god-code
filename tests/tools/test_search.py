import pytest
from pathlib import Path
from godot_agent.tools.search import GrepTool, GlobTool


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "player.gd").write_text(
        "extends CharacterBody2D\nvar speed = 100\nfunc _ready():\n\tpass\n"
    )
    (tmp_path / "src" / "enemy.gd").write_text(
        "extends CharacterBody2D\nvar speed = 50\nfunc die():\n\tqueue_free()\n"
    )
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "main.tscn").write_text(
        '[gd_scene format=3]\n[node name="Main" type="Node2D"]\n'
    )
    return tmp_path


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_finds_matches(self, project_dir):
        tool = GrepTool()
        result = await tool.execute(
            tool.Input(pattern="speed", path=str(project_dir))
        )
        assert result.error is None
        assert len(result.output.matches) == 2

    @pytest.mark.asyncio
    async def test_grep_with_glob_filter(self, project_dir):
        tool = GrepTool()
        result = await tool.execute(
            tool.Input(
                pattern="CharacterBody2D", path=str(project_dir), glob="*.gd"
            )
        )
        assert result.error is None
        assert len(result.output.matches) == 2

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, project_dir):
        tool = GrepTool()
        result = await tool.execute(
            tool.Input(pattern="nonexistent_xyz", path=str(project_dir))
        )
        assert result.error is None
        assert len(result.output.matches) == 0


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_gd_files(self, project_dir):
        tool = GlobTool()
        result = await tool.execute(
            tool.Input(pattern="**/*.gd", path=str(project_dir))
        )
        assert result.error is None
        assert len(result.output.files) == 2

    @pytest.mark.asyncio
    async def test_glob_tscn_files(self, project_dir):
        tool = GlobTool()
        result = await tool.execute(
            tool.Input(pattern="**/*.tscn", path=str(project_dir))
        )
        assert result.error is None
        assert len(result.output.files) == 1

import pytest
from godot_agent.tools.list_dir import ListDirTool


class TestListDirTool:
    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        (tmp_path / "script.gd").write_text("extends Node\n")
        (tmp_path / "scene.tscn").write_text("[gd_scene]\n")
        (tmp_path / "subdir").mkdir()
        tool = ListDirTool()
        result = await tool.execute(tool.Input(path=str(tmp_path)))
        assert result.error is None
        assert result.output.total == 3
        names = [e["name"] for e in result.output.entries]
        assert "script.gd" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_recursive(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "player.gd").write_text("extends Node\n")
        tool = ListDirTool()
        result = await tool.execute(tool.Input(path=str(tmp_path), recursive=True))
        assert result.error is None
        names = [e["name"] for e in result.output.entries]
        assert any("player.gd" in n for n in names)

    @pytest.mark.asyncio
    async def test_nonexistent_path(self):
        tool = ListDirTool()
        result = await tool.execute(tool.Input(path="/nonexistent/path"))
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_pattern_filter(self, tmp_path):
        (tmp_path / "a.gd").write_text("x")
        (tmp_path / "b.tscn").write_text("y")
        tool = ListDirTool()
        result = await tool.execute(tool.Input(path=str(tmp_path), pattern="*.gd"))
        assert result.output.total == 1
        assert result.output.entries[0]["name"] == "a.gd"

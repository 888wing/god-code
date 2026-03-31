import pytest
from pathlib import Path
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool, EditFileTool


class TestReadFileTool:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.gd"
        f.write_text("extends Node\n\nfunc _ready():\n\tpass\n")
        tool = ReadFileTool()
        result = await tool.execute(tool.Input(path=str(f)))
        assert result.error is None
        assert "extends Node" in result.output.content
        assert result.output.line_count == 4

    @pytest.mark.asyncio
    async def test_read_with_offset_limit(self, tmp_path):
        f = tmp_path / "test.gd"
        f.write_text("\n".join(f"line {i}" for i in range(20)))
        tool = ReadFileTool()
        result = await tool.execute(tool.Input(path=str(f), offset=5, limit=3))
        assert "line 5" in result.output.content
        assert result.output.line_count == 3

    @pytest.mark.asyncio
    async def test_read_missing_file(self, tmp_path):
        tool = ReadFileTool()
        result = await tool.execute(tool.Input(path=str(tmp_path / "nope.gd")))
        assert result.error is not None


class TestWriteFileTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path):
        f = tmp_path / "new.gd"
        tool = WriteFileTool()
        result = await tool.execute(tool.Input(path=str(f), content="extends Node\n"))
        assert result.error is None
        assert f.read_text() == "extends Node\n"

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "script.gd"
        tool = WriteFileTool()
        result = await tool.execute(tool.Input(path=str(f), content="pass\n"))
        assert result.error is None
        assert f.exists()


class TestEditFileTool:
    @pytest.mark.asyncio
    async def test_replace_string(self, tmp_path):
        f = tmp_path / "test.gd"
        f.write_text("var hp = 100\nvar atk = 10\n")
        tool = EditFileTool()
        result = await tool.execute(
            tool.Input(
                path=str(f),
                old_string="var hp = 100",
                new_string="var hp = 200",
            )
        )
        assert result.error is None
        assert "var hp = 200" in f.read_text()

    @pytest.mark.asyncio
    async def test_replace_not_found(self, tmp_path):
        f = tmp_path / "test.gd"
        f.write_text("var hp = 100\n")
        tool = EditFileTool()
        result = await tool.execute(
            tool.Input(
                path=str(f),
                old_string="var mp = 100",
                new_string="var mp = 200",
            )
        )
        assert result.error is not None

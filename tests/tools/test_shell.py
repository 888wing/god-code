import pytest
from godot_agent.tools.shell import RunShellTool


class TestRunShellTool:
    @pytest.mark.asyncio
    async def test_echo_command(self):
        tool = RunShellTool()
        result = await tool.execute(tool.Input(command="echo hello"))
        assert result.error is None
        assert "hello" in result.output.stdout
        assert result.output.exit_code == 0

    @pytest.mark.asyncio
    async def test_failing_command(self):
        tool = RunShellTool()
        result = await tool.execute(tool.Input(command="false"))
        assert result.error is None
        assert result.output.exit_code != 0

    @pytest.mark.asyncio
    async def test_cwd(self, tmp_path):
        (tmp_path / "test.txt").write_text("content")
        tool = RunShellTool()
        result = await tool.execute(tool.Input(command="ls test.txt", cwd=str(tmp_path)))
        assert result.error is None
        assert "test.txt" in result.output.stdout

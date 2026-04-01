import pytest
import subprocess
from godot_agent.tools.git import GitTool


class TestGitTool:
    @pytest.mark.asyncio
    async def test_git_status(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "test.gd").write_text("extends Node\n")
        tool = GitTool()
        result = await tool.execute(tool.Input(command="status", cwd=str(tmp_path)))
        assert result.error is None
        assert "test.gd" in result.output.stdout

    @pytest.mark.asyncio
    async def test_git_log(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "test.gd").write_text("extends Node\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        tool = GitTool()
        result = await tool.execute(tool.Input(command="log --oneline -1", cwd=str(tmp_path)))
        assert result.error is None
        assert "init" in result.output.stdout

    @pytest.mark.asyncio
    async def test_git_diff(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "test.gd").write_text("extends Node\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "test.gd").write_text("extends Node2D\n")
        tool = GitTool()
        result = await tool.execute(tool.Input(command="diff", cwd=str(tmp_path)))
        assert result.error is None
        assert "Node2D" in result.output.stdout

    @pytest.mark.asyncio
    async def test_git_invalid_command(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        tool = GitTool()
        result = await tool.execute(tool.Input(command="not-a-real-command", cwd=str(tmp_path)))
        assert result.error is None
        assert result.output.exit_code != 0

    @pytest.mark.asyncio
    async def test_git_invalid_cwd(self):
        tool = GitTool()
        result = await tool.execute(tool.Input(command="status", cwd="/nonexistent/path"))
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_exit_code_on_success(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        tool = GitTool()
        result = await tool.execute(tool.Input(command="status", cwd=str(tmp_path)))
        assert result.output.exit_code == 0

    def test_tool_schema(self):
        tool = GitTool()
        schema = tool.to_openai_schema()
        assert schema["function"]["name"] == "git"
        assert "parameters" in schema["function"]

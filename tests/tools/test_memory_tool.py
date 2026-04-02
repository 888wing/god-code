from godot_agent.tools.file_ops import clear_project_root, set_project_root
from godot_agent.tools.memory_tool import ReadDesignMemoryTool, UpdateDesignMemoryTool


def test_update_and_read_design_memory_tool(tmp_path):
    set_project_root(tmp_path)
    try:
        update_tool = UpdateDesignMemoryTool()
        read_tool = ReadDesignMemoryTool()

        result = update_tool.validate_input(update_tool.Input(project_path=str(tmp_path), section="pillars", items=["Readable combat"]))
        assert result is None

        import asyncio
        asyncio.run(update_tool.execute(update_tool.Input(project_path=str(tmp_path), section="pillars", items=["Readable combat"])))
        read_result = asyncio.run(read_tool.execute(read_tool.Input(project_path=str(tmp_path))))
        assert "Readable combat" in read_result.output.report
    finally:
        clear_project_root()

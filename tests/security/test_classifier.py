from pathlib import Path

from godot_agent.security.classifier import OperationRisk, classify_operation
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool
from godot_agent.tools.git import GitTool
from godot_agent.tools.scene_tools import AddSceneNodeTool
from godot_agent.tools.shell import RunShellTool


def test_read_file_is_safe() -> None:
    tool = ReadFileTool()
    risk = classify_operation(tool, tool.Input(path="/tmp/example.gd"))
    assert risk is OperationRisk.SAFE


def test_write_project_settings_is_high_risk() -> None:
    tool = WriteFileTool()
    risk = classify_operation(tool, tool.Input(path="/tmp/project.godot", content=""))
    assert risk is OperationRisk.HIGH


def test_scene_mutation_is_medium_risk(tmp_path: Path) -> None:
    scene = tmp_path / "main.tscn"
    scene.write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
    tool = AddSceneNodeTool()
    risk = classify_operation(
        tool,
        tool.Input(path=str(scene), parent=".", name="Hud", type="CanvasLayer"),
    )
    assert risk is OperationRisk.MEDIUM


def test_shell_rm_rf_is_critical() -> None:
    tool = RunShellTool()
    risk = classify_operation(tool, tool.Input(command="rm -rf ./build"))
    assert risk is OperationRisk.CRITICAL


def test_git_status_is_low_risk() -> None:
    tool = GitTool()
    risk = classify_operation(tool, tool.Input(command="status"))
    assert risk is OperationRisk.LOW

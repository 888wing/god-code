from pathlib import Path

from godot_agent.runtime.quality_gate import ChangeSet
from godot_agent.security.classifier import OperationRisk
from godot_agent.security.hooks import HookResult
from godot_agent.security.policies import PermissionPolicyFramework, ToolExecutionContext
from godot_agent.security.protected_paths import discover_protected_paths
from godot_agent.tools.file_ops import ReadFileTool, WriteFileTool, clear_project_root, set_project_root


def test_plan_mode_blocks_mutation(tmp_path: Path) -> None:
    set_project_root(tmp_path)
    try:
        tool = WriteFileTool()
        context = ToolExecutionContext(mode="plan", changeset=ChangeSet())
        decision = PermissionPolicyFramework().evaluate(
            tool=tool,
            parsed_input=tool.Input(path=str(tmp_path / "file.gd"), content=""),
            context=context,
            risk=OperationRisk.MEDIUM,
            hook_result=HookResult(),
        )
        assert not decision.allowed
        assert "plan mode" in decision.reason
    finally:
        clear_project_root()


def test_allowed_tools_filter_blocks_missing_tool(tmp_path: Path) -> None:
    set_project_root(tmp_path)
    try:
        tool = ReadFileTool()
        context = ToolExecutionContext(mode="apply", allowed_tools={"grep"})
        decision = PermissionPolicyFramework().evaluate(
            tool=tool,
            parsed_input=tool.Input(path=str(tmp_path / "file.gd")),
            context=context,
            risk=OperationRisk.SAFE,
            hook_result=HookResult(),
        )
        assert not decision.allowed
        assert "not allowed" in decision.reason
    finally:
        clear_project_root()


def test_critical_risk_is_denied(tmp_path: Path) -> None:
    set_project_root(tmp_path)
    try:
        tool = WriteFileTool()
        context = ToolExecutionContext(mode="apply")
        decision = PermissionPolicyFramework().evaluate(
            tool=tool,
            parsed_input=tool.Input(path=str(tmp_path / "danger.txt"), content=""),
            context=context,
            risk=OperationRisk.CRITICAL,
            hook_result=HookResult(),
        )
        assert not decision.allowed
        assert "CRITICAL" in decision.reason
    finally:
        clear_project_root()


def test_protected_raw_mutation_is_denied(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    set_project_root(tmp_path)
    try:
        tool = WriteFileTool()
        context = ToolExecutionContext(
            mode="apply",
            project_root=tmp_path,
            protected_paths=discover_protected_paths(tmp_path),
        )
        decision = PermissionPolicyFramework().evaluate(
            tool=tool,
            parsed_input=tool.Input(path=str(tmp_path / "project.godot"), content="changed"),
            context=context,
            risk=OperationRisk.HIGH,
            hook_result=HookResult(),
        )
        assert not decision.allowed
        assert "protected" in decision.reason
    finally:
        clear_project_root()


def test_hook_ask_requires_approval(tmp_path: Path) -> None:
    set_project_root(tmp_path)
    try:
        tool = WriteFileTool()
        context = ToolExecutionContext(mode="apply")
        decision = PermissionPolicyFramework().evaluate(
            tool=tool,
            parsed_input=tool.Input(path=str(tmp_path / "notes.txt"), content="hello"),
            context=context,
            risk=OperationRisk.MEDIUM,
            hook_result=HookResult(permission_behavior="ask", blocking_error="approval needed"),
        )
        assert not decision.allowed
        assert decision.requires_approval
        assert decision.reason == "approval needed"
    finally:
        clear_project_root()

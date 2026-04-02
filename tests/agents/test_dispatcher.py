from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.llm.client import ChatResponse, LLMClient, Message, TokenUsage
from godot_agent.prompts.assembler import PromptContext
from godot_agent.tools.file_ops import ReadFileTool
from godot_agent.tools.registry import ToolRegistry


def _resp(content: str) -> ChatResponse:
    return ChatResponse(message=Message.assistant(content=content), usage=TokenUsage())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Test"\n')
    return tmp_path


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    return registry


class TestAgentDispatcher:
    @pytest.mark.asyncio
    async def test_planner_runs_with_role_scoped_engine(self, project_root: Path) -> None:
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(return_value=_resp("Plan: inspect scripts, patch one file, validate."))
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )

        result = await dispatcher.run_planner("Fix the player controller")

        assert result.role == "planner"
        assert "Plan:" in result.content
        assert dispatcher.resolve_allowed_tools("planner") == {"read_file"}

    @pytest.mark.asyncio
    async def test_worker_inherits_apply_tooling(self, project_root: Path) -> None:
        client = AsyncMock(spec=LLMClient)
        client.chat = AsyncMock(return_value=_resp("Implemented the requested fix."))
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )

        result = await dispatcher.run_worker("Create a save file loader", plan="1. Inspect project\n2. Add loader")

        assert result.role == "worker"
        assert result.verdict == "PASS"
        assert "Implemented" in result.content
        assert dispatcher.resolve_allowed_tools("worker") == {"read_file", "write_file"}

    @pytest.mark.asyncio
    async def test_reviewer_wraps_deterministic_review(self, project_root: Path, monkeypatch) -> None:
        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
        )

        async def fake_review_changes(*, project_root, changed_files, godot_path, quality_report):
            from godot_agent.runtime.reviewer import ReviewCheck, ReviewReport

            return ReviewReport(
                checks=[
                    ReviewCheck(
                        description="Run validation",
                        command=f"{godot_path} --headless --quit",
                        observed_output="No issues found.",
                        status="PASS",
                    )
                ]
            )

        monkeypatch.setattr("godot_agent.agents.dispatcher.review_changes", fake_review_changes)

        result = await dispatcher.run_reviewer(changed_files={str(project_root / "player.gd")})

        assert result.role == "reviewer"
        assert result.verdict == "PASS"
        assert "Run validation" in result.content

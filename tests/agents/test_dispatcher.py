from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from godot_agent.agents.configs import AGENT_CONFIGS
from godot_agent.agents.dispatcher import AgentDispatcher


class TestPlannerPrompt:
    """Regression v1.0.0/F1+F2: planner prompt rewrite to stop the
    'I am in PLAN mode' hallucination and enforce a structured format.
    """

    def test_planner_prompt_does_not_say_plan_mode(self):
        prompt = AGENT_CONFIGS["planner"].prompt.lower()
        # The exact phrasing the LLM was producing
        assert "plan mode" not in prompt or "not.*plan mode" in prompt or "plan mode is" in prompt, (
            "planner prompt must not casually say 'plan mode'; "
            "it must explicitly disavow that interpretation"
        )

    def test_planner_prompt_identifies_role_correctly(self):
        prompt = AGENT_CONFIGS["planner"].prompt.lower()
        assert "planner" in prompt, "planner prompt must identify itself as planner"
        assert "sub-agent" in prompt or "subagent" in prompt, (
            "planner prompt should clarify it's a sub-agent inside god-code"
        )

    def test_planner_prompt_enforces_structured_format(self):
        prompt = AGENT_CONFIGS["planner"].prompt
        for required_section in ["Goal", "Scope", "Steps", "Risks", "Validation"]:
            assert required_section in prompt, (
                f"planner prompt must require {required_section!r} section"
            )
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

    def test_sub_engine_defaults_without_stream_wiring(self, project_root: Path) -> None:
        """A dispatcher with no stream wiring produces sub-engines with streaming off.

        Documents the baseline so the next test clearly shows the new wiring propagates.
        """
        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )
        sub_engine = dispatcher._build_engine(AGENT_CONFIGS["planner"], user_hint="anything")
        assert sub_engine.use_streaming is False
        assert sub_engine.on_stream_start is None
        assert sub_engine.on_stream_chunk is None
        assert sub_engine.on_stream_end is None
        assert sub_engine.on_event is None

    def test_sub_engine_inherits_stream_wiring_from_dispatcher(self, project_root: Path) -> None:
        """Regression: when the dispatcher has stream callbacks set (by the CLI),
        sub-engines created for planner/worker/reviewer passes MUST inherit them,
        so the planner pass streams text to the TUI instead of blocking silently.

        Before v0.9.2, dispatcher._build_engine created fresh engines without ever
        wiring on_stream_*, leaving the user with a stuck spinner during planner
        passes (especially painful with reasoning_effort=high on gpt-5.4, where
        the planner call could take 60-120s with zero visible feedback).
        """
        stream_starts: list[int] = []
        stream_chunks: list[str] = []
        stream_ends: list[bool] = []
        events_seen: list[str] = []

        def on_start() -> None:
            stream_starts.append(1)

        def on_chunk(text: str) -> None:
            stream_chunks.append(text)

        def on_end(finalize: bool) -> None:
            stream_ends.append(finalize)

        def on_event(event) -> None:
            events_seen.append(event.kind)

        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
            base_allowed_tools={"read_file", "write_file"},
        )
        dispatcher.use_streaming = True
        dispatcher.on_stream_start = on_start
        dispatcher.on_stream_chunk = on_chunk
        dispatcher.on_stream_end = on_end
        dispatcher.on_event = on_event

        sub_engine = dispatcher._build_engine(AGENT_CONFIGS["planner"], user_hint="anything")
        assert sub_engine.use_streaming is True
        assert sub_engine.on_stream_start is on_start
        assert sub_engine.on_stream_chunk is on_chunk
        assert sub_engine.on_stream_end is on_end
        assert sub_engine.on_event is on_event

    @pytest.mark.asyncio
    async def test_reviewer_wraps_deterministic_review(self, project_root: Path, monkeypatch) -> None:
        client = AsyncMock(spec=LLMClient)
        dispatcher = AgentDispatcher(
            client=client,
            registry=_registry(),
            prompt_context=PromptContext(project_root=project_root, mode="apply"),
            project_path=str(project_root),
        )

        async def fake_review_changes(*, project_root, changed_files, godot_path, quality_report, runtime_snapshot=None):
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


class TestExtractWorkerPlan:
    """Regression v1.0.1/T3: the plan injected into worker/main history
    must be trimmed to just Goal + Steps. Risks and Validation are
    user-facing context shown in the TUI but not needed by the worker
    sub-agent for execution, so injecting them wastes tokens on every
    subsequent LLM call.
    """

    def test_extract_keeps_goal_and_steps(self):
        from godot_agent.agents.dispatcher import extract_worker_plan
        full_plan = (
            "## Plan\n\n"
            "**Goal**: Add HP bar to player scene\n\n"
            "**Scope**: 2 files | 4 steps | risk: low\n\n"
            "**Steps**:\n"
            "1. read `res://scenes/player.tscn`\n"
            "2. add ProgressBar node for HP\n"
            "3. bind HP to stats via signal\n"
            "4. validate scene\n\n"
            "**Risks**: UI might overlap with existing HUD\n\n"
            "**Validation**: scene validates, HP changes update bar\n"
        )
        reduced = extract_worker_plan(full_plan)
        # Goal and Steps must remain
        assert "Add HP bar to player scene" in reduced
        assert "ProgressBar" in reduced
        assert "bind HP to stats" in reduced
        # Risks and Validation must be gone
        assert "UI might overlap" not in reduced
        assert "scene validates, HP changes" not in reduced
        # Reduction must actually reduce the token count
        assert len(reduced) < len(full_plan)

    def test_extract_handles_missing_risks_section(self):
        """If planner omits the Risks section entirely, the extract still
        returns Goal+Steps without crashing."""
        from godot_agent.agents.dispatcher import extract_worker_plan
        plan = (
            "## Plan\n\n"
            "**Goal**: fix null ref in enemy.gd\n\n"
            "**Steps**:\n"
            "1. find the null deref\n"
            "2. add guard\n"
        )
        reduced = extract_worker_plan(plan)
        assert "fix null ref" in reduced
        assert "add guard" in reduced

    def test_extract_falls_back_on_malformed_plan(self):
        """If the LLM produces non-standard markdown, extract_worker_plan
        must fall back to the full text (defensive — better to keep the
        context than lose the plan entirely)."""
        from godot_agent.agents.dispatcher import extract_worker_plan
        malformed = "Just do the thing. No structure, no headers."
        reduced = extract_worker_plan(malformed)
        assert reduced == malformed

    def test_extract_empty_input_returns_empty(self):
        from godot_agent.agents.dispatcher import extract_worker_plan
        assert extract_worker_plan("") == ""

    def test_extract_scope_section_is_also_dropped(self):
        """Scope is meta-information about the plan size — worker doesn't
        need it either. Only Goal + Steps are actionable."""
        from godot_agent.agents.dispatcher import extract_worker_plan
        plan = (
            "## Plan\n\n"
            "**Goal**: refactor combat loop\n\n"
            "**Scope**: 3 files | 5 steps | risk: medium\n\n"
            "**Steps**:\n"
            "1. extract helper\n"
            "2. rewire caller\n\n"
            "**Risks**: None identified\n\n"
            "**Validation**: tests pass\n"
        )
        reduced = extract_worker_plan(plan)
        assert "refactor combat loop" in reduced
        assert "extract helper" in reduced
        assert "3 files | 5 steps" not in reduced
        assert "None identified" not in reduced
        assert "tests pass" not in reduced

    def test_extract_reduces_token_count_by_at_least_20_percent(self):
        """Regression gate: for a representative well-formed plan, the
        reduction should be at least 20%. Catches the case where extract
        accidentally becomes a no-op."""
        from godot_agent.agents.dispatcher import extract_worker_plan
        plan = (
            "## Plan\n\n"
            "**Goal**: implement boss fight state machine with 4 phases\n\n"
            "**Scope**: 6 files | 12 steps | risk: high\n\n"
            "**Steps**:\n"
            "1. create BossState base class in res://src/combat/boss_state.gd\n"
            "2. implement IdlePhase with perception checks\n"
            "3. implement AttackPhase with telegraph animation\n"
            "4. implement EnragePhase triggered below 30% HP\n"
            "5. implement DefeatedPhase with death animation\n"
            "6. wire state transitions via signals\n"
            "7. add BossStateMachine coordinator\n"
            "8. integrate with existing boss.gd controller\n"
            "9. add GUT tests for each phase\n"
            "10. run validation\n"
            "11. screenshot test in scene\n"
            "12. performance profiling\n\n"
            "**Risks**: state transition races, animation timing desyncs, "
            "GUT test flakiness under Godot 4.4 headless mode, potential "
            "frame drops during Enrage→Defeated transition with particles\n\n"
            "**Validation**: all GUT tests pass, visual regression passes "
            "against baseline, no frame drops > 16ms during transitions, "
            "boss defeat sequence completes without residual state\n"
        )
        reduced = extract_worker_plan(plan)
        reduction_ratio = 1 - (len(reduced) / len(plan))
        assert reduction_ratio >= 0.20, (
            f"expected >= 20% reduction, got {reduction_ratio:.1%} "
            f"(full: {len(plan)} chars, reduced: {len(reduced)} chars)"
        )


class TestPlannerInjectionReduced:
    """Regression v1.0.1/T3: after _maybe_run_planner runs, the message
    appended to engine.messages must contain only Goal+Steps, not the
    full planner output with Risks+Validation."""

    @pytest.mark.asyncio
    async def test_planner_injection_contains_only_goal_and_steps(self):
        from unittest.mock import AsyncMock
        from godot_agent.agents.results import AgentTaskResult
        from godot_agent.llm.client import ChatResponse, LLMClient, Message, TokenUsage
        from godot_agent.runtime.engine import ConversationEngine
        from godot_agent.tools.registry import ToolRegistry

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.chat = AsyncMock(
            return_value=ChatResponse(
                message=Message.assistant(content="done"),
                usage=TokenUsage(),
            )
        )
        full_plan = (
            "## Plan\n\n"
            "**Goal**: implement HP bar\n\n"
            "**Scope**: 2 files | 4 steps | risk: low\n\n"
            "**Steps**:\n1. read player.tscn\n2. add ProgressBar\n\n"
            "**Risks**: may overlap HUD\n\n"
            "**Validation**: scene validates\n"
        )

        class MockDispatcher:
            async def run_planner(self, task):
                return AgentTaskResult(role="planner", content=full_plan)

        engine = ConversationEngine(
            client=mock_client,
            registry=ToolRegistry(),
            system_prompt="t",
            mode="apply",
            dispatcher=MockDispatcher(),
        )
        engine.planner_lazy = False  # ensure planner runs

        await engine._maybe_run_planner("implement HP bar in player.tscn")

        planner_msgs = [
            m for m in engine.messages
            if isinstance(m.content, str) and "[SYSTEM] Planner pass" in m.content
        ]
        assert len(planner_msgs) == 1
        injected = planner_msgs[0].content
        # Goal + Steps present
        assert "implement HP bar" in injected
        assert "ProgressBar" in injected
        # Risks + Validation NOT present (they were in the full plan)
        assert "may overlap HUD" not in injected
        assert "scene validates" not in injected

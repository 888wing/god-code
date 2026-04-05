"""Synchronous multi-agent dispatcher."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from godot_agent.godot.impact_analysis import format_impact_report, infer_request_impact
from godot_agent.agents.configs import AGENT_CONFIGS, AgentConfig
from godot_agent.agents.results import AgentTaskResult
from godot_agent.llm.client import LLMClient
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.runtime.design_memory import GameplayIntentProfile, load_design_memory
from godot_agent.runtime.intent_resolver import resolve_gameplay_intent
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.playtest_harness import format_playtest_report, run_playtest_harness
from godot_agent.runtime.quality_gate import QualityGateReport
from godot_agent.runtime.runtime_bridge import get_runtime_snapshot
from godot_agent.runtime.reviewer import format_review_report, review_changes
from godot_agent.tools.registry import ToolRegistry


class AgentDispatcher:
    """Creates role-scoped engines and deterministic review passes."""

    def __init__(
        self,
        *,
        client: LLMClient,
        registry: ToolRegistry,
        prompt_context: PromptContext | None,
        project_path: str | None,
        godot_path: str = "godot",
        base_allowed_tools: set[str] | None = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.prompt_context = prompt_context
        self.project_path = project_path
        self.godot_path = godot_path
        self.base_allowed_tools = set(base_allowed_tools) if base_allowed_tools is not None else None

    def _clone_registry(self) -> ToolRegistry:
        cloned = ToolRegistry()
        for tool in self.registry.list_tools():
            cloned.register(tool)
        return cloned

    def resolve_allowed_tools(self, role: str) -> set[str]:
        config = AGENT_CONFIGS[role]
        if self.base_allowed_tools is None:
            return set(config.allowed_tools)
        return set(config.allowed_tools & self.base_allowed_tools)

    def _build_prompt_assembler(self, config: AgentConfig) -> PromptAssembler | None:
        if self.prompt_context is None:
            return None
        context = replace(
            self.prompt_context,
            mode=config.mode,
            extra_prompt="\n\n".join(
                section for section in [self.prompt_context.extra_prompt, config.prompt] if section
            ),
        )
        return PromptAssembler(context)

    def _resolve_intent_profile(self, user_hint: str) -> GameplayIntentProfile:
        if not self.project_path:
            return GameplayIntentProfile()
        project_root = Path(self.project_path)
        design_memory = load_design_memory(project_root)
        return resolve_gameplay_intent(project_root, user_hint=user_hint, design_memory=design_memory)

    def _build_engine(self, config: AgentConfig, *, user_hint: str) -> ConversationEngine:
        registry = self._clone_registry()
        prompt_assembler = self._build_prompt_assembler(config)
        allowed_tools = self.resolve_allowed_tools(config.name)
        if prompt_assembler is not None:
            design_memory = load_design_memory(Path(self.project_path)) if self.project_path else None
            intent_profile = self._resolve_intent_profile(user_hint)
            system_prompt = prompt_assembler.build(
                user_hint=user_hint,
                active_tools=[tool.name for tool in registry.list_tools() if tool.name in allowed_tools],
                design_memory=design_memory,
                intent_profile=intent_profile,
            )
        else:
            system_prompt = config.prompt

        engine = ConversationEngine(
            client=self.client,
            registry=registry,
            system_prompt=system_prompt,
            max_tool_rounds=config.max_tool_rounds,
            project_path=self.project_path,
            godot_path=self.godot_path,
            auto_validate=config.auto_validate,
            prompt_assembler=prompt_assembler,
            mode=config.mode,
        )
        engine.base_allowed_tools = set(allowed_tools)
        engine.allowed_tools = set(allowed_tools)
        return engine

    async def run_planner(self, task: str) -> AgentTaskResult:
        config = AGENT_CONFIGS["planner"]
        engine = self._build_engine(config, user_hint=task)
        planning_prompt = task
        if self.project_path:
            impact_report = infer_request_impact(Path(self.project_path), task)
            planning_prompt = f"{task}\n\nLikely impact before implementation:\n{format_impact_report(impact_report)}"
        content = await engine.submit(planning_prompt)
        return AgentTaskResult(
            role=config.name,
            content=content,
            used_tools=engine.last_turn.tools_called if engine.last_turn else [],
        )

    async def run_worker(self, task: str, *, plan: str = "") -> AgentTaskResult:
        config = AGENT_CONFIGS["worker"]
        prompt = task if not plan else f"{task}\n\nApproved plan:\n{plan}"
        engine = self._build_engine(config, user_hint=task)
        content = await engine.submit(prompt)
        verdict = "FAIL" if engine.last_review_report and engine.last_review_report.requires_fix else "PASS"
        return AgentTaskResult(
            role=config.name,
            content=content,
            verdict=verdict,
            used_tools=engine.last_turn.tools_called if engine.last_turn else [],
        )

    async def run_reviewer(
        self,
        *,
        changed_files: set[str],
        quality_report: QualityGateReport | None = None,
    ) -> AgentTaskResult:
        if not self.project_path:
            return AgentTaskResult(role="reviewer", verdict="PASS", content="No project path configured.")
        report = await review_changes(
            project_root=Path(self.project_path),
            changed_files=changed_files,
            godot_path=self.godot_path,
            quality_report=quality_report,
            runtime_snapshot=get_runtime_snapshot(),
        )
        return AgentTaskResult(
            role="reviewer",
            content=format_review_report(report),
            verdict=report.verdict,
            raw=report,
        )

    async def run_playtest_analyst(self, *, changed_files: set[str]) -> AgentTaskResult:
        if not self.project_path:
            return AgentTaskResult(role="playtest_analyst", verdict="PASS", content="No project path configured.")
        report = run_playtest_harness(
            project_root=Path(self.project_path),
            changed_files=changed_files,
            runtime_snapshot=get_runtime_snapshot(),
            intent_profile=self._resolve_intent_profile(""),
            design_memory=load_design_memory(Path(self.project_path)),
        )
        return AgentTaskResult(
            role="playtest_analyst",
            content=format_playtest_report(report),
            verdict=report.verdict,
            raw=report,
        )

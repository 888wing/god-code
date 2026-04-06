"""Conversation engine with tool calling loop, context management, and error detection."""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from godot_agent.godot.impact_analysis import ImpactAnalysisReport, analyze_change_impact
from godot_agent.llm.client import LLMClient, Message, TokenUsage
from godot_agent.prompts.assembler import PromptAssembler
from godot_agent.prompts.skill_selector import narrow_tools_for_skills, resolve_skills
from godot_agent.runtime.context_manager import smart_compact, estimate_message_tokens, truncate_tool_result, compress_step_messages
from godot_agent.runtime.execution_plan import ExecutionPlan, PlanStep
from godot_agent.runtime.design_memory import DesignMemory, GameplayIntentProfile, load_design_memory
from godot_agent.runtime.events import EngineEvent
from godot_agent.runtime.intent_resolver import resolve_gameplay_intent
from godot_agent.runtime.playtest_harness import PlaytestReport, format_playtest_report, run_playtest_harness
from godot_agent.runtime.quality_gate import (
    ChangeSet,
    QualityGateReport,
    format_quality_gate_report,
    run_quality_gate,
)
from godot_agent.runtime.live_client import LiveRuntimeClient
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, get_runtime_snapshot, update_runtime_snapshot
from godot_agent.runtime.reviewer import ReviewReport, format_review_report, review_changes
from godot_agent.runtime.validation_checks import ValidationSuite
from godot_agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from godot_agent.agents.dispatcher import AgentDispatcher

log = logging.getLogger(__name__)

# Compact at 75% of 1.05M context to leave room for current turn
_COMPACT_THRESHOLD = 787500  # 75% of 1.05M
_FILE_MUTATING_TOOLS = {
    "write_file",
    "edit_file",
    "edit_script",
    "add_scene_node",
    "write_scene_property",
    "add_scene_connection",
    "remove_scene_node",
}
_FILE_READING_TOOLS = {
    "read_file",
    "read_script",
    "read_scene",
    "scene_tree",
}


class LoopPhase(enum.Enum):
    PREPARE_CONTEXT = "prepare_context"
    CALL_MODEL = "call_model"
    EXECUTE_TOOLS = "execute_tools"
    RUN_QUALITY_GATE = "run_quality_gate"
    RUN_REVIEWER = "run_reviewer"
    RUN_PLAYTEST_ANALYST = "run_playtest_analyst"
    RUN_VISUAL_ITERATION = "run_visual_iteration"
    NEXT_ROUND = "next_round"
    DONE = "done"


@dataclass
class TurnStats:
    usage: TokenUsage = field(default_factory=TokenUsage)
    api_calls: int = 0
    tools_called: list[str] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    validation_status: str = "not_run"
    validation_errors: int = 0
    validation_warnings: int = 0
    assistant_preview: str = ""


@dataclass
class ProjectScanSummary:
    project_path: str
    file_count: int
    guide_file: str | None = None
    sample_files: list[str] = field(default_factory=list)


@dataclass
class LoopState:
    phase: LoopPhase = LoopPhase.PREPARE_CONTEXT
    round_index: int = 0
    pending_response: Message | None = None
    final_response: str = ""
    tool_names_used: set[str] = field(default_factory=set)
    modified_files: set[str] = field(default_factory=set)


# Callback types
ToolStartCallback = Callable[[str, dict], None]  # (tool_name, args) -> None
ToolEndCallback = Callable[[str, bool, str], None]  # (tool_name, success, summary) -> None
DiffCallback = Callable[[str, str, str], None]  # (old_text, new_text, filename) -> None
EventCallback = Callable[[EngineEvent], None]


def _has_meaningful_text(value: str) -> bool:
    return any(ch.isprintable() and not ch.isspace() for ch in value)


class ConversationEngine:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        system_prompt: str,
        max_tool_rounds: int = 20,
        project_path: str | None = None,
        godot_path: str = "godot",
        auto_validate: bool = True,
        prompt_assembler: PromptAssembler | None = None,
        mode: str = "apply",
        dispatcher: "AgentDispatcher | None" = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[Message] = [Message.system(system_prompt)]
        self.project_path = project_path
        self.godot_path = godot_path
        self.auto_validate = auto_validate
        self.prompt_assembler = prompt_assembler
        self.mode = mode
        self.dispatcher = dispatcher
        self.session_usage = TokenUsage()
        self.session_api_calls = 0
        self.last_turn: TurnStats | None = None
        self.last_quality_report: QualityGateReport | None = None
        self.last_review_report: ReviewReport | None = None
        self.last_playtest_report: PlaytestReport | None = None
        self.last_impact_report: ImpactAnalysisReport | None = None
        self.design_memory: DesignMemory = load_design_memory(Path(self.project_path)) if self.project_path else DesignMemory()
        self.intent_profile: GameplayIntentProfile = GameplayIntentProfile()
        self.last_response: str = ""
        self.last_user_input: str = ""
        self.last_plan: str = ""
        self.current_plan: ExecutionPlan | None = None
        self.project_scan: ProjectScanSummary | None = None
        self.project_scan_text: str = ""
        self.changeset = ChangeSet()

        self.auto_commit = False
        self.use_streaming = False
        self.base_allowed_tools: set[str] | None = None
        self.allowed_tools: set[str] | None = None
        self.active_skills: list[str] = []
        self.skill_mode: str = "auto"
        self.enabled_skills: list[str] = []
        self.disabled_skills: list[str] = []

        # TUI callbacks
        self.on_tool_start: ToolStartCallback | None = None
        self.on_tool_end: ToolEndCallback | None = None
        self.on_diff: DiffCallback | None = None
        self.on_stream_start: Callable[[], None] | None = None
        self.on_stream_chunk: Callable[[str], None] | None = None
        self.on_stream_end: Callable[[bool], None] | None = None
        self.on_commit_suggest: Callable[[], None] | None = None
        self.on_event: EventCallback | None = None
        self._last_intent_signature: tuple[str, str, bool, tuple[str, ...]] | None = None
        self._live_client: LiveRuntimeClient | None = None
        self.refresh_intent_profile()
        self._sync_registry_context()

    def _emit_event(self, kind: str, message: str = "", **data: Any) -> None:
        if self.on_event:
            self.on_event(EngineEvent(kind=kind, message=message, data=data))

    def _sync_registry_context(self) -> None:
        self.registry.configure_execution_context(
            mode=self.mode,
            project_root=self.project_path if self.project_path else None,
            allowed_tools=self.allowed_tools,
            changeset=self.changeset,
            emit_event=lambda kind, message, data: self._emit_event(kind, message, **data),
            llm_client=self.client,
        )

    async def _try_live_bridge(self) -> None:
        """Attempt to connect to a running Godot instance via the live bridge.

        If Godot is reachable, fetches a live runtime snapshot and stores it as
        the current global snapshot.  If not reachable, silently continues.
        This method never raises — all exceptions are swallowed so the engine
        loop is never blocked by bridge failures.
        """
        try:
            if self._live_client is None:
                self._live_client = LiveRuntimeClient(timeout=0.5)
            connected = await self._live_client.connect()
            if connected:
                snapshot = await self._live_client.build_snapshot()
                update_runtime_snapshot(snapshot)
                await self._live_client.disconnect()
        except Exception:
            pass

    def _base_tool_scope(self) -> set[str] | None:
        if self.base_allowed_tools is not None:
            return set(self.base_allowed_tools)
        if self.allowed_tools is not None:
            self.base_allowed_tools = set(self.allowed_tools)
            return set(self.allowed_tools)
        return None

    def _refresh_tool_scope(self) -> None:
        base_scope = self._base_tool_scope()
        skills = resolve_skills(
            self.last_user_input,
            self._recent_context_files(),
            max_skills=2,
            skill_mode=self.skill_mode,
            enabled_skills=self.enabled_skills,
            disabled_skills=self.disabled_skills,
            intent_profile=self.intent_profile,
        )
        narrowed = narrow_tools_for_skills(skills, base_scope)

        self.active_skills = [skill.key for skill in skills]
        self.allowed_tools = narrowed if narrowed is not None else base_scope
        self._sync_registry_context()

    def _current_openai_tools(self) -> list[dict] | None:
        use_strict = getattr(getattr(self.client, "config", None), "model", "").startswith("gpt-5")
        return self.registry.to_openai_tools(self.allowed_tools, strict=use_strict) or None

    def scan_project(self) -> ProjectScanSummary | None:
        """Auto-scan project for context. Returns summary or None."""
        if not self.project_path:
            return None
        root = Path(self.project_path)
        parts: list[str] = []
        guide_file: str | None = None

        # Read CLAUDE.md if exists
        for name in ["CLAUDE.md", "README.md"]:
            f = root / name
            if f.exists():
                text = f.read_text(errors="replace")[:2000]
                parts.append(f"--- {name} ---\n{text}")
                guide_file = name
                break

        # List project structure
        files: list[str] = []
        for ext in ["*.gd", "*.tscn", "*.tres", "*.json"]:
            files.extend(str(p.relative_to(root)) for p in root.rglob(ext) if ".godot" not in str(p))
        if files:
            parts.append(f"--- Project files ({len(files)}) ---\n" + "\n".join(sorted(files)[:50]))

        if parts:
            context = "\n\n".join(parts)
            self.project_scan_text = context
            self.messages.append(Message.user(
                f"[SYSTEM] Project scan results (auto-loaded):\n{context}"
            ))
            self.project_scan = ProjectScanSummary(
                project_path=str(root),
                file_count=len(files),
                guide_file=guide_file,
                sample_files=sorted(files)[:5],
            )
            self._emit_event(
                "project_scanned",
                f"Loaded project context from {root}",
                file_count=len(files),
                guide_file=guide_file,
                sample_files=self.project_scan.sample_files,
            )
            return self.project_scan
        return None

    def _recent_context_files(self) -> list[str]:
        files = list(self.changeset.modified_files) + list(self.changeset.read_files)
        unique: list[str] = []
        seen: set[str] = set()
        for path in reversed(files):
            if path in seen:
                continue
            seen.add(path)
            unique.append(self._relative_path(path))
        return list(reversed(unique[-20:]))

    def _refresh_system_prompt(self) -> None:
        if not self.prompt_assembler:
            return

        if self.project_path:
            self.design_memory = load_design_memory(Path(self.project_path))
        self.refresh_intent_profile()
        active_tools = [
            tool.name
            for tool in self.registry.list_tools()
            if self.allowed_tools is None or tool.name in self.allowed_tools
        ]
        self.messages[0] = Message.system(
            self.prompt_assembler.build(
                user_hint=self.last_user_input,
                file_paths=self._recent_context_files(),
                skill_mode=self.skill_mode,
                enabled_skills=self.enabled_skills,
                disabled_skills=self.disabled_skills,
                active_tools=active_tools,
                project_scan=self.project_scan_text,
                design_memory=self.design_memory,
                intent_profile=self.intent_profile,
                impact_report=self.last_impact_report,
                runtime_snapshot=get_runtime_snapshot(),
                quality_report=self.last_quality_report,
                review_report=self.last_review_report,
                playtest_report=self.last_playtest_report,
            )
        )

    def refresh_intent_profile(self, user_hint: str | None = None) -> GameplayIntentProfile:
        if not self.project_path:
            self.intent_profile = GameplayIntentProfile()
            return self.intent_profile

        self.design_memory = load_design_memory(Path(self.project_path))
        self.intent_profile = resolve_gameplay_intent(
            Path(self.project_path),
            user_hint=user_hint if user_hint is not None else self.last_user_input,
            design_memory=self.design_memory,
            recent_files=self._recent_context_files(),
        )
        signature = (
            self.intent_profile.genre,
            self.intent_profile.enemy_model,
            self.intent_profile.confirmed,
            tuple(self.intent_profile.conflicts),
        )
        if signature != self._last_intent_signature:
            self._last_intent_signature = signature
            self._emit_event(
                "intent_inferred",
                self.intent_profile.genre or "unresolved",
                profile=self.intent_profile.to_dict(),
            )
            if self.intent_profile.conflicts:
                self._emit_event(
                    "intent_conflict_detected",
                    ", ".join(self.intent_profile.conflicts),
                    profile=self.intent_profile.to_dict(),
                )
        return self.intent_profile

    async def _maybe_compact(self) -> None:
        total = sum(estimate_message_tokens(m) for m in self.messages)
        if total > _COMPACT_THRESHOLD:
            before = len(self.messages)
            log.info("Smart compacting: ~%d tokens, %d messages", total, before)
            self.messages = smart_compact(
                self.messages, keep_recent=20, target_ratio=0.60, max_tokens=1050000
            )
            after = len(self.messages)
            after_tokens = sum(estimate_message_tokens(m) for m in self.messages)
            log.info("Compacted: %d → %d messages, ~%d tokens", before, after, after_tokens)
            self._emit_event(
                "context_compacted",
                f"Compacted context from {before} to {after} messages",
                before_messages=before,
                after_messages=after,
                after_tokens=after_tokens,
            )

    def _summarize_args(self, name: str, args: dict) -> str:
        """Create a short summary of tool arguments for display."""
        if name in {
            "read_file",
            "write_file",
            "edit_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "add_scene_node",
            "write_scene_property",
            "add_scene_connection",
            "remove_scene_node",
        }:
            path = args.get("path", "")
            return path.split("/")[-1] if "/" in path else path
        if name == "grep":
            return f'"{args.get("pattern", "")}"'
        if name == "glob":
            return args.get("pattern", "")
        if name in {"run_godot"}:
            return args.get("command", "")
        if name in {"validate_project", "check_consistency", "project_dependency_graph", "analyze_impact", "read_design_memory", "update_design_memory", "get_runtime_snapshot", "run_playtest"}:
            return self._relative_path(args.get("project_path", ""))
        if name in {"get_runtime_state", "get_events_since", "compare_baseline", "report_failure"}:
            return args.get("baseline_id", "") or args.get("test_id", "") or str(args.get("tick", ""))
        if name in {"load_scene", "capture_viewport"}:
            return args.get("scene_path", "") or args.get("artifact_name", "")
        if name == "press_action":
            return args.get("action", "")
        if name == "advance_ticks":
            return str(args.get("count", ""))
        if name == "set_fixture":
            return args.get("name", "")
        if name in {"slice_sprite_sheet", "validate_sprite_imports"}:
            return self._relative_path(args.get("input_path", "")) or self._relative_path(args.get("metadata_path", ""))
        if name == "git":
            return args.get("command", "")[:30]
        if name == "run_shell":
            return args.get("command", "")[:40]
        return ""

    def _relative_path(self, path_str: str) -> str:
        if not path_str:
            return ""
        path = Path(path_str)
        if self.project_path:
            try:
                return str(path.resolve().relative_to(Path(self.project_path).resolve()))
            except (ValueError, FileNotFoundError):
                pass
        return path.name or path_str

    def _summarize_result(self, name: str, args: dict, result: Any) -> str:
        if result.error:
            return result.error
        payload = result.output.model_dump() if getattr(result, "output", None) is not None else {}

        if name in {"read_file", "read_script"}:
            return f"read {payload.get('line_count', 0)} lines from {self._relative_path(args.get('path', ''))}"
        if name == "write_file":
            return f"wrote {payload.get('bytes_written', 0)} bytes to {self._relative_path(args.get('path', ''))}"
        if name in {"edit_file", "edit_script"}:
            return f"updated {self._relative_path(args.get('path', ''))}"
        if name in {"read_scene", "scene_tree"}:
            tree = payload.get("tree", "")
            node_count = len(payload.get("nodes", [])) if isinstance(payload.get("nodes"), list) else max(len(tree.splitlines()), 1)
            return f"read scene {self._relative_path(args.get('path', ''))} ({node_count} nodes)"
        if name == "add_scene_node":
            return f"added node {payload.get('node_added', '')} to {self._relative_path(args.get('path', ''))}"
        if name == "write_scene_property":
            return f"updated scene property in {self._relative_path(args.get('path', ''))}"
        if name == "add_scene_connection":
            return f"added scene connection in {self._relative_path(args.get('path', ''))}"
        if name == "remove_scene_node":
            return f"removed node from {self._relative_path(args.get('path', ''))}"
        if name == "lint_script":
            return f"linted {self._relative_path(args.get('path', ''))}: {payload.get('issue_count', 0)} issues"
        if name == "list_dir":
            return f"listed {payload.get('total', 0)} entries"
        if name == "grep":
            return f"found {len(payload.get('matches', []))} matches"
        if name == "glob":
            return f"found {len(payload.get('files', []))} files"
        if name == "run_godot":
            errors = len(payload.get("errors", []))
            warnings = len(payload.get("warnings", []))
            command = args.get("command", "godot")
            if command == "validate":
                return f"validate: {errors} errors, {warnings} warnings"
            return f"{command}: exit {payload.get('exit_code', 0)} with {errors} errors"
        if name in {"git", "run_shell"}:
            stdout = (payload.get("stdout", "") or "").strip()
            stderr = (payload.get("stderr", "") or "").strip()
            headline = stdout.splitlines()[0] if stdout else stderr.splitlines()[0] if stderr else ""
            if headline:
                return headline[:120]
            return f"exit {payload.get('exit_code', 0)}"
        if name == "validate_project":
            return "project validation passed" if payload.get("success") else "project validation failed"
        if name == "check_consistency":
            return f"consistency issues: {payload.get('issue_count', 0)}"
        if name == "project_dependency_graph":
            return payload.get("summary", "").splitlines()[0] if payload.get("summary") else "dependency graph built"
        if name == "analyze_impact":
            return f"impact covers {len(payload.get('affected_files', []))} files"
        if name in {"read_design_memory", "update_design_memory"}:
            report = payload.get("report", "")
            return report.splitlines()[0] if report else "design memory updated"
        if name == "get_runtime_snapshot":
            report = payload.get("report", "")
            return report.splitlines()[0] if report else "runtime snapshot read"
        if name == "run_playtest":
            return f"playtest verdict {payload.get('verdict', 'PASS')}"
        if name == "load_scene":
            return f"loaded {payload.get('active_scene', '')}"
        if name == "set_fixture":
            return f"fixtures: {', '.join(payload.get('fixture_names', []))}"
        if name == "press_action":
            active = payload.get("active_inputs", [])
            return f"active inputs: {', '.join(active) if active else 'none'}"
        if name == "advance_ticks":
            return f"advanced to tick {payload.get('current_tick', 0)}"
        if name == "get_runtime_state":
            state = payload.get("state", {})
            return f"runtime state keys: {len(state.get('state', state) if isinstance(state, dict) else state)}"
        if name == "get_events_since":
            return f"events: {len(payload.get('events', []))}"
        if name == "capture_viewport":
            return f"captured {self._relative_path(payload.get('path', ''))}"
        if name == "compare_baseline":
            verdict = "matched" if payload.get("matched") else "mismatch"
            return f"{verdict}: {payload.get('baseline_path', '').split('/')[-1]}"
        if name == "report_failure":
            return f"failure bundle {self._relative_path(payload.get('bundle_path', ''))}"
        if name == "slice_sprite_sheet":
            return f"sliced {payload.get('frame_count', 0)} frames"
        if name == "validate_sprite_imports":
            return "sprite imports valid" if payload.get("valid") else f"sprite import issues: {len(payload.get('issues', []))}"
        return "ok"

    def _record_tool_effect(self, tool_name: str, args: dict, succeeded: bool, modified_files: set[str]) -> None:
        if not succeeded:
            return
        path = args.get("path")
        if path and tool_name in _FILE_READING_TOOLS:
            self.changeset.mark_read(path)
        if path and tool_name in _FILE_MUTATING_TOOLS:
            self.changeset.mark_modified(path)
            modified_files.add(str(Path(path).resolve()))

    def _build_route_metadata(self, round_index: int = 0) -> dict:
        """Build routing metadata for backend orchestration."""
        skill = self.active_skills[0] if self.active_skills else None
        meta: dict = {
            "session_id": getattr(self, "session_id", ""),
            "agent_role": getattr(self, "_current_agent_role", "worker"),
            "skill": skill,
            "mode": self.mode,
            "round_number": round_index + 1,
            "changeset_size": len(self.changeset.modified_files),
            "estimated_tokens": 0,
        }
        # Backend routing hints from LLMConfig (propagated from AgentConfig)
        llm_cfg = getattr(self.client, "config", None)
        if llm_cfg:
            cost_pref = getattr(llm_cfg, "backend_cost_preference", "")
            if cost_pref and cost_pref != "balanced":
                meta["cost_preference"] = cost_pref
            force_provider = getattr(llm_cfg, "backend_force_provider", "")
            if force_provider:
                meta["force_provider"] = force_provider
            force_model = getattr(llm_cfg, "backend_force_model", "")
            if force_model:
                meta["force_model"] = force_model
        return meta

    async def _call_model(self, tools: list[dict] | None, use_streaming: bool, turn: TurnStats, round_index: int = 0) -> tuple[Message, bool]:
        stream_active = use_streaming and self.on_stream_chunk is not None
        route_metadata = self._build_route_metadata(round_index)
        if stream_active:
            if self.on_stream_start:
                self.on_stream_start()
            self._emit_event("assistant_stream_started", "Assistant is composing a reply")
            from godot_agent.llm.streaming import stream_chat_with_callback
            chat_resp = await stream_chat_with_callback(
                self.client,
                self.messages,
                tools,
                on_chunk=self.on_stream_chunk,
                route_metadata=route_metadata,
            )
        else:
            chat_resp = await self.client.chat(self.messages, tools, route_metadata=route_metadata)

        turn.usage = turn.usage + chat_resp.usage
        turn.api_calls += 1
        self.session_usage = self.session_usage + chat_resp.usage
        self.session_api_calls += 1
        self.messages.append(chat_resp.message)
        return chat_resp.message, stream_active

    async def _execute_pending_tools(self, response: Message, turn: TurnStats) -> tuple[set[str], set[str]]:
        tool_names_used: set[str] = set()
        modified_files: set[str] = set()
        for tc in response.tool_calls or []:
            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError:
                args = {}

            tool_names_used.add(tc.name)
            turn.tools_called.append(tc.name)
            summary = self._summarize_args(tc.name, args)

            if self.on_tool_start:
                self.on_tool_start(tc.name, args)
            self._emit_event(
                "tool_started",
                f"{tc.name}: {summary}" if summary else tc.name,
                tool_name=tc.name,
                args=args,
                args_summary=summary,
            )

            old_text = None
            if tc.name in _FILE_MUTATING_TOOLS and self.on_diff:
                path = args.get("path", "")
                try:
                    target_path = Path(path)
                    old_text = target_path.read_text(errors="replace") if target_path.exists() else ""
                except Exception:
                    old_text = None

            result = await self.registry.execute(tc.name, args)

            result_summary = self._summarize_result(tc.name, args, result)
            turn.tool_summaries.append(result_summary)

            if self.on_tool_end:
                self.on_tool_end(tc.name, result.error is None, result_summary)
            self._emit_event(
                "tool_finished",
                result_summary,
                tool_name=tc.name,
                success=result.error is None,
                summary=result_summary,
            )

            if tc.name in _FILE_MUTATING_TOOLS and old_text is not None and result.error is None and self.on_diff:
                try:
                    new_text = Path(args.get("path", "")).read_text(errors="replace")
                    filename = self._relative_path(args.get("path", ""))
                    self.on_diff(old_text, new_text, filename)
                except Exception:
                    pass

            self._record_tool_effect(tc.name, args, result.error is None, modified_files)

            if result.error:
                content = json.dumps({"error": result.error})
            else:
                raw = json.dumps(result.output.model_dump() if result.output else {})
                content = truncate_tool_result(raw)
            self.messages.append(Message.tool_result(tool_call_id=tc.id, content=content))

        return tool_names_used, modified_files

    async def _run_quality_gate_for_round(self, modified_files: set[str], turn: TurnStats) -> ValidationSuite | None:
        if not modified_files or not self.project_path or not self.auto_validate:
            return None

        suite = ValidationSuite(self.project_path, modified_files)
        await suite.run_all()

        self._emit_event("quality_gate_started", "Running Godot quality gate", changed_files=len(modified_files))
        report = await run_quality_gate(
            project_root=Path(self.project_path),
            changed_files=modified_files,
            godot_path=self.godot_path,
            validation_suite=suite,
        )
        self.last_impact_report = analyze_change_impact(Path(self.project_path), modified_files)
        self.last_quality_report = report
        turn.validation_status = report.verdict
        turn.validation_errors = len(report.errors)
        turn.validation_warnings = len(report.warnings)
        self._emit_event(
            "quality_gate_finished",
            f"Quality gate verdict: {report.verdict}",
            verdict=report.verdict,
            errors=len(report.errors),
            warnings=len(report.warnings),
        )

        guidance = (
            "Fix the blocking issues before proceeding."
            if report.requires_fix
            else "Use this verification status when you continue."
        )
        self.messages.append(
            Message.user(
                f"[SYSTEM] Quality gate after your changes:\n{format_quality_gate_report(report)}\n{guidance}"
            )
        )
        return suite

    async def _run_reviewer_for_round(self, modified_files: set[str], suite: ValidationSuite | None = None) -> None:
        if not modified_files or not self.project_path:
            return

        self._emit_event("reviewer_started", "Running reviewer pass", changed_files=len(modified_files))
        if self.dispatcher is not None:
            reviewer_result = await self.dispatcher.run_reviewer(
                changed_files=modified_files,
                quality_report=self.last_quality_report,
            )
            report = reviewer_result.raw if isinstance(reviewer_result.raw, ReviewReport) else None
            if report is None:
                report = ReviewReport()
        else:
            report = await review_changes(
                project_root=Path(self.project_path),
                changed_files=modified_files,
                godot_path=self.godot_path,
                quality_report=self.last_quality_report,
                design_memory=self.design_memory,
                intent_profile=self.intent_profile,
                impact_report=self.last_impact_report,
                runtime_snapshot=get_runtime_snapshot(),
                playtest_report=self.last_playtest_report,
                validation_suite=suite,
            )
        self.last_review_report = report
        self._emit_event("reviewer_finished", f"Reviewer verdict: {report.verdict}", verdict=report.verdict)

        guidance = (
            "Reviewer found blocking issues. Fix them before finalizing."
            if report.requires_fix
            else "Use the reviewer output to report validated results and remaining risks."
        )
        self.messages.append(
            Message.user(
                f"[SYSTEM] Reviewer pass after your changes:\n{format_review_report(report)}\n{guidance}"
            )
        )

        if self.auto_commit and not report.requires_fix and self.last_quality_report and not self.last_quality_report.requires_fix:
            if self.on_commit_suggest:
                self.on_commit_suggest()
            self._emit_event("commit_suggested", "Changes are ready to commit")

    async def _run_playtest_analyst_for_round(self, modified_files: set[str]) -> None:
        if not modified_files or not self.project_path:
            return
        self._emit_event("playtest_started", "Running playtest analyst", changed_files=len(modified_files))
        if self.dispatcher is not None:
            playtest_result = await self.dispatcher.run_playtest_analyst(changed_files=modified_files)
            report = playtest_result.raw if isinstance(playtest_result.raw, PlaytestReport) else None
        else:
            report = run_playtest_harness(
                project_root=Path(self.project_path),
                changed_files=modified_files,
                impact_report=self.last_impact_report,
                runtime_snapshot=get_runtime_snapshot(),
                intent_profile=self.intent_profile,
                design_memory=self.design_memory,
            )
        self.last_playtest_report = report or PlaytestReport()
        self._emit_event("playtest_finished", f"Playtest verdict: {self.last_playtest_report.verdict}", verdict=self.last_playtest_report.verdict)
        self.messages.append(
            Message.user(
                f"[SYSTEM] Playtest analyst after your changes:\n{format_playtest_report(self.last_playtest_report)}\n"
                "Use this runtime evidence when deciding whether the gameplay change is truly complete."
            )
        )

    async def _run_loop(self, tools: list[dict] | None, use_streaming: bool = False) -> str:
        turn = TurnStats()
        state = LoopState()
        suite: ValidationSuite | None = None

        while state.phase is not LoopPhase.DONE:
            if state.round_index > self.max_tool_rounds:
                self.last_turn = turn
                self._emit_event("turn_finished", "Tool call limit reached", total_tokens=turn.usage.total_tokens)
                return "Tool call limit reached. Please simplify the request."

            if state.phase is LoopPhase.PREPARE_CONTEXT:
                await self._try_live_bridge()
                await self._maybe_compact()
                self._refresh_tool_scope()
                self._refresh_system_prompt()
                self._emit_event(
                    "assistant_round_started",
                    f"Assistant round {state.round_index + 1}",
                    round_index=state.round_index + 1,
                )
                state.phase = LoopPhase.CALL_MODEL
                continue

            if state.phase is LoopPhase.CALL_MODEL:
                tools = self._current_openai_tools()
                response, stream_active = await self._call_model(tools, use_streaming, turn, round_index=state.round_index)
                state.pending_response = response

                if not response.tool_calls:
                    turn.assistant_preview = (response.content or "").strip().splitlines()[0][:120]
                    self.last_response = response.content or ""
                    if stream_active:
                        if self.on_stream_end:
                            self.on_stream_end(True)
                        self._emit_event("assistant_stream_finished", "Assistant response ready", final=True)
                    else:
                        self._emit_event("assistant_response_ready", turn.assistant_preview, final=True)
                    state.final_response = response.content or ""
                    state.phase = LoopPhase.DONE
                    continue

                if stream_active:
                    if self.on_stream_end:
                        self.on_stream_end(False)
                    self._emit_event(
                        "assistant_stream_finished",
                        "Assistant requested tools",
                        final=False,
                        tool_calls=len(response.tool_calls),
                    )

                state.phase = LoopPhase.EXECUTE_TOOLS
                continue

            if state.phase is LoopPhase.EXECUTE_TOOLS:
                assert state.pending_response is not None
                state.tool_names_used, state.modified_files = await self._execute_pending_tools(state.pending_response, turn)
                state.phase = LoopPhase.RUN_QUALITY_GATE
                continue

            if state.phase is LoopPhase.RUN_QUALITY_GATE:
                suite = await self._run_quality_gate_for_round(state.modified_files, turn)
                state.phase = LoopPhase.RUN_REVIEWER
                continue

            if state.phase is LoopPhase.RUN_REVIEWER:
                await self._run_reviewer_for_round(state.modified_files, suite=suite)
                state.phase = LoopPhase.RUN_PLAYTEST_ANALYST
                continue

            if state.phase is LoopPhase.RUN_PLAYTEST_ANALYST:
                await self._run_playtest_analyst_for_round(state.modified_files)
                state.phase = LoopPhase.RUN_VISUAL_ITERATION
                continue

            if state.phase is LoopPhase.RUN_VISUAL_ITERATION:
                # Visual iteration sub-loop placeholder.
                # When fully wired, this phase will:
                #   screenshot -> analyze_screenshot -> apply changes ->
                #   re-screenshot -> score_screenshot -> check threshold
                # For now, transition directly to NEXT_ROUND.
                state.phase = LoopPhase.NEXT_ROUND
                continue

            if state.phase is LoopPhase.NEXT_ROUND:
                state.round_index += 1
                state.pending_response = None
                state.tool_names_used.clear()
                state.modified_files = set()
                state.phase = LoopPhase.PREPARE_CONTEXT
                continue

        self.last_turn = turn
        self._emit_event(
            "turn_finished",
            "Turn finished",
            total_tokens=turn.usage.total_tokens,
            tools=turn.tools_called,
            validation_status=turn.validation_status,
        )
        return state.final_response

    async def _maybe_run_planner(self, user_input: str) -> None:
        if self.dispatcher is None or self.mode not in {"apply", "fix"} or not _has_meaningful_text(user_input):
            return

        self._emit_event("planner_started", "Running planner pass")
        if self.project_path:
            self.last_impact_report = analyze_change_impact(Path(self.project_path), set(self.changeset.read_files) or {str(Path(self.project_path) / "project.godot")})
        planner_result = await self.dispatcher.run_planner(user_input)
        self.last_plan = planner_result.content
        self.messages.append(
            Message.user(
                f"[SYSTEM] Planner pass before implementation:\n{planner_result.content}\n"
                "Follow this plan unless direct inspection or validation proves it wrong."
            )
        )
        self._emit_event("planner_finished", "Planner pass complete", used_tools=planner_result.used_tools)

    async def submit(self, user_input: str) -> str:
        if not _has_meaningful_text(user_input):
            return ""
        self.last_user_input = user_input
        self.refresh_intent_profile(user_input)
        self._sync_registry_context()
        await self._maybe_run_planner(user_input)
        self.messages.append(Message.user(user_input))
        self._emit_event("turn_started", user_input.splitlines()[0][:120], user_input=user_input)
        return await self._run_loop(None, use_streaming=self.use_streaming)

    async def submit_with_images(self, text: str, images_b64: list[str]) -> str:
        if not images_b64 and not _has_meaningful_text(text):
            return ""
        self.last_user_input = text
        self.refresh_intent_profile(text)
        self._sync_registry_context()
        await self._maybe_run_planner(text)
        self.messages.append(Message.user_with_images(text, images_b64))
        self._emit_event("turn_started", text.splitlines()[0][:120], user_input=text, images=len(images_b64))
        return await self._run_loop(None, use_streaming=self.use_streaming)

    def _check_auto_health(self) -> "ContextHealth":
        from godot_agent.runtime.context_health import ContextHealth
        total_tokens = sum(estimate_message_tokens(m) for m in self.messages)
        usage_ratio = total_tokens / 1050000
        return ContextHealth(
            token_usage_ratio=usage_ratio,
            consecutive_errors=getattr(self, '_auto_consecutive_errors', 0),
            tool_success_rate=getattr(self, '_auto_tool_success_rate', 1.0),
            rounds_since_compact=getattr(self, '_auto_rounds_since_compact', 0),
        )

    async def _run_auto_step(self, step: PlanStep) -> bool:
        """Execute a single plan step. Returns True if successful."""
        step.status = "running"
        instruction = (
            f"[AUTO] Execute step {step.index}: {step.action} {step.target}\n"
            f"Files: {', '.join(step.files)}"
        )
        self.messages.append(Message.user(instruction))
        old_mode = self.mode
        self.mode = "auto_execute"
        self._sync_registry_context()
        try:
            result = await self._run_loop(None, use_streaming=self.use_streaming)
            if self.last_quality_report and self.last_quality_report.requires_fix:
                for _retry in range(3):
                    self.messages.append(Message.user("[AUTO] Quality gate failed. Fix the issues."))
                    result = await self._run_loop(None, use_streaming=self.use_streaming)
                    if not self.last_quality_report or not self.last_quality_report.requires_fix:
                        break
                else:
                    step.status = "failed"
                    step.summary = "quality gate failed after 3 retries"
                    return False
            step.mark_done(f"completed: {', '.join(step.files)}")
            self.messages = compress_step_messages(self.messages, step.index, step.summary)
            return True
        except Exception as e:
            step.status = "failed"
            step.summary = str(e)[:200]
            return False
        finally:
            self.mode = old_mode
            self._sync_registry_context()

    async def close(self) -> None:
        await self.client.close()

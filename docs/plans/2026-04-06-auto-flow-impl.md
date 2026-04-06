# `/auto` Smart Agent Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unified `/auto` command that understands a request, produces a structured plan, gets user approval, and executes to completion with context protection and live progress tracking.

**Architecture:** New `ExecutionPlan` dataclass holds plan steps. Engine gets a new `_run_auto_flow()` method that orchestrates understand→plan→execute→report. Context protection via tool result truncation, step compression, report pruning, and health monitoring. Session handoff enhanced with changeset + plan persistence.

**Tech Stack:** Python 3.12+, pytest, pytest-asyncio. Existing engine/TUI/security infrastructure.

**Design Doc:** `docs/plans/2026-04-06-interactive-ux-redesign.md`

---

## Task 1: ExecutionPlan dataclass

**Files:**
- Create: `godot_agent/runtime/execution_plan.py`
- Test: `tests/runtime/test_execution_plan.py`

**Step 1: Write the failing test**

```python
# tests/runtime/test_execution_plan.py
from __future__ import annotations
from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan

def test_plan_step_defaults():
    step = PlanStep(index=1, action="create", target="boss state machine", files=["src/boss.gd"])
    assert step.status == "pending"
    assert step.summary == ""

def test_execution_plan_approved_steps():
    plan = ExecutionPlan(title="Add boss", steps=[
        PlanStep(index=1, action="create", target="base class", files=["a.gd"], status="approved"),
        PlanStep(index=2, action="modify", target="spawner", files=["b.gd"], status="skipped"),
        PlanStep(index=3, action="create", target="scene", files=["c.tscn"], status="approved"),
    ], risk="medium")
    assert len(plan.approved_steps) == 2
    assert plan.pending_steps == []

def test_plan_step_mark_done():
    step = PlanStep(index=1, action="create", target="test", files=["a.gd"], status="approved")
    step.mark_done("created a.gd +45 lines")
    assert step.status == "done"
    assert step.summary == "created a.gd +45 lines"

def test_plan_serialization_roundtrip():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="file", files=["a.gd"], status="done", summary="ok"),
    ], risk="low")
    data = plan.to_dict()
    restored = ExecutionPlan.from_dict(data)
    assert restored.title == plan.title
    assert restored.steps[0].status == "done"

def test_plan_progress_display():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="a", files=["a.gd"], status="done"),
        PlanStep(index=2, action="modify", target="b", files=["b.gd"], status="running"),
        PlanStep(index=3, action="create", target="c", files=["c.gd"], status="pending"),
    ], risk="low")
    assert plan.done_count == 1
    assert plan.total_actionable == 3
    assert plan.current_step.index == 2
```

**Step 2: Run test — FAIL**

Run: `cd ~/projects/god-code && .venv/bin/python -m pytest tests/runtime/test_execution_plan.py -v`

**Step 3: Implement**

```python
# godot_agent/runtime/execution_plan.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class PlanStep:
    index: int
    action: str          # create, modify, delete, configure, validate
    target: str          # human-readable description
    files: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, approved, skipped, running, done, failed
    summary: str = ""

    def mark_done(self, summary: str) -> None:
        self.status = "done"
        self.summary = summary

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "action": self.action, "target": self.target,
                "files": self.files, "status": self.status, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutionPlan:
    title: str
    steps: list[PlanStep] = field(default_factory=list)
    risk: str = "low"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def approved_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "approved"]

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    @property
    def actionable_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status in ("approved", "running", "done", "failed")]

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")

    @property
    def total_actionable(self) -> int:
        return len(self.actionable_steps)

    @property
    def current_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "running":
                return s
        for s in self.steps:
            if s.status == "approved":
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "steps": [s.to_dict() for s in self.steps],
                "risk": self.risk, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(title=data["title"], steps=steps, risk=data.get("risk", "low"),
                   created_at=data.get("created_at", ""))
```

**Step 4: Run test — PASS**

**Step 5: Commit**

```bash
git add godot_agent/runtime/execution_plan.py tests/runtime/test_execution_plan.py
git commit -m "feat: add ExecutionPlan and PlanStep dataclasses"
```

---

## Task 2: Tool result truncation

**Files:**
- Modify: `godot_agent/runtime/context_manager.py`
- Test: `tests/runtime/test_context_manager.py`

**Step 1: Write the failing test**

```python
# Append to tests/runtime/test_context_manager.py
from godot_agent.runtime.context_manager import truncate_tool_result

def test_truncate_short_result_unchanged():
    text = "short result"
    assert truncate_tool_result(text) == text

def test_truncate_long_result():
    text = "A" * 5000
    result = truncate_tool_result(text, max_chars=2000)
    assert len(result) < 2500
    assert "[...truncated" in result
    assert result.startswith("A" * 100)  # head preserved
    assert result.endswith("A" * 100)    # tail preserved

def test_truncate_preserves_json_structure():
    import json
    data = {"output": "x" * 5000, "metadata": {"risk": "low"}}
    text = json.dumps(data)
    result = truncate_tool_result(text, max_chars=2000)
    assert len(result) < 2500
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# Add to godot_agent/runtime/context_manager.py

def truncate_tool_result(content: str, max_chars: int = 2000) -> str:
    """Truncate large tool results, keeping head and tail for context."""
    if len(content) <= max_chars:
        return content
    head_size = int(max_chars * 0.6)
    tail_size = int(max_chars * 0.25)
    omitted = len(content) - head_size - tail_size
    return f"{content[:head_size]}\n[...truncated {omitted} chars...]\n{content[-tail_size:]}"
```

**Step 4: Wire into engine.py `_execute_pending_tools`**

In `godot_agent/runtime/engine.py`, import `truncate_tool_result` and apply it before appending tool results:

```python
# At line ~638, replace:
#   content = json.dumps(result.output.model_dump() if result.output else {})
# With:
from godot_agent.runtime.context_manager import truncate_tool_result
raw = json.dumps(result.output.model_dump() if result.output else {})
content = truncate_tool_result(raw)
```

**Step 5: Run full suite — PASS**

**Step 6: Commit**

```bash
git commit -am "feat: truncate large tool results to protect context window"
```

---

## Task 3: Report pruning

**Files:**
- Modify: `godot_agent/runtime/context_manager.py`
- Test: `tests/runtime/test_context_manager.py`

**Step 1: Write the failing test**

```python
from godot_agent.runtime.context_manager import prune_system_reports
from godot_agent.llm.types import Message

def test_prune_keeps_latest_two_reports():
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Quality gate: report 1"),
        Message.user("normal user message"),
        Message.user("[SYSTEM] Quality gate: report 2"),
        Message.user("[SYSTEM] Quality gate: report 3"),
        Message.user("another user message"),
    ]
    pruned = prune_system_reports(messages, max_reports=2)
    system_reports = [m for m in pruned if m.content and "[SYSTEM]" in m.content]
    assert len(system_reports) == 2
    assert "report 2" in system_reports[0].content
    assert "report 3" in system_reports[1].content

def test_prune_keeps_all_when_under_limit():
    messages = [
        Message.system("system"),
        Message.user("[SYSTEM] Quality gate: report 1"),
    ]
    pruned = prune_system_reports(messages, max_reports=2)
    assert len(pruned) == 2
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# Add to godot_agent/runtime/context_manager.py

def prune_system_reports(messages: list[Message], max_reports: int = 2) -> list[Message]:
    """Remove old [SYSTEM] quality/reviewer/playtest reports, keeping latest N."""
    report_indices: list[int] = []
    for i, m in enumerate(messages):
        if m.role == "user" and isinstance(m.content, str) and m.content.startswith("[SYSTEM]"):
            report_indices.append(i)
    if len(report_indices) <= max_reports:
        return messages
    to_remove = set(report_indices[:-max_reports])
    return [m for i, m in enumerate(messages) if i not in to_remove]
```

**Step 4: Run — PASS**

**Step 5: Commit**

```bash
git commit -am "feat: prune old system reports from context"
```

---

## Task 4: Context health monitor

**Files:**
- Create: `godot_agent/runtime/context_health.py`
- Test: `tests/runtime/test_context_health.py`

**Step 1: Write the failing test**

```python
# tests/runtime/test_context_health.py
from __future__ import annotations
from godot_agent.runtime.context_health import ContextHealth

def test_healthy_context():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=2)
    assert not h.should_pause
    assert not h.should_compact

def test_should_pause_on_errors():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=3, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_pause

def test_should_pause_on_low_success():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.2, rounds_since_compact=0)
    assert h.should_pause

def test_should_compact_on_high_usage():
    h = ContextHealth(token_usage_ratio=0.65, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_compact

def test_should_compact_on_many_rounds():
    h = ContextHealth(token_usage_ratio=0.3, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=6)
    assert h.should_compact

def test_should_pause_on_extreme_usage():
    h = ContextHealth(token_usage_ratio=0.92, consecutive_errors=0, tool_success_rate=0.9, rounds_since_compact=0)
    assert h.should_pause
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# godot_agent/runtime/context_health.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ContextHealth:
    token_usage_ratio: float = 0.0
    consecutive_errors: int = 0
    tool_success_rate: float = 1.0
    rounds_since_compact: int = 0

    @property
    def should_pause(self) -> bool:
        return (
            self.consecutive_errors >= 3
            or self.tool_success_rate < 0.3
            or self.token_usage_ratio > 0.9
        )

    @property
    def should_compact(self) -> bool:
        return self.token_usage_ratio > 0.6 or self.rounds_since_compact > 5
```

**Step 4: Run — PASS**

**Step 5: Commit**

```bash
git add godot_agent/runtime/context_health.py tests/runtime/test_context_health.py
git commit -am "feat: add ContextHealth monitor for degradation detection"
```

---

## Task 5: TUI plan display + status line

**Files:**
- Modify: `godot_agent/tui/display.py`
- Test: `tests/tui/test_display.py` (or verify manually)

**Step 1: Write the test**

```python
# Append to tests/tui/test_display.py (or create if needed)
def test_plan_panel_renders(capsys):
    from godot_agent.tui.display import Display
    from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan
    d = Display()
    plan = ExecutionPlan(title="Test Plan", steps=[
        PlanStep(index=1, action="create", target="file A", files=["a.gd"], status="done", summary="+45 lines"),
        PlanStep(index=2, action="modify", target="file B", files=["b.gd"], status="running"),
        PlanStep(index=3, action="create", target="file C", files=["c.gd"], status="pending"),
    ], risk="medium")
    d.plan_panel(plan)  # Should not crash

def test_plan_status_line():
    from godot_agent.tui.display import Display
    from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan
    d = Display()
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="running"),
    ], risk="low")
    line = d.plan_status_line(plan)
    assert "2" in line  # step number
    assert "B" in line  # current target
```

**Step 2: Implement two new display methods**

```python
# Add to godot_agent/tui/display.py

def plan_panel(self, plan: ExecutionPlan) -> None:
    """Rich panel showing all plan steps with status icons."""
    from godot_agent.runtime.execution_plan import ExecutionPlan
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(width=3)  # icon
    t.add_column()          # step description
    t.add_column(style="dim")  # summary/files
    STATUS_ICONS = {"done": "[green]OK[/]", "running": "[yellow]>>[/]", "pending": "[dim]..[/]",
                    "approved": "[dim]..[/]", "failed": "[red]!![/]", "skipped": "[dim]--[/]"}
    for s in plan.steps:
        icon = STATUS_ICONS.get(s.status, "  ")
        desc = f"{s.index}. {s.action} {s.target}"
        info = s.summary if s.summary else ", ".join(s.files[:2])
        t.add_row(icon, desc, f"[dim]{info}[/]")
    progress = f"Progress: {plan.done_count}/{plan.total_actionable}"
    panel = Panel(Group(t, Text(progress, style="dim")), title=f"Plan: {plan.title}", border_style="green")
    self.console.print(panel)

def plan_status_line(self, plan: ExecutionPlan) -> str:
    """One-line status for persistent display during auto execution."""
    step = plan.current_step
    if not step:
        return f"[green]Plan complete: {plan.done_count}/{plan.total_actionable}[/]"
    return f"[yellow]Step {step.index}/{plan.total_actionable}: {step.action} {step.target}...[/]"
```

**Step 3: Add `/status` plan display to commands.py**

In `godot_agent/cli/commands.py`, find the existing `/status` handler and add plan display:

```python
# After existing /status logic, add:
if hasattr(engine, 'current_plan') and engine.current_plan:
    display.plan_panel(engine.current_plan)
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git commit -am "feat: add plan panel and status line to TUI"
```

---

## Task 6: System prompt proactive rules

**Files:**
- Modify: `godot_agent/prompts/assembler.py`
- Test: `tests/prompts/test_assembler.py`

**Step 1: Write the test**

```python
# Append to tests/prompts/test_assembler.py
def test_proactive_rules_in_prompt():
    from godot_agent.prompts.assembler import PromptAssembler, PromptContext
    from pathlib import Path
    ctx = PromptContext(project_root=Path("/tmp/fake"), mode="apply")
    assembler = PromptAssembler(ctx)
    prompt = assembler.build(user_hint="test")
    assert "When to Pause" in prompt or "before proceeding" in prompt.lower()

def test_auto_mode_plan_format_in_prompt():
    from godot_agent.prompts.assembler import PromptAssembler, PromptContext
    from pathlib import Path
    ctx = PromptContext(project_root=Path("/tmp/fake"), mode="apply")
    assembler = PromptAssembler(ctx)
    prompt = assembler.build(user_hint="test", auto_mode=True)
    assert "### Plan:" in prompt
```

**Step 2: Implement**

Add `_proactive_rules_section()` and `_auto_plan_format_section()` methods to `PromptAssembler`:

```python
# In assembler.py

def _proactive_rules_section(self) -> str:
    return """## When to Pause and Ask

Before making changes, assess scope. If your plan would:
- Modify 5+ files → state the scope and ask "proceed?"
- Delete anything → list what will be removed and confirm
- Conflict with design memory → quote the conflict and ask

When the request is vague ("fix the UI", "improve performance"):
- List what you found and ask which to address
- Do NOT guess and act on all of them

Proceed without asking when scope is clear, contained (1-3 files), and reversible."""

def _auto_plan_format_section(self) -> str:
    return """## Plan Output Format

Output plans in this format:

### Plan: [title]

**Scope**: [N] files | **Risk**: low/medium/high | **Steps**: [N]

1. [action] [target] — [description]
   Files: `path/file.gd`

2. [action] [target] — [description]
   Files: `path/file.tscn`

Risks: [if any]"""
```

Add `auto_mode: bool = False` parameter to `build()` method. Include `_proactive_rules_section()` always, and `_auto_plan_format_section()` when `auto_mode=True`.

**Step 3: Run — PASS**

**Step 4: Commit**

```bash
git commit -am "feat: add proactive questioning rules and plan format to system prompt"
```

---

## Task 7: Permission bypass for auto-execute

**Files:**
- Modify: `godot_agent/security/hooks.py`
- Modify: `godot_agent/security/policies.py`
- Test: `tests/security/test_hooks.py`
- Test: `tests/security/test_policies.py`

**Step 1: Write the failing test**

```python
# Append to tests/security/test_hooks.py
import pytest
from unittest.mock import MagicMock
from godot_agent.security.hooks import RequireReadBeforeWriteHook

@pytest.mark.asyncio
async def test_read_before_write_allows_in_auto_mode():
    hook = RequireReadBeforeWriteHook()
    tool = MagicMock()
    tool.name = "edit_file"
    input_obj = MagicMock()
    input_obj.path = "/tmp/test.gd"
    context = MagicMock()
    context.mode = "auto_execute"
    context.changeset.read_files = set()  # NOT read yet
    result = await hook.pre_execute(tool, input_obj, context)
    # In auto_execute mode, should NOT block
    assert result is None or result.permission_behavior != "deny"
```

```python
# Append to tests/security/test_policies.py
def test_auto_execute_allows_high_risk():
    from godot_agent.security.policies import PermissionPolicyFramework, ToolExecutionContext
    from godot_agent.security.classifier import OperationRisk
    from unittest.mock import MagicMock
    framework = PermissionPolicyFramework()
    tool = MagicMock()
    tool.name = "edit_file"
    tool.is_read_only.return_value = False
    context = ToolExecutionContext(mode="auto_execute")
    context.allowed_tools = {"edit_file"}
    hook_result = MagicMock()
    hook_result.permission_behavior = None
    hook_result.blocking_error = None
    decision = framework.evaluate(tool=tool, parsed_input=MagicMock(), context=context, risk=OperationRisk.HIGH, hook_result=hook_result)
    assert decision.allowed
```

**Step 2: Run — FAIL**

**Step 3: Implement**

In `hooks.py` `RequireReadBeforeWriteHook.pre_execute()`:
```python
# At the top of pre_execute, add:
if context.mode == "auto_execute":
    return None  # Auto-execute bypasses read-before-write
```

In `policies.py` `evaluate()`, add `"auto_execute"` alongside `"apply"` and `"fix"` in the mode checks:
```python
# Change: context.mode not in {"apply", "fix"}
# To:     context.mode not in {"apply", "fix", "auto_execute"}
```

**Step 4: Run full suite — PASS**

**Step 5: Commit**

```bash
git commit -am "feat: add auto_execute mode bypass for read-before-write and HIGH risk"
```

---

## Task 8: Session handoff with changeset + plan

**Files:**
- Modify: `godot_agent/runtime/session.py`
- Test: `tests/runtime/test_session.py`

**Step 1: Write the failing test**

```python
# Append to tests/runtime/test_session.py
def test_session_saves_changeset(tmp_path):
    from godot_agent.runtime.session import save_session, load_session
    from godot_agent.llm.types import Message
    path = save_session(
        str(tmp_path), "test-1", [Message.system("sys")],
        changeset_read=["a.gd", "b.gd"],
        changeset_modified=["a.gd"],
        completed_steps=["Step 1: created a.gd +45 lines"],
    )
    record = load_session(path)
    assert record.changeset_read == ["a.gd", "b.gd"]
    assert record.changeset_modified == ["a.gd"]
    assert record.completed_steps == ["Step 1: created a.gd +45 lines"]

def test_session_loads_without_changeset(tmp_path):
    """Backward compat: old sessions without changeset fields."""
    from godot_agent.runtime.session import save_session, load_session
    from godot_agent.llm.types import Message
    path = save_session(str(tmp_path), "test-2", [Message.system("sys")])
    record = load_session(path)
    assert record.changeset_read == []
    assert record.changeset_modified == []
    assert record.completed_steps == []
```

**Step 2: Run — FAIL**

**Step 3: Add fields to SessionRecord and save/load**

Add to `SessionRecord`:
```python
changeset_read: list[str] = field(default_factory=list)
changeset_modified: list[str] = field(default_factory=list)
completed_steps: list[str] = field(default_factory=list)
last_plan: dict[str, Any] | None = None
```

Add matching params to `save_session()` and include them in the JSON output. In `load_session()`, use `.get()` with empty defaults for backward compat.

**Step 4: Run — PASS**

**Step 5: Commit**

```bash
git commit -am "feat: persist changeset and plan steps in session records"
```

---

## Task 9: `/auto` command + engine flow

**Files:**
- Modify: `godot_agent/cli/commands.py`
- Modify: `godot_agent/runtime/engine.py`
- Test: `tests/runtime/test_engine.py`

This is the largest task — the core `/auto` flow.

**Step 1: Write the test**

```python
# Append to tests/runtime/test_engine.py
def test_engine_has_current_plan():
    from godot_agent.runtime.engine import ConversationEngine
    assert hasattr(ConversationEngine, 'current_plan')

def test_engine_has_auto_execute_method():
    from godot_agent.runtime.engine import ConversationEngine
    assert hasattr(ConversationEngine, '_run_auto_step')
```

**Step 2: Run — FAIL**

**Step 3: Add to engine.py**

Add `current_plan: ExecutionPlan | None = None` to `ConversationEngine.__init__()`.

Add `_run_auto_step()` method:
```python
async def _run_auto_step(self, step: PlanStep) -> bool:
    """Execute a single plan step. Returns True if successful."""
    step.status = "running"
    # Inject step instruction as user message
    instruction = f"[AUTO] Execute step {step.index}: {step.action} {step.target}\nFiles: {', '.join(step.files)}"
    self.messages.append(Message.user(instruction))
    # Run one model+tools loop
    old_mode = self.mode
    self.mode = "auto_execute"
    self._sync_registry_context()
    try:
        result = await self._run_loop(None, use_streaming=self.use_streaming)
        # Check quality gate
        if self.last_quality_report and self.last_quality_report.requires_fix:
            # Auto-retry up to 3 times
            for retry in range(3):
                self.messages.append(Message.user("[AUTO] Quality gate failed. Fix the issues."))
                result = await self._run_loop(None, use_streaming=self.use_streaming)
                if not self.last_quality_report or not self.last_quality_report.requires_fix:
                    break
            else:
                step.status = "failed"
                step.summary = "quality gate failed after 3 retries"
                return False
        step.mark_done(f"completed: {', '.join(step.files)}")
        return True
    except Exception as e:
        step.status = "failed"
        step.summary = str(e)[:200]
        return False
    finally:
        self.mode = old_mode
        self._sync_registry_context()
```

**Step 4: Add `/auto` command handler in commands.py**

In the command dispatch section of `_loop()`, add:

```python
if cmd == "/auto" or cmd.startswith("/auto "):
    auto_request = stripped[5:].strip() if len(stripped) > 5 else ""
    if not auto_request:
        display.error("Usage: /auto <what you want to build>")
        continue
    await _run_auto_flow(auto_request)
    continue
```

Implement `_run_auto_flow(request: str)`:
```python
async def _run_auto_flow(request: str):
    nonlocal engine
    # Phase 1: UNDERSTAND + PLAN — ask model to produce structured plan
    plan_prompt = (
        f"The user wants: {request}\n\n"
        "Scan the project, then output a structured plan using the Plan Output Format. "
        "If you need to ask 1-2 clarifying questions first, ask them now."
    )
    with display.thinking():
        response = await engine.submit(plan_prompt)
    display.agent_response(response)

    # Parse plan from response (look for "### Plan:" header)
    plan = _parse_plan_from_response(response)
    if not plan:
        display.info("No structured plan detected. Use /auto again with a clearer request.")
        return

    engine.current_plan = plan
    display.plan_panel(plan)

    # Phase 2: APPROVE
    display.info("approve / skip N / add: ... / cancel")
    while True:
        choice = await _prompt_text_value("<cyan>plan></cyan> ")
        if not choice or choice.lower() == "cancel":
            engine.current_plan = None
            display.info("Plan cancelled.")
            return
        if choice.lower() in ("approve", "go", "y", "yes"):
            for s in plan.steps:
                if s.status == "pending":
                    s.status = "approved"
            break
        if choice.lower().startswith("skip"):
            indices = [int(x) for x in choice.split()[1:] if x.isdigit()]
            for s in plan.steps:
                if s.index in indices:
                    s.status = "skipped"
            display.plan_panel(plan)
            continue

    # Phase 3: EXECUTE
    display.info("Executing plan...")
    for step in plan.steps:
        if step.status != "approved":
            continue
        display.console.print(f"  {engine._tui_display.plan_status_line(plan)}" if hasattr(engine, '_tui_display') else f"  Step {step.index}/{plan.total_actionable}: {step.action} {step.target}...")
        success = await engine._run_auto_step(step)
        if not success:
            display.error(f"Step {step.index} failed: {step.summary}")
            display.plan_panel(plan)
            display.info("Fix the issue and run /auto again, or continue manually.")
            return

    # Phase 4: REPORT
    display.plan_panel(plan)
    display.success(f"Plan complete: {plan.done_count}/{plan.total_actionable} steps done.")
    engine.current_plan = None
```

**Step 5: Run full suite — PASS**

**Step 6: Commit**

```bash
git commit -am "feat: add /auto command with understand → plan → approve → execute flow"
```

---

## Task 10: Step compression during auto-execute

**Files:**
- Modify: `godot_agent/runtime/context_manager.py`
- Modify: `godot_agent/runtime/engine.py`
- Test: `tests/runtime/test_context_manager.py`

**Step 1: Write the test**

```python
from godot_agent.runtime.context_manager import compress_step_messages
from godot_agent.llm.types import Message

def test_compress_step_messages():
    messages = [
        Message.system("sys"),
        Message.user("do something earlier"),
        Message.user("[AUTO] Execute step 1: create boss.gd"),
        Message.assistant(content="I'll create the file", tool_calls=[]),
        Message.user('{"output": "' + 'x' * 3000 + '"}'),  # large tool result
        Message.user("[SYSTEM] Quality gate: passed"),
        Message.user("[AUTO] Execute step 2: modify spawner"),
    ]
    compressed = compress_step_messages(messages, completed_step_index=1, summary="created boss.gd +45 lines")
    # Step 1's tool results + quality report should be replaced with summary
    assert len(compressed) < len(messages)
    step_summary = [m for m in compressed if "Step 1 done" in (m.content or "")]
    assert len(step_summary) == 1
```

**Step 2: Implement**

```python
# Add to context_manager.py
def compress_step_messages(messages: list[Message], completed_step_index: int, summary: str) -> list[Message]:
    """Replace a completed step's messages with a 1-line summary."""
    marker = f"[AUTO] Execute step {completed_step_index}:"
    next_marker = f"[AUTO] Execute step {completed_step_index + 1}:"
    start = None
    end = len(messages)
    for i, m in enumerate(messages):
        content = m.content if isinstance(m.content, str) else ""
        if marker in content and start is None:
            start = i
        elif start is not None and (next_marker in content or content.startswith("[AUTO]")):
            end = i
            break
    if start is None:
        return messages
    summary_msg = Message.user(f"[Step {completed_step_index} done: {summary}]")
    return messages[:start] + [summary_msg] + messages[end:]
```

**Step 3: Wire into `_run_auto_step` in engine.py** — after `step.mark_done()`, call `compress_step_messages()` on `self.messages`.

**Step 4: Run — PASS**

**Step 5: Commit**

```bash
git commit -am "feat: compress completed auto-execute steps to preserve context"
```

---

## Task 11: Health monitoring integration

**Files:**
- Modify: `godot_agent/runtime/engine.py`
- Test: `tests/runtime/test_engine.py`

**Step 1: Write the test**

```python
def test_engine_has_check_health():
    from godot_agent.runtime.engine import ConversationEngine
    assert hasattr(ConversationEngine, '_check_auto_health')
```

**Step 2: Implement `_check_auto_health()` in engine.py**

```python
def _check_auto_health(self) -> ContextHealth:
    from godot_agent.runtime.context_health import ContextHealth
    from godot_agent.runtime.context_manager import estimate_message_tokens
    total_tokens = sum(estimate_message_tokens(m) for m in self.messages)
    usage_ratio = total_tokens / 1050000
    return ContextHealth(
        token_usage_ratio=usage_ratio,
        consecutive_errors=getattr(self, '_auto_consecutive_errors', 0),
        tool_success_rate=getattr(self, '_auto_tool_success_rate', 1.0),
        rounds_since_compact=getattr(self, '_auto_rounds_since_compact', 0),
    )
```

Wire into `_run_auto_step()`: check health before each step. If `should_pause`, stop and report. If `should_compact`, run `smart_compact()`.

**Step 3: Run — PASS**

**Step 4: Commit**

```bash
git commit -am "feat: integrate health monitoring into auto-execute loop"
```

---

## Task 12: TUI commands table + /auto help

**Files:**
- Modify: `godot_agent/tui/display.py`
- Modify: `godot_agent/cli/commands.py`

**Step 1: Add /auto to commands table in display.py**

```python
# In commands_table(), add before /version:
t.add_row("/auto <request>", "plan, approve, and auto-execute a task")
t.add_row("/status", "show current plan progress (during /auto)")
```

**Step 2: Run full suite — PASS**

**Step 3: Commit**

```bash
git commit -am "feat: add /auto to help commands and wire /status for plan display"
```

---

## Task 13: Full integration test

**Files:**
- Test: `tests/test_auto_flow.py`

**Step 1: Write integration test**

```python
# tests/test_auto_flow.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from godot_agent.runtime.execution_plan import PlanStep, ExecutionPlan
from godot_agent.runtime.context_health import ContextHealth

def test_plan_approve_execute_roundtrip():
    """Verify plan creation → approve → step execution → completion."""
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"]),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"]),
    ], risk="low")
    # Approve all
    for s in plan.steps:
        s.status = "approved"
    assert len(plan.approved_steps) == 2
    # Simulate execution
    plan.steps[0].mark_done("+45 lines")
    assert plan.done_count == 1
    assert plan.current_step.index == 2

def test_plan_skip_step():
    plan = ExecutionPlan(title="Test", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="approved"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="skipped"),
        PlanStep(index=3, action="create", target="C", files=["c.gd"], status="approved"),
    ], risk="low")
    assert plan.total_actionable == 2  # skipped not counted

def test_health_triggers_compact():
    h = ContextHealth(token_usage_ratio=0.65, rounds_since_compact=6)
    assert h.should_compact
    assert not h.should_pause

def test_serialization_full_cycle():
    plan = ExecutionPlan(title="Full", steps=[
        PlanStep(index=1, action="create", target="A", files=["a.gd"], status="done", summary="ok"),
        PlanStep(index=2, action="modify", target="B", files=["b.gd"], status="approved"),
    ], risk="medium")
    data = plan.to_dict()
    restored = ExecutionPlan.from_dict(data)
    assert restored.done_count == 1
    assert len(restored.approved_steps) == 1
```

**Step 2: Run full suite**

```bash
cd ~/projects/god-code && .venv/bin/python -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git commit -am "test: add integration tests for /auto flow"
```

---

## Task 14: Version bump + final test run

**Step 1: Update version**

```bash
# pyproject.toml: version = "0.9.0"
```

**Step 2: Run full suites**

```bash
cd ~/projects/god-code && .venv/bin/python -m pytest tests/ -v
```

**Step 3: Sync landing page**

```bash
cd ~/projects/god-code-site
# Update hero-badge, stats, add /auto to terminal demo
npx astro build && npx wrangler pages deploy dist --project-name god-code-site
```

**Step 4: Update backend version**

```bash
cd ~/projects/god-code-api
# wrangler.toml: LATEST_VERSION = "0.9.0"
npx wrangler deploy
```

**Step 5: Commit and push all 3 repos**

```bash
cd ~/projects/god-code && git commit -am "release: v0.9.0" && git push
cd ~/projects/god-code-api && git commit -am "chore: update LATEST_VERSION to 0.9.0" && git push
cd ~/projects/god-code-site && git commit -am "chore: sync landing page for v0.9.0" && git push
```

---

## Summary

| Task | Deliverable | Files |
|------|-------------|-------|
| 1 | ExecutionPlan dataclass | `runtime/execution_plan.py` |
| 2 | Tool result truncation | `runtime/context_manager.py`, `runtime/engine.py` |
| 3 | Report pruning | `runtime/context_manager.py` |
| 4 | Context health monitor | `runtime/context_health.py` |
| 5 | TUI plan display + status | `tui/display.py` |
| 6 | System prompt proactive rules | `prompts/assembler.py` |
| 7 | Permission bypass for auto | `security/hooks.py`, `security/policies.py` |
| 8 | Session handoff | `runtime/session.py` |
| 9 | `/auto` command + engine flow | `cli/commands.py`, `runtime/engine.py` |
| 10 | Step compression | `runtime/context_manager.py`, `runtime/engine.py` |
| 11 | Health monitoring integration | `runtime/engine.py` |
| 12 | TUI /auto help | `tui/display.py`, `cli/commands.py` |
| 13 | Integration tests | `tests/test_auto_flow.py` |
| 14 | Version bump + 3-repo sync | `pyproject.toml`, landing page, API |

### Dependencies

```
Task 1 ──→ Task 5, 8, 9, 10, 13
Task 2 ──→ Task 9
Task 3 ──→ Task 9
Task 4 ──→ Task 11
Task 6 ──→ Task 9
Task 7 ──→ Task 9
Task 9 ──→ Task 10, 11, 12
All ────→ Task 13 → Task 14
```

Tasks 1-8 can be parallelized (no interdependencies). Task 9 is the integration point. Tasks 10-12 build on 9. Task 13-14 are final.

### Total: 14 tasks across 2 repos

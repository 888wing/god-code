# Interactive UX Redesign — Smart Agent Flow

**Date**: 2026-04-06
**Status**: Approved
**Goal**: One command (`/auto`) that understands, plans, gets approval, executes to completion, and stays healthy across long sessions.

## Core Principle

Replace 3 separate features (proactive questions + plan mode + autonomous mode) with **one unified flow**. The agent decides internally when to ask, when to plan, and when to execute. The user gives direction and approves the plan — everything else is automatic.

---

## `/auto` — Smart Agent Flow

### Phase 1: UNDERSTAND (1 round)

Agent scans codebase + design memory, then decides:
- If scope is clear → skip to Phase 2
- If ambiguous → ask 1-2 targeted questions (multi-choice preferred)
- If design memory conflicts with request → surface the conflict

**System prompt injection for this phase:**
```
Scan the project and assess whether the request is clear enough to plan.
Ask at most 2 questions if:
- The scope is ambiguous (could mean 2+ fundamentally different things)
- A critical implementation choice exists (state machine vs behavior tree, etc.)
- The request conflicts with design memory
Do NOT ask if:
- The scope is obvious from context
- You have enough information to produce a concrete plan
- The question is about a minor detail you can decide yourself
```

**Key**: Questions are asked as part of the agent's text response, not via engine checkpoints. This keeps the flow natural — the user answers in the next message, agent proceeds to Phase 2.

### Phase 2: PLAN (1 round)

Agent outputs a structured plan. Format enforced via system prompt:

```
### Plan: [title]

**Scope**: [N] files | **Risk**: low/medium/high | **Steps**: [N]

1. [action verb] [target] — [one-line description]
   Files: `path/file.gd`

2. [action verb] [target] — [one-line description]
   Files: `path/scene.tscn`, `path/script.gd`

3. ...

Risks: [if any]
```

**User responds with one of:**
- `approve` or `go` → execute all steps
- `skip 3` → execute all except step 3
- `add: also do X` → agent appends a step and re-shows plan
- `cancel` → abort

**Plan storage**: Stored on `engine.current_plan: ExecutionPlan` (not in message list). Survives across rounds but doesn't bloat context.

```python
@dataclass
class PlanStep:
    index: int
    action: str         # create, modify, delete, configure, validate
    target: str         # human-readable: "boss state machine base class"
    files: list[str]    # paths
    status: str = "pending"  # pending | approved | skipped | running | done | failed
    summary: str = ""   # filled after completion: "+45 lines, validated OK"

@dataclass
class ExecutionPlan:
    title: str
    steps: list[PlanStep]
    risk: str           # low, medium, high
    created_at: str     # ISO timestamp
```

### Phase 3: EXECUTE (N rounds, fully automatic)

Engine switches to apply mode internally and executes approved steps sequentially.

**Status line** (always visible, one line, updates in-place):
```
⚡ Step 2/5: editing boss_phase_spread.gd...
```

**`/status` command** expands to full Rich panel:
```
┌─ Plan: Add 3-phase boss system ───────────────────┐
│ ✅ 1. Create BossStateMachine      [2 files, +98]  │
│ 🔄 2. Implement phase scripts      [editing...]    │
│ ⏳ 3. Create boss scene                            │
│ ⏳ 4. Wire into spawner                            │
│ ── 5. Validate (skipped)                           │
│                                                     │
│ Progress: 1/4 | Tokens: 8,200 | Time: 1m 24s      │
└─────────────────────────────────────────────────────┘
```

**Permission bypass during execute:**

| Check | Behavior |
|-------|----------|
| Read-before-write | Auto-read silently, then write |
| Protected paths | Warn in log, allow |
| Risk: MEDIUM/HIGH | Allow + log |
| Risk: CRITICAL | Stop and ask user |
| Quality gate fail | Auto-retry fix (max 3x per step) |
| 3x consecutive failures | Stop, show report, ask user |

**Step completion flow:**
1. Execute step's tool calls
2. Run quality gate on modified files
3. If pass → mark step done, compress step context, move to next
4. If fail → auto-fix attempt (up to 3x) → still fail → pause

**User can type at any time during execution:**
- Any input → pause after current step finishes, show progress, wait for instruction
- `/status` → show full plan panel without pausing
- `/cancel` → stop execution, keep completed work

### Phase 4: REPORT

After all steps complete (or stopped):

```
┌─ Done ─────────────────────────────────────────────┐
│ Plan: Add 3-phase boss system                       │
│ Steps: 4/4 complete | 1 skipped                     │
│ Files: 3 created, 2 modified                        │
│ Validation: passed                                  │
│ Tokens: 18,200 | Cost: $0.05 | Time: 3m 12s        │
└─────────────────────────────────────────────────────┘
```

Auto-updates:
- Design memory: if new systems/patterns were created
- Changeset: saved to session for `/resume`
- Plan status: saved to session for `/resume`

---

## Context Protection Layer

### Problem
`/auto` can run 20+ tool rounds. Without protection, context bloats and quality degrades.

### Solution: 4 mechanisms

#### 1. Tool Result Truncation

```python
MAX_TOOL_RESULT_CHARS = 2000

def truncate_tool_result(content: str) -> str:
    """Keep first 1000 + last 500 chars, insert [...truncated N chars...]."""
    if len(content) <= MAX_TOOL_RESULT_CHARS:
        return content
    head = content[:1200]
    tail = content[-500:]
    omitted = len(content) - 1700
    return f"{head}\n[...truncated {omitted} chars...]\n{tail}"
```

Applied in `_execute_pending_tools()` before appending tool result to messages.

#### 2. Step Completion Compression

When a plan step completes, replace all its tool results + quality reports with a single summary:

```python
def compress_completed_step(self, step: PlanStep):
    """Replace step's messages with 1-line summary."""
    # Find messages from this step's execution
    # Replace with: "[Step 2 done: modified boss_phase_spread.gd +45 lines, validated OK]"
    # Keeps recent context clean for next step
```

This is the key innovation for `/auto` — each completed step shrinks to ~50 tokens instead of accumulating 2000+ tokens of tool results.

#### 3. Report Pruning

```python
MAX_QUALITY_REPORTS_IN_CONTEXT = 2  # Only keep latest 2

def prune_old_reports(self):
    """Remove quality/reviewer/playtest reports older than the last 2."""
    # Scan messages for [SYSTEM] Quality gate / Reviewer / Playtest
    # Keep most recent 2, remove older ones
```

#### 4. Health Monitor

```python
@dataclass
class ContextHealth:
    token_usage_ratio: float     # 0.0 - 1.0
    rounds_since_compact: int
    consecutive_errors: int       # Same error 3+ times = stuck
    tool_success_rate: float      # Below 50% = something wrong
    steps_completed: int
    steps_remaining: int

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

**On `should_pause`**: Stop execution, show health report, ask user.
**On `should_compact`**: Run mini-compact (more aggressive than standard 75% threshold).

---

## Session Handoff (Cross-Session Continuity)

### Enhanced SessionRecord

```python
@dataclass
class SessionRecord:
    # ... existing fields ...

    # NEW: execution state
    changeset_read: list[str]       # files read this session
    changeset_modified: list[str]   # files modified this session
    last_plan: dict | None          # ExecutionPlan serialized
    completed_steps: list[str]      # "Step 1: created boss_state_machine.gd (+98 lines)"
```

### `/resume` Behavior

On resume, inject a context restoration message:

```
[SYSTEM] Restored session context:
- Previous plan: "Add 3-phase boss system" (4/5 steps complete)
- Files modified last session: boss_state_machine.gd, boss_phase_spread.gd, ...
- Last step completed: Step 4 (wire into spawner)
- Remaining: Step 5 (validate)

Design memory is current. Changeset has been restored.
```

User can then:
- Continue where they left off: "continue the plan"
- Start something new: just type a new request
- `/status` to see the restored plan state

---

## Proactive Questioning (Simplified)

Instead of complex engine-level checkpoint gates, proactive questioning is handled entirely through the system prompt in Phase 1 (UNDERSTAND). The agent's own intelligence decides when to ask.

**Additional system prompt rules for ALL modes (not just /auto):**

```
## When to Pause and Ask

Before making changes, briefly assess scope. If your plan would:
- Modify 5+ files → state the scope and ask "proceed?"
- Delete anything → list what will be removed and ask "confirm?"
- Conflict with design memory → quote the conflict and ask

When the user says something vague like "fix the UI" or "improve performance":
- List what you found and ask which to address
- Do NOT guess and proceed on all of them
```

This replaces the engine-level `ProactiveCheckpoint` class from the original design — simpler, uses LLM intelligence instead of hardcoded rules.

---

## Implementation Plan

| Phase | Deliverable | Effort | Files |
|-------|-------------|--------|-------|
| **1** | ExecutionPlan dataclass + PlanStep | 1h | `runtime/execution_plan.py` |
| **2** | `/auto` command parsing + Phase 1-2 (understand + plan) | 3h | `cli/commands.py`, `prompts/assembler.py` |
| **3** | Phase 3 execute loop + status line + /status panel | 4h | `runtime/engine.py`, `tui/display.py` |
| **4** | Tool result truncation + step compression | 2h | `runtime/context_manager.py`, `runtime/engine.py` |
| **5** | Health monitor + auto-pause on degradation | 2h | `runtime/context_manager.py` |
| **6** | Permission bypass for auto-execute (auto-read, allow HIGH) | 2h | `security/hooks.py`, `security/policies.py` |
| **7** | Session handoff (changeset + plan in SessionRecord) | 2h | `runtime/session.py` |
| **8** | System prompt proactive rules (all modes) | 1h | `prompts/assembler.py` |
| **9** | Report pruning + mini-compact during execution | 2h | `runtime/context_manager.py` |
| **10** | Testing + integration | 3h | `tests/` |

**Total: ~22h across 10 phases**

**Dependencies:**
```
Phase 1 → Phase 2 → Phase 3 (core flow)
Phase 4 + 5 + 9 (context protection, parallel-safe)
Phase 6 (permissions, independent)
Phase 7 (session, independent)
Phase 8 (prompts, independent)
Phase 10 waits for all
```

Phases 4-9 can run in parallel after Phase 3.

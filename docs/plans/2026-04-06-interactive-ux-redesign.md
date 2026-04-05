# Interactive UX Redesign — Proactive Agent, Structured Plans, Autonomous Mode

**Date**: 2026-04-06
**Status**: Design
**Goal**: Make god-code feel like an intelligent collaborator, not a passive tool executor.

## Problem Statement

god-code currently has three UX gaps:

1. **The agent never asks questions** — the system prompt doesn't instruct the LLM to clarify ambiguity, confirm scope, or suggest alternatives. The only proactive checkpoint is gameplay intent (one narrow trigger). Safety enforcement is done by silently rejecting tool calls, which the LLM retries or gives up on.

2. **Plan mode is just "read-only mode"** — there's no structured plan output, no step approval, no plan-to-execution transition. Users get a text wall and must manually copy-paste instructions.

3. **No autonomous mode** — whether you're fixing a typo or building a boss system, every operation goes through the same permission pipeline. There's no way to say "I trust you, just do it."

## Design

### A. Proactive Questioning System

#### A1. System Prompt Injection — "When to Ask"

Add a `_proactive_rules_section()` to `prompts/assembler.py` that injects context-aware questioning rules:

```
## When to Ask Before Acting

You MUST pause and ask the user before proceeding when:

1. **Ambiguous scope**: The request could affect 1 file or 20. Ask which.
   Example: "fix the UI" → "Which UI? I see HUD, MainMenu, and PauseScreen."

2. **Large blast radius**: Your plan would modify 5+ files. Confirm the scope.
   Example: "This will change 8 files across 3 directories. Proceed?"

3. **Destructive operations**: Deleting files, removing nodes, resetting state.
   Example: "This will remove the EnemySpawner node and its 3 children. Confirm?"

4. **Architecture decisions**: Creating new systems, choosing patterns, adding autoloads.
   Example: "Should I use a state machine or behavior tree for this AI?"

5. **Conflicting with design memory**: The request contradicts established rules.
   Example: "Design memory says 'no physics-based movement', but you're asking for RigidBody2D."

6. **Missing information**: You need a detail the user hasn't provided.
   Example: "What resolution should the sprite be? Design memory says 64x64."

You SHOULD proceed without asking when:
- The scope is clear and contained (1-3 files)
- The request matches existing patterns in the codebase
- You have all the information needed
- The change is easily reversible (edit, not delete)
```

#### A2. Engine-Level Proactive Checkpoints

Add checkpoint hooks in `engine.py` that trigger BEFORE tool execution:

```python
class ProactiveCheckpoint:
    """A question the engine wants to ask the user before proceeding."""
    question: str
    options: list[str] | None = None  # None = free text
    context: str = ""
    skip_label: str = "Proceed anyway"

# New engine method
async def _check_proactive_gates(self, response: Message) -> ProactiveCheckpoint | None:
    """Analyze model response before executing tools. Return checkpoint if needed."""

    # Gate 1: Blast radius check
    tool_count = len(response.tool_calls or [])
    write_tools = [tc for tc in (response.tool_calls or []) if not self.registry.get(tc.name).is_read_only()]
    if len(write_tools) >= 5 and self.mode != "autonomous":
        return ProactiveCheckpoint(
            question=f"About to modify {len(write_tools)} files. Proceed?",
            options=["Yes, proceed", "Show me the plan first", "Cancel"],
        )

    # Gate 2: Mode mismatch
    if self.mode == "plan" and write_tools:
        return ProactiveCheckpoint(
            question="You're in plan mode but the request implies changes. Switch to apply mode?",
            options=["Switch to apply", "Stay in plan", "Cancel"],
        )

    # Gate 3: Destructive operations (delete, remove, reset)
    destructive = [tc for tc in write_tools if "delete" in tc.name or "remove" in tc.name]
    if destructive:
        return ProactiveCheckpoint(
            question=f"This includes {len(destructive)} destructive operations. Confirm?",
            options=["Yes, delete", "Show details", "Cancel"],
        )

    return None  # No checkpoint needed
```

#### A3. TUI Checkpoint Display

New `display.py` method for inline checkpoints:

```python
def proactive_checkpoint(self, checkpoint: ProactiveCheckpoint) -> str:
    """Display a checkpoint panel and return user's choice."""
    # Rich Panel with question + options
    # Inline in the chat flow, not a separate menu
    # Returns selected option text or user's free text
```

### B. Plan Mode Redesign — Structured Plans

#### B1. Plan Output Format

When in plan mode, the system prompt instructs the LLM to output structured plans:

```
## Plan Mode Output Format

When in plan mode, output plans in this exact format:

### Plan: [title]

**Scope**: [number] files | **Risk**: [low/medium/high] | **Estimated tools**: [count]

1. **[action verb] [target]** — [description]
   - Files: `path/to/file.gd`, `path/to/scene.tscn`
   - Risk: low
   - Reversible: yes

2. **[action verb] [target]** — [description]
   - Files: `path/to/other.gd`
   - Risk: medium
   - Reversible: yes

3. ...

**Dependencies**: Step 2 requires Step 1.
**Risks**: [any risks or concerns]
**Alternative approaches**: [if applicable]
```

#### B2. Plan Storage and Execution

```python
@dataclass
class PlanStep:
    index: int
    action: str          # "create", "modify", "delete", "configure"
    target: str          # human-readable target
    description: str
    files: list[str]
    risk: str            # low, medium, high
    status: str = "pending"  # pending, approved, rejected, completed, failed

@dataclass
class ExecutionPlan:
    title: str
    steps: list[PlanStep]
    scope_files: int
    overall_risk: str

    @property
    def approved_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "approved"]
```

#### B3. New Commands

```
/plan               — show current plan (if any)
/plan approve       — approve all pending steps
/plan approve 1,3,5 — approve specific steps
/plan reject 2      — reject a step
/plan execute       — switch to apply mode and execute approved steps
/plan clear         — discard current plan
```

#### B4. Plan-to-Execution Flow

```
User: "refactor the enemy system to use state machines"
                    ↓
[Plan mode] Agent inspects codebase, outputs structured plan
                    ↓
/plan → User reviews plan (5 steps shown)
/plan reject 4 → User rejects optional step
/plan approve → Approve remaining 4 steps
/plan execute → Engine switches to apply mode, executes steps 1→2→3→5
                    ↓
After each step: checkpoint
  "Step 1 complete (create StateMachine base). Continue to Step 2?"
                    ↓
[All steps done] → Auto quality gate → Report
```

### C. Autonomous Mode

#### C1. Mode Definition

Add a 6th interaction mode: `autonomous` (or `/turbo`).

```python
# In modes.py
ModeSpec(
    name="autonomous",
    label="Autonomous",
    description="Full tool access with minimal confirmations. Agent works until done.",
    allowed_tools=APPLY_TOOLS | {"analyze_screenshot", "score_screenshot"},
    system_hint=(
        "You are in AUTONOMOUS mode. Execute the task completely without pausing. "
        "Chain tool calls aggressively. Fix validation errors immediately. "
        "Only stop to ask the user if you encounter a genuine ambiguity that "
        "could lead to two fundamentally different implementations."
    ),
)
```

#### C2. Permission Bypass Rules

In autonomous mode, the permission pipeline changes:

| Check | Normal Mode | Autonomous Mode |
|-------|-------------|-----------------|
| Mode tool allowlist | Enforced | Same as apply |
| Read-before-write hook | Block | Auto-read then write |
| Protected path hook | Block | Warn but allow |
| Risk: MEDIUM | Allow | Allow |
| Risk: HIGH | Allow (apply/fix only) | Allow + log |
| Risk: CRITICAL | Block always | Block always (never bypass) |
| Quality gate failures | Inject report | Auto-retry fix (up to 3x) |
| Round limit | 20 | 40 |
| Blast radius checkpoint | Prompt user | Skip |

#### C3. Auto-Read-Before-Write

The biggest friction in normal mode is the read-before-write hook. In autonomous mode:

```python
# In hooks.py
class AutoReadBeforeWriteHook:
    """In autonomous mode, auto-read the file before allowing write."""

    async def pre_execute(self, tool, input, context):
        if context.mode != "autonomous":
            return RequireReadBeforeWriteHook().pre_execute(tool, input, context)

        # Auto-read the file if not yet read
        path = getattr(input, "path", None)
        if path and path not in context.changeset.read_files:
            read_tool = context.registry.get("read_file")
            if read_tool:
                await read_tool.execute(read_tool.Input(path=path))
                context.changeset.read_files.add(str(Path(path).resolve()))
        return HookResult()  # Allow
```

#### C4. Activation and Safety

```
/mode autonomous    — enter autonomous mode
/turbo              — alias for /mode autonomous
```

**Safety rails that NEVER change regardless of mode:**
1. CRITICAL risk operations always blocked (rm -rf, git reset --hard, etc.)
2. Project root containment always enforced
3. Round limit enforced (40 in autonomous, 20 otherwise)
4. Token budget enforced
5. `.godot` import database never directly modified

**Exit conditions:**
- User types anything → autonomous pauses, shows progress, waits
- Round limit reached → report progress, ask to continue
- 3 consecutive quality gate failures → stop and ask

### D. Implementation Priority

| Phase | Items | Effort | Impact |
|-------|-------|--------|--------|
| **D1** | System prompt proactive rules (A1) + mode mismatch detection (A2 Gate 2) | 2h | High — agent starts asking smart questions |
| **D2** | Autonomous mode definition (C1) + permission bypass (C2) + auto-read (C3) | 4h | High — removes friction for experienced users |
| **D3** | Structured plan output format (B1) + plan storage (B2) | 3h | Medium — better plan mode UX |
| **D4** | Plan commands (B3) + plan-to-execution flow (B4) | 4h | Medium — complete plan workflow |
| **D5** | Blast radius checkpoint (A2 Gate 1) + destructive checkpoint (A2 Gate 3) | 2h | Medium — safety improvement |
| **D6** | TUI checkpoint display (A3) | 2h | Medium — visual polish |

### E. Summary

```
Before:
  User → Request → [Agent blindly executes or silently fails] → Result

After:
  User → Request
    ↓
  [Proactive check: scope clear? blast radius? mode match?]
    ↓ (if unclear)
  Agent: "I see 3 possible interpretations. Which do you mean?"
    ↓ (if clear)
  [Execute in current mode]
    ↓ plan mode                    ↓ apply mode               ↓ autonomous mode
  Structured plan output          Normal execution            Aggressive chaining
  /plan approve → /plan execute   Quality gates + review      Auto-fix, minimal pauses
                                                              Only stops on ambiguity
```

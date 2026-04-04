# God Code v0.7: Demo-Ready Upgrade Plan (Revised)

**Date**: 2026-04-04
**Goal**: Upgrade god-code from "strong prototype assistant" to "agent that can reliably deliver and verify polished 2D demo slices"
**Scope**: 4 workstreams, 2 foundational refactors, 2 additive capability layers
**Prerequisite**: Current v0.6.1 runtime harness + skills + computer-use changes merged first

---

## Executive Summary

God-code already has more than the original collision/physics baseline: it now ships with multiple gameplay skills, a quality gate, reviewer/playtest passes, design memory, visual regression helpers, and a multi-agent dispatcher.

The remaining gap is not "more prompt text". The real blockers to stable demo output are:

1. **Runtime evidence is still too synthetic**
   The playtest harness mostly evaluates an in-memory `RuntimeSnapshot`, not authoritative state captured from a real editor/runtime session.
2. **Scene editing is string-only**
   The `.tscn` parser/writer currently treats node properties as raw strings, which makes higher-level UI/audio planning brittle.
3. **Presentation-layer guidance is not wired into deterministic checks**
   UI and audio scaffolding are useful only if they emit values the current toolchain can write and the quality gate can audit.
4. **New tools must reach the main agent loop**
   Registering a tool in `cli.py` or exposing it over MCP is not enough; it must also be available through mode-level and agent-level allowlists.

Therefore the v0.7 plan should prioritize **verification infrastructure first**, then build UI/audio/demo helpers on top of that foundation.

---

## Success Criteria

God-code can be considered "demo-ready" for 2D projects when all of the following are true:

1. The agent can make scene/script changes and prove them with **live or headless runtime evidence**, not only synthetic harness state.
2. The agent can express common UI/audio scene edits through **typed scene serialization helpers** without hand-authoring raw Godot strings for every property.
3. The quality gate, reviewer, and playtest analyst can all surface **presentation-layer regressions** such as broken UI layout, missing theme/audio wiring, and invalid scene configuration.
4. Auto-generated playtest coverage is treated as **advisory baseline coverage**, not false proof of correctness.
5. All new tools are usable from the main CLI agent flow: `apply`, `plan`, `review`, and `fix` as appropriate.

---

## Non-Goals

- Generating final art, music, or voice content inside god-code itself
- Replacing hand-authored end-to-end scenarios for boss fights, narrative sequences, or tightly scripted demos
- Broadening scope to 3D-specific demo workflows in this phase

---

## Workstream 1: Runtime Evidence Bridge Hardening

### Problem

`run_playtest_harness()` currently verifies `required_nodes`, `required_events`, `required_inputs`, and `snapshot.errors` against `RuntimeSnapshot`. That is useful, but it is not sufficient evidence for "stable demo output" because the current bridge data can be synthetic or partially injected by tools rather than sourced from an actual running project.

### Target Outcome

Every playtest/reviewer verdict should be able to distinguish:

- **live editor/runtime evidence**
- **headless capture evidence**
- **synthetic harness evidence**

Only the first two should be allowed to fully substantiate a demo-readiness claim.

### Design

Extend the runtime bridge model so evidence quality is explicit instead of implicit.

```python
@dataclass
class RuntimeSnapshot:
    active_scene: str = ""
    current_tick: int = 0
    nodes: list[RuntimeNodeState] = field(default_factory=list)
    events: list[RuntimeEvent] = field(default_factory=list)
    input_actions: list[str] = field(default_factory=list)
    active_inputs: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    fixtures: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)
    source: str = "synthetic"          # synthetic | live_editor | headless
    evidence_level: str = "low"        # low | medium | high
    bridge_connected: bool = False
    captured_at: str = ""
```

### Required Changes

1. **Bridge metadata**
   Add `source`, `evidence_level`, `bridge_connected`, and `captured_at` to `RuntimeSnapshot`.

2. **Authoritative ingestion path**
   Update editor/runtime bridge integration so snapshots loaded from a running Godot session are marked `source="live_editor"` and `evidence_level="high"`.

3. **Headless fallback semantics**
   Headless screenshot/run-scene flows should be marked `source="headless"` and `evidence_level="medium"`.

4. **Synthetic evidence downgrade**
   If playtest results are based only on synthetic harness data, generated scenarios must not produce a strong "PASS" signal for demo readiness. At minimum, they should be capped to `PARTIAL` or explicitly labeled "synthetic-only evidence".

5. **Reviewer integration**
   The reviewer and gameplay reviewer should render evidence quality, not just scenario outcome.

### Implementation

**Files to modify:**
- `godot_agent/runtime/runtime_bridge.py`
- `godot_agent/tools/editor_bridge.py`
- `godot_agent/runtime/playtest_harness.py`
- `godot_agent/runtime/gameplay_reviewer.py`
- `godot_agent/runtime/reviewer.py`
- `godot_agent/runtime/engine.py`

**Tests to add/update:**
- `tests/runtime/test_runtime_bridge.py`
- `tests/runtime/test_playtest_harness.py`
- `tests/runtime/test_reviewer.py`

### Verification

```bash
pytest tests/runtime/test_runtime_bridge.py -v
pytest tests/runtime/test_playtest_harness.py -v
pytest tests/runtime/test_reviewer.py -v
```

### Risk: Medium

This workstream changes verdict semantics, but it is the main blocker for credible demo-readiness claims.

---

## Workstream 2: Typed TSCN Property Serialization

### Problem

The current `.tscn` parser stores node properties as `dict[str, str]`, and scene mutation tools also expect serialized Godot strings. That is fine for low-level edits, but it is the wrong substrate for UI presets, audio scaffolds, and structured validators.

### Target Outcome

Keep raw-string compatibility, but add a typed layer for the subset of Godot values god-code needs to plan and write common demo features.

### Design

Create a small Variant codec instead of trying to solve all Godot serialization at once.

```python
GodotScalar = str | int | float | bool
GodotValue = GodotScalar | dict[str, Any] | list[Any]

def parse_variant(text: str) -> GodotValue: ...
def serialize_variant(value: GodotValue) -> str: ...
```

### Supported Types in v0.7

Focus only on values needed by the planned advisors and validators:

- `bool`
- `int`, `float`
- quoted `String`
- `StringName` literals such as `&"Music"`
- `Vector2(...)`
- `Color(...)`
- small dictionaries used by advisors before serialization
- small lists for array-like properties when needed

Unsupported values should safely fall back to raw strings.

### Required Changes

1. **Variant codec**
   Add a helper module for parsing/serializing the supported subset.

2. **Parser helpers**
   Keep raw property strings in `scene_parser.py`, but add typed helper accessors so validators do not have to re-implement parsing.

3. **Writer helpers**
   Update scene writing utilities so higher-level tools can pass typed values and rely on `serialize_variant()`.

4. **Tool input widening**
   Where safe, allow scene tools to accept JSON-like property payloads instead of only `dict[str, str]`.

5. **Backward compatibility**
   Existing callers that already pass serialized strings should continue to work.

### Implementation

**Files to create:**
- `godot_agent/godot/variant_codec.py`

**Files to modify:**
- `godot_agent/godot/scene_parser.py`
- `godot_agent/godot/scene_writer.py`
- `godot_agent/tools/scene_tools.py`

**Tests to add/update:**
- `tests/godot/test_variant_codec.py`
- `tests/godot/test_scene_parser.py`
- `tests/tools/test_scene_tools.py`

### Verification

```bash
pytest tests/godot/test_variant_codec.py -v
pytest tests/godot/test_scene_parser.py -v
pytest tests/tools/test_scene_tools.py -v
```

### Risk: Medium

This is an internal refactor, but it unblocks every structured scene-planning feature in later workstreams.

---

## Workstream 3: Presentation Layer Advisors (UI + Audio)

### Problem

UI and audio are real demo-quality differentiators, but they should not be added as prompt-only knowledge. They need deterministic advisors, validators, and integration into the existing quality flow.

### Target Outcome

God-code can:

- scaffold common UI structures using serializable scene properties
- scaffold audio nodes and bus assignments with explicit validation
- surface UI/audio issues in quality gate and reviewer output

### Design

Build UI and audio support on top of Workstream 2 rather than bypassing it.

### 3A. UI Layout Advisor

Create `godot_agent/godot/ui_layout_advisor.py` with:

- `UILayoutConfig`
- `LAYOUT_PRESETS`
- `plan_ui_layout(pattern: str)`
- `validate_ui_layout(scene: TscnScene) -> list[str]`

Important constraint: advisor outputs must be **already serializable through the scene tools**. That means:

- `to_tscn_nodes()` must emit values that the updated scene tools can write directly
- validators must read via the typed property helpers, not assume `dict`/`int` objects already exist inside `scene.nodes`

### 3B. Audio Scaffolder

Create `godot_agent/godot/audio_scaffolder.py` with:

- `AudioNodeConfig`
- `AUDIO_PRESETS`
- `scaffold_audio_nodes(pattern: str)`
- `validate_audio_nodes(scene: TscnScene, project_root: Path) -> list[str]`

Audio validation should cover at least:

- missing `bus`
- missing `stream`
- unknown bus names when a custom bus such as `Music`, `SFX`, or `UI` is used

To support that, extend project-level parsing if needed so god-code can inspect available bus names from the project or default bus layout.

### 3C. Main-Agent Integration

New UI/audio tools must be integrated in all required layers:

- `godot_agent/tools/analysis_tools.py`
- `godot_agent/mcp_server.py`
- `godot_agent/cli.py`
- `godot_agent/runtime/modes.py`
- any affected role config via mode-derived allowlists

### 3D. Quality Gate / Reviewer Integration

If a changed `.tscn` contains Control-based UI or AudioStreamPlayer nodes, the quality gate and reviewer should run the corresponding validators automatically.

### Implementation

**Files to create:**
- `godot_agent/godot/ui_layout_advisor.py`
- `godot_agent/godot/audio_scaffolder.py`

**Files to modify:**
- `godot_agent/tools/analysis_tools.py`
- `godot_agent/mcp_server.py`
- `godot_agent/cli.py`
- `godot_agent/runtime/modes.py`
- `godot_agent/runtime/quality_gate.py`
- `godot_agent/runtime/reviewer.py`
- `godot_agent/prompts/godot_playbook.py`
- `godot_agent/godot/project.py` or a dedicated audio bus parser if required

**Tests to create/update:**
- `tests/godot/test_ui_layout_advisor.py`
- `tests/godot/test_audio_scaffolder.py`
- `tests/runtime/test_quality_gate.py`

### Verification

```bash
pytest tests/godot/test_ui_layout_advisor.py -v
pytest tests/godot/test_audio_scaffolder.py -v
pytest tests/runtime/test_quality_gate.py -v
```

### Risk: Low-Medium

The advisor logic itself is additive. The main risk is incomplete integration with the main agent flow, which is why allowlist and quality-gate wiring are part of this workstream rather than "follow-up tasks".

---

## Workstream 4: Scenario Coverage Expansion and Prompt-Layer Alignment

### Problem

The current repo has only a few hand-authored scenario specs, and demo-oriented prompt skills are still missing in UI/animation/scene-flow/state-management areas. However, expanding these layers only helps after runtime evidence and typed scene serialization are in place.

### Target Outcome

Auto-generated scenarios become a useful **coverage amplifier**, not a source of false confidence. New skills become useful **tool-routing hints**, not the primary mechanism for demo stability.

### Design

### 4A. Auto-Generated Baseline Scenarios

Add `generate_scenario_specs()` to `playtest_harness.py`, but revise the contract:

- generated specs are **in-memory only** in v0.7
- generated specs are marked as baseline/advisory metadata
- generated specs require live/headless runtime evidence to become strong signals
- generated specs never replace hand-authored end-to-end flows

Prefer extending `ScenarioSpec` explicitly instead of writing underscore-prefixed ad hoc JSON keys.

```python
@dataclass
class ScenarioSpec:
    ...
    source: str = "manual"          # manual | generated
    confidence: str = "high"        # low | medium | high
    evidence_policy: str = "advisory"  # advisory | require_live_for_pass
    source_scene: str = ""
```

### 4B. Skill Layer Expansion

After Workstreams 2 and 3 land, add the following skills:

- `ui_layout`
- `animation_pipeline`
- `scene_transition`
- `game_state`

These skills should:

- reference only tools that actually exist in the current mode/tool allowlists
- narrow tool scope as a hint, not a hard lockout
- reflect the current repo state instead of restating an outdated "only two skills" baseline

### 4C. Acceptance Semantics

Generated scenarios should follow these verdict rules:

- **PASS**: only if backed by live/headless evidence and assertions succeed
- **PARTIAL**: if assertions are based only on synthetic harness evidence
- **FAIL**: if assertions fail under any evidence type

### Implementation

**Files to modify:**
- `godot_agent/runtime/playtest_harness.py`
- `godot_agent/prompts/skill_library.py`
- `godot_agent/prompts/skill_selector.py`
- `godot_agent/runtime/gameplay_reviewer.py`

**Tests to create/update:**
- `tests/runtime/test_playtest_harness.py`
- `tests/prompts/test_skill_selector.py`

### Verification

```bash
pytest tests/runtime/test_playtest_harness.py -v
pytest tests/prompts/test_skill_selector.py -v
```

### Risk: Low-Medium

This workstream is useful, but it should be explicitly downstream of Workstreams 1 and 2.

---

## Integration Requirements

Every new tool or validator added in v0.7 must be checked against all of the following:

1. `build_registry()` registration
2. CLI mode allowlists in `godot_agent/runtime/modes.py`
3. role-scoped access derived from those modes in `godot_agent/agents/configs.py`
4. MCP exposure if the tool is meant to be externally callable
5. quality gate / reviewer / playtest analyst consumption where relevant

If any one of these is skipped, the feature is incomplete.

---

## Recommended Order

**Required order**: 1 -> 2 -> 3 -> 4

This is intentionally different from the earlier plan. The workstreams are **not** independent in practice:

- Workstream 1 is the verification foundation.
- Workstream 2 is the scene-editing foundation.
- Workstream 3 depends on Workstream 2.
- Workstream 4 depends on Workstreams 1 and 2, and benefits from Workstream 3.

Parallelization is still possible inside a phase:

- UI and audio sub-work in Workstream 3 can proceed in parallel after the typed property layer is available.
- Skill tests and scenario generation logic in Workstream 4 can proceed in parallel after the new verdict semantics are defined.

---

## Summary Table

| Workstream | Primary Outcome | Type | Risk | Blocking? |
|------------|-----------------|------|------|-----------|
| 1. Runtime Evidence Bridge | Credible demo verification | Foundation | Medium | Yes |
| 2. Typed TSCN Serialization | Writable structured scene planning | Foundation | Medium | Yes |
| 3. Presentation Advisors | UI/audio scaffolding + validators | Additive | Low-Med | After WS2 |
| 4. Scenario + Skill Alignment | Coverage expansion without false confidence | Additive | Low-Med | After WS1/WS2 |

---

## Final Acceptance Gate

After all 4 workstreams land:

```bash
# Full suite
pytest tests/ -v

# Focused verification
pytest \
  tests/runtime/test_runtime_bridge.py \
  tests/godot/test_variant_codec.py \
  tests/godot/test_ui_layout_advisor.py \
  tests/godot/test_audio_scaffolder.py \
  tests/runtime/test_playtest_harness.py \
  tests/prompts/test_skill_selector.py -v
```

### Demo-Readiness Smoke Exercise

Run a real workflow against a sample 2D project:

1. Ask god-code to add a pause menu with:
   - centered container layout
   - button minimum sizes
   - fade transition hook
   - UI click audio node
2. Require the resulting change set to pass:
   - Godot headless validation
   - scene/resource validation
   - UI validator
   - audio validator
   - reviewer pass
3. Require playtest evidence to include:
   - non-synthetic snapshot source
   - expected scene/UI nodes
   - screenshot or viewport artifact
   - no runtime errors

If the smoke exercise cannot be verified with real or headless evidence, the implementation is not yet demo-ready.

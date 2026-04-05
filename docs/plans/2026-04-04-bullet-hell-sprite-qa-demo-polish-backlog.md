# God Code: Bullet Hell, Sprite QA, And Demo Polish Backlog

**Date**: 2026-04-04
**Goal**: Close the most visible gap between "working prototype" and "credible 2D demo output" for genre-aware Godot projects.
**Scope**: `bullet_hell` template library, sprite acceptance gate, demo-quality playtest rubric
**Reference project**: `starfall_demo`

---

## Executive Summary

God Code already has:

- gameplay-intent inference
- profile-aware skills
- runtime harness primitives
- visual regression helpers
- design memory
- reviewer and playtest stages

The current gap is not basic Godot editing. The current gap is **quality shape**.

The `starfall_demo` review exposed three recurring failure classes:

1. enemy behavior for `bullet_hell` still trends toward ad-hoc scripted movement instead of a reusable pattern/phase system
2. sprite generation and post-processing can produce assets, but do not yet enforce a strict acceptance contract such as `64x64`, `#00FF00` cleanup, alpha correctness, and Godot import sanity
3. playtesting and review can prove "not obviously broken", but do not yet enforce demo-level pacing, feedback, readability, and presentation quality

This backlog turns those three weak points into explicit workstreams.

---

## Product Goal

For first-class 2D real-time genres, God Code should be able to:

1. infer that a project is `bullet_hell`
2. generate enemy systems from pattern templates instead of generic enemy-AI improvisation
3. reject sprites that do not meet project art constraints
4. distinguish prototype-grade output from demo-grade output during review and playtest

---

## Non-Goals

- universal enemy AI that works for every genre
- replacing hand-authored art direction
- guaranteeing final-commercial polish from a single pass
- broadening the same phase to 3D action, RTS, turn-based tactics, stealth-heavy AI, or multiplayer combat

---

## Workstream A: Bullet Hell Template Library

### Problem

The current `bullet_hell` direction is better than generic enemy-AI guessing, but still too prompt-shaped. The system can identify the genre, yet it does not have a strong internal library for:

- entry choreography
- movement patterns
- bullet patterns
- boss phases
- bullet cleanup
- density progression

This leaves the model too much freedom to produce shallow or repetitive patterns.

### Target Outcome

For `bullet_hell` projects, enemy generation should resolve into reusable gameplay building blocks instead of monolithic script logic.

### Core Design

Introduce genre-specific template families:

- `movement_pattern`
- `fire_pattern`
- `phase_transition`
- `wave_spec`
- `encounter_director`

These are not only prompt concepts. They should be represented in:

- skill guidance
- design memory
- generation scaffolds
- playtest contracts

### First Template Set

#### Movement Patterns

- `straight_drop`
- `sine_drift`
- `sweep_horizontal`
- `arc_entry`
- `enter_hold_exit`
- `waypoint_path`

#### Fire Patterns

- `single_shot`
- `aimed_burst`
- `fan_burst`
- `ring_burst`
- `spiral_stream`
- `sweeping_fan`

#### Phase Transitions

- `pause_and_telegraph`
- `clear_bullets`
- `invuln_transition`
- `pattern_swap`
- `hp_threshold_transition`

#### Wave Specs

- `staggered_line`
- `left_right_pincer`
- `escort_wave`
- `miniboss_intro`
- `boss_phase_sequence`

### Required Data Model

Add bullet-hell-specific profile fields under gameplay intent or a genre extension object:

```json
{
  "genre": "bullet_hell",
  "enemy_model": "scripted_patterns",
  "boss_model": "phase_based",
  "combat_profile": {
    "player_space_model": "free_2d_dodge",
    "density_curve": "ramp_up",
    "readability_target": "clear_dense",
    "bullet_cleanup_policy": "phase_transition_and_timeout",
    "phase_style": "telegraphed"
  }
}
```

### Required Changes

#### Files to modify

- `godot_agent/prompts/skill_library.py`
- `godot_agent/prompts/skill_selector.py`
- `godot_agent/prompts/assembler.py`
- `godot_agent/runtime/design_memory.py`
- `godot_agent/runtime/intent_resolver.py`
- `godot_agent/runtime/playtest_harness.py`
- `godot_agent/runtime/scenario_specs/`

#### New files to add

- `godot_agent/prompts/genre_templates.py`
- `godot_agent/runtime/scenario_specs/bullet_hell_wave_progression.json`
- `godot_agent/runtime/scenario_specs/bullet_hell_phase_transition.json`
- `godot_agent/runtime/scenario_specs/bullet_hell_pattern_readability.json`

### Acceptance Criteria

- bullet-hell enemy tasks consistently route to a pattern-first architecture
- generated plans mention movement, fire pattern, and phase behavior explicitly
- playtest scenarios can validate bullet cleanup and wave pacing
- reviewer output can flag "reactive chase AI" as a mismatch for `bullet_hell` profile

### Tests

- `tests/prompts/test_genre_templates.py`
- `tests/runtime/test_intent_resolver.py`
- `tests/runtime/test_playtest_harness.py`
- `tests/runtime/test_design_memory.py`

---

## Workstream B: Sprite QA And Acceptance Gate

### Problem

The current sprite pipeline can:

- generate
- key out backgrounds
- resize
- slice

But it does not yet decide whether the asset is acceptable for the project.

That means a sprite can still pass through even if it:

- is not `64x64`
- still contains `#00FF00`
- lacks transparency where required
- violates pixel-art expectations
- imports into Godot with the wrong apparent result

### Target Outcome

Sprite generation should become a gated pipeline:

`generate -> post-process -> QA -> accept or repair -> import`

### Asset Spec Model

Extend design memory or project asset settings to support:

```json
{
  "asset_spec": {
    "style": "pixel_art",
    "target_size": [64, 64],
    "background_key": "#00FF00",
    "alpha_required": true,
    "palette_mode": "restricted",
    "import_filter": "nearest",
    "allow_resize": false
  }
}
```

### QA Checks

#### File-level checks

- exact width and height
- alpha channel present when required
- count of remaining key-color pixels
- file format and save success

#### Style checks

- approximate palette cardinality
- edge softness or blur heuristics
- nearest-neighbor expectation compatibility

#### Import-level checks

- generated Godot import settings are sane
- viewport capture after import does not show green background
- baseline compare against expected silhouette or framing when available

### Failure Artifacts

For every generated sprite, store:

- `original.png`
- `keyed.png`
- `final.png`
- `mask.png`
- `qa.json`

If QA fails, return:

- failure reasons
- measured values
- candidate repair actions

### Required Changes

#### Files to modify

- `godot_agent/tools/image_gen.py`
- `godot_agent/tools/sprite_pipeline.py`
- `godot_agent/tools/runtime_harness.py`
- `godot_agent/runtime/design_memory.py`
- `godot_agent/runtime/intent_resolver.py`

#### New files to add

- `godot_agent/tools/sprite_qa.py`
- `godot_agent/runtime/scenario_specs/sprite_import_visibility.json`
- `godot_agent/runtime/scenario_specs/pixel_art_asset_acceptance.json`

### Acceptance Criteria

- sprites outside declared size fail QA
- residual `#00FF00` pixels fail QA
- missing alpha fails when `alpha_required=true`
- pixel-art projects get explicit warnings for blurry or over-smoothed output
- agent can explain why an asset was rejected instead of silently accepting it

### Tests

- `tests/tools/test_sprite_qa.py`
- `tests/tools/test_sprite_pipeline.py`
- `tests/tools/test_image_gen.py`
- `tests/runtime/test_design_memory.py`

---

## Workstream C: Demo Polish Rubric

### Problem

The current playtest system is strong enough to catch many technical failures, but it still does not express the difference between:

- prototype-level correctness
- demo-level presentation

As a result, output can pass basic checks while still feeling flat, under-signaled, or unfinished.

### Target Outcome

Introduce explicit demo-quality review and playtest rules that can mark results as:

- `pass`
- `partial`
- `warn`
- `fail`

based on presentation and feel criteria, not only functional correctness.

### Quality Target Model

Extend gameplay or project quality settings:

```json
{
  "quality_target": "demo",
  "polish_profile": {
    "combat_feedback": "required",
    "boss_transition": "required",
    "ui_readability": "required",
    "wave_pacing": "required",
    "juice_level": "moderate"
  }
}
```

### Demo Rubric Categories

#### Combat feedback

- hit flash present
- enemy death feedback present
- player damage feedback present
- bullet spawn telegraph or clarity present where appropriate

#### Encounter pacing

- wave escalation is visible
- boss phase transition is visible
- quiet vs dense moments are distinguishable

#### Readability

- bullet patterns are interpretable
- HUD remains legible during action
- visual clutter is below project-specific tolerance

#### Presentation

- title/menu language matches actual mechanics
- placeholder text or obsolete mechanic references are flagged
- scene transitions feel intentional rather than abrupt

### Required Changes

#### Files to modify

- `godot_agent/runtime/playtest_harness.py`
- `godot_agent/runtime/engine.py`
- `godot_agent/runtime/reviewer.py`
- `godot_agent/runtime/gameplay_reviewer.py`
- `godot_agent/tui/display.py`
- `godot_agent/runtime/design_memory.py`

#### New files to add

- `godot_agent/runtime/polish_rubric.py`
- `godot_agent/runtime/scenario_specs/demo_combat_feedback.json`
- `godot_agent/runtime/scenario_specs/demo_wave_pacing.json`
- `godot_agent/runtime/scenario_specs/demo_boss_transition.json`
- `godot_agent/runtime/scenario_specs/demo_ui_readability.json`

### Acceptance Criteria

- review output can distinguish "works" from "demo-ready"
- prototype-grade gameplay can receive warnings without producing false confidence
- bullet-hell demo scenarios validate wave progression and phase signaling
- obsolete or conflicting UX copy can be surfaced as presentation regressions

### Tests

- `tests/runtime/test_polish_rubric.py`
- `tests/runtime/test_reviewer.py`
- `tests/runtime/test_playtest_harness.py`
- `tests/tui/test_display.py`

---

## Cross-Cutting Work: TUI And Intent Integration

The three workstreams above should not stay hidden in backend logic. The TUI should surface the active constraints.

### Required TUI additions

- show `quality_target`
- show `asset_spec`
- show `combat_profile` summary for first-class genres
- display when results are only `prototype-safe` versus `demo-ready`

### Files to modify

- `godot_agent/cli.py`
- `godot_agent/tui/display.py`
- `godot_agent/tui/input_handler.py`

### Suggested commands

- `/intent`
- `/intent edit`
- `/quality`
- `/assetspec`

The `/quality` and `/assetspec` commands can initially be read-only if interactive editing is too much for the first pass.

---

## Delivery Order

### Batch 1: Asset And Quality Contracts

Deliver first:

- `asset_spec`
- `quality_target`
- design-memory persistence
- TUI visibility for those fields

Reason:

The rest of the system needs a clear contract before generation or review logic can become stricter.

### Batch 2: Sprite QA Gate

Deliver second:

- `sprite_qa.py`
- hard acceptance checks
- QA artifacts
- basic import verification

Reason:

This immediately addresses a concrete failure class and is bounded enough to stabilize early.

### Batch 3: Bullet Hell Template Library

Deliver third:

- template metadata
- prompt and skill upgrades
- bullet-hell scenario specs

Reason:

Pattern-first generation is easier to validate once quality and asset constraints are already modeled.

### Batch 4: Demo Polish Rubric

Deliver fourth:

- rubric model
- reviewer integration
- scenario-based polish warnings

Reason:

This layer builds on the first three and turns "technically acceptable" into "demo-quality aware".

---

## Validation Strategy

### Static validation

- intent resolution picks correct genre and quality contract
- asset specs round-trip through config and design memory
- template selection routes correctly for `bullet_hell`

### Runtime validation

- scenario specs can verify bullet cleanup and phase transitions
- sprite import checks can prove that green-screen remnants are gone
- playtest can return `warn` or `partial`, not only binary pass/fail

### Human-facing validation

- TUI clearly shows when the project is configured for `demo`
- reviewer language explains why a result feels unfinished
- users can see which asset constraints are active before generation

---

## Out Of Scope For This Phase

Do not force these into the same phase:

- `stealth_guard` full template library
- 3D action enemy systems
- RTS or multi-agent squad combat
- multiplayer combat validation
- automatic art-style grading against arbitrary reference packs

Those need separate domain models and would dilute the current 2D demo-quality goal.

---

## Definition Of Done

This backlog is complete when all of the following are true:

1. `bullet_hell` tasks no longer default to shallow generic enemy AI
2. generated sprites can be rejected for spec violations before import
3. demo-quality projects can receive presentation warnings even when they technically run
4. TUI makes the active quality and asset constraints visible
5. tests cover the new quality contracts and scenario behavior


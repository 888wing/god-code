# God Code Dogfooding Inventory

**Date**: 2026-04-05  
**Reference project**: `starfall_demo`  
**Purpose**: Separate what the recent demo-upgrade work proved should become `god-code` product capability from what should remain project-specific iteration for now.

---

## Executive Summary

The recent `starfall_demo` work showed that the right execution model is:

1. use a real project as the proving ground
2. upstream repeated, cross-project failures into `god-code` as soon as they are proven
3. keep genre-specific content tuning inside the demo until patterns stabilize

This is not a call to finish the whole demo before improving `god-code`, and it is not a call to stop feature work for abstract refactors. The working pattern is:

`short inventory -> next demo slice -> upstream proven reusable capability`

---

## Proven Product Gaps Already Upstreamed

These were exposed by `starfall_demo`, and they are clearly general `god-code` gaps rather than one-off game issues.

### 1. Scene smoke validation must catch real load/runtime failures

**What failed during dogfooding**

- passive validation looked green while actual scene execution still had resource or script problems
- ANSI-colored Godot CLI errors were not always parsed correctly

**What was upstreamed**

- scene smoke checks in validation
- ANSI-safe parsing in `error_loop`
- better real-runtime failure surfacing

**Why it belongs in `god-code`**

- every Godot project benefits from this
- this is core trust infrastructure, not genre logic

### 2. Sprite QA without reimport is incomplete

**What failed during dogfooding**

- PNG files were correct
- runtime screenshots still showed stale imported textures
- deleting `.ctex` files reproduced the same issue reliably

**What was upstreamed**

- `Godot --import` helper
- auto-reimport in sprite generation / validation workflows
- import-aware verification path

**Why it belongs in `god-code`**

- every sprite-producing project can hit stale import cache
- this is a general asset-pipeline correctness issue

### 3. Design intent must be persisted, not re-guessed every turn

**What failed during dogfooding**

- the project could drift between prototype assumptions and demo expectations
- genre, quality target, and asset rules needed to stay stable across turns

**What was upstreamed**

- gameplay intent
- quality target
- asset spec
- polish profile
- structured design memory

**Why it belongs in `god-code`**

- this is required for any multi-step game workflow
- not specific to `bullet_hell`

---

## Proven Product Gaps Not Fully Solved Yet

These are now clearly product-level gaps, but they are not fully generalized yet.

### 1. Runtime playtest still needs deterministic input orchestration

Current validation can:

- load scenes
- inspect runtime state
- capture screenshots
- compare artifacts

But `starfall_demo` also showed that screenshot-only smoke validation is too weak for real gameplay review:

- the player idles
- the game evolves without controlled input
- a screenshot can capture a valid but unhelpful moment

**What `god-code` still needs**

- scripted movement / dodge / shoot playtest flows
- fixed-tick scenario runners with inputs
- reusable combat verification checkpoints

**Why this is product-level**

- any action game will need this
- this is the next step after scene smoke

### 2. Demo-quality review is still under-modeled

The system can now prove:

- scenes load
- imports are fresh
- assets meet basic contracts

It still cannot strongly judge:

- pacing quality
- encounter readability
- hit/death feel
- whether a combat slice feels like a prototype or a demo

**What `god-code` still needs**

- a stronger demo polish rubric
- feedback-oriented checks
- genre-aware quality thresholds

### 3. Bullet-hell support is still more “pattern-capable” than “template-complete”

The demo now has better:

- escalation
- disappearing bullets
- boss phase transitions
- combat feedback

But those improvements are still mostly inside the project code, not a reusable first-class template library.

**What `god-code` still needs**

- reusable `bullet_hell` encounter templates
- phase families
- bullet pattern presets
- readability / density contracts

---

## Demo-Only Work That Should Stay In The Project For Now

These should continue inside `starfall_demo` until they stabilize across more than one slice.

### 1. Exact pattern tuning

Keep local for now:

- spread angles
- bullet speed curves
- cadence timing
- enemy spacing
- boss pattern sequencing

Reason:

- these are still content decisions, not framework decisions

### 2. Exact juice style

Keep local for now:

- score popup style
- flash strength
- burst shape
- hit feedback intensity
- text timing and callout tone

Reason:

- different games will want different emotional tone
- current work proves the need for feedback hooks, not one universal style

### 3. Project-specific balance

Keep local for now:

- player survivability
- wave duration
- score values
- density ceiling
- boss HP pacing

Reason:

- balance belongs to the game until enough reuse patterns appear

---

## Do Not Upstream Yet

These are tempting to generalize too early, but should wait.

### 1. A universal enemy AI system

Do not build this yet.

Reason:

- `starfall_demo` reinforces that `bullet_hell` enemies are choreography-driven, not generic reactive AI
- universalization here would likely make outputs worse

### 2. A single “demo polish” preset for all genres

Do not hardcode this yet.

Reason:

- platformers, shooters, tower defense, and stealth games express polish differently
- first prove genre-specific rubrics before collapsing anything

### 3. Automated combat feel scoring

Do not pretend this is solved yet.

Reason:

- the infrastructure is not there yet
- deterministic input-driven playtests should come first

---

## Next Upstream Candidates

These are the highest-value product changes once the next demo slice is complete.

### Candidate A: Scripted Combat Playtest Layer

Add support for:

- action sequences
- timed input scripts
- wave checkpoints
- combat-state assertions

Expected product value:

- turns screenshot smoke into actual gameplay validation

### Candidate B: Bullet Hell Template Library v1

Add first-class templates for:

- entry movement
- fan / ring / spiral / vanishing bullet families
- phase-transition cleanup
- density progression contracts

Expected product value:

- less ad-hoc prompt improvisation
- more reliable shooter generation

### Candidate C: Demo Polish Rubric v1

Add reviewer/playtest criteria for:

- hit clarity
- enemy death confirmation
- boss transition readability
- HUD non-intrusiveness
- encounter pacing

Expected product value:

- better distinction between “works” and “showable”

---

## Recommended Execution Order

### Step 1

Do one more `starfall_demo` slice focused on:

- scripted dodge/shoot playtest
- boss progression coverage
- clearer mid-combat evidence capture

### Step 2

Upstream the deterministic combat playtest layer into `god-code`.

### Step 3

Do a second `bullet_hell` content pass using that new playtest layer.

### Step 4

Only then upstream the stable `bullet_hell` template library and demo polish rubric pieces that repeated across the last two slices.

---

## Working Rule

Use this rule for future dogfooding:

- if a failure is about **correctness, observability, validation, import behavior, or intent persistence**, upstream it quickly
- if a failure is about **content taste, balance, pacing, or exact genre tuning**, keep it in the demo until it repeats

This keeps `god-code` moving toward real product capability without freezing feature work for premature abstraction.

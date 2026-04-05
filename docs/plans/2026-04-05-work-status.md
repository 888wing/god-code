# God Code: Master Work Status

**Last updated**: 2026-04-05
**Current version**: v0.6.1 (uncommitted changes on main)
**Purpose**: Single reference for picking up any workstream in a fresh session

---

## Active Workstreams Overview

| # | Workstream | Plan Document | Status | Blocked By |
|---|-----------|---------------|--------|-----------|
| A | **v0.6.1 uncommitted changes** | — | Ready to commit | Nothing |
| B | **API Backend (god-code-api)** | `2026-04-04-api-backend-design.md` | **v0.1 deployed** | Nothing |
| C | **v0.7 Demo-Ready Upgrade** | `2026-04-04-demo-ready-upgrade.md` | **Not started** | A merged first |
| D | **Bullet Hell / Sprite QA / Demo Polish** | `2026-04-04-bullet-hell-sprite-qa-demo-polish-backlog.md` | **Not started** | C (WS 1-2) |
| E | **Dogfooding Inventory** | `2026-04-05-dogfooding-inventory.md` | **Reference doc** | Next starfall_demo slice |

---

## A. v0.6.1 Uncommitted Changes (god-code main branch)

### What's in the diff (33 files, +1593/-89 lines)

These changes are staged but not committed on main. They must be merged before any v0.7 work begins.

| Feature | Key Files | Lines |
|---------|-----------|-------|
| Runtime harness (11 tools) | `tools/runtime_harness.py`, `runtime/runtime_bridge.py` | +553 |
| Visual regression loop | `runtime/visual_regression.py`, `runtime/playtest_harness.py` | +489 |
| Skill selector system | `prompts/skill_selector.py`, `cli.py` | +272 |
| OpenAI computer-use | `llm/adapters/openai.py`, `llm/types.py` | +123 |
| Sprite pipeline | `tools/sprite_pipeline.py` | +171 |
| MCP server expansion (40+ tools) | `mcp_server.py` | +207 |
| API backend client adaptation | `runtime/config.py`, `llm/client.py`, `runtime/engine.py` | +120 |
| Tests | 12 test files | +262 |

### Action needed

```bash
cd ~/projects/god-code
git add -A
git commit -m "feat(v0.6.1): runtime harness, skill system, computer-use, sprite pipeline, backend client"
```

### Verification

```bash
pytest tests/ -x -q  # 501/501 should pass
```

---

## B. API Backend (god-code-api) — DEPLOYED

### Repo & Infrastructure

| Resource | Value |
|----------|-------|
| GitHub | `888wing/god-code-api` (private) |
| Local | `~/projects/god-code-api` |
| Worker URL | `https://god-code-api.nano122090.workers.dev` |
| D1 Database | `c65c8d75-40e3-470d-8ca0-cc14859eeda4` (WEUR) |
| KV Namespace | `e5f2521d8e5942a2a9bc4e1b5c1d34e6` |
| Worker Secret | `SCORING_API_KEY` (Gemini, set) |
| Tests | 87/87 (Vitest) |
| Commits | 15 on master |

### Architecture

3-layer routing engine (constraints → policy → intelligence) + quality scoring (Gemini Flash) + session state (Durable Objects) + A/B testing framework + SSE streaming.

### What's done

- [x] Project scaffold + types
- [x] Router engine (3 layers)
- [x] Provider adapters (OpenAI, Anthropic, Gemini, xAI)
- [x] Session DO (pure functions + DO class)
- [x] Quality scorer (sampler, compressor, pipeline, alerts)
- [x] Worker entry + /v1/orchestrate endpoint
- [x] SSE streaming support
- [x] D1 schema + migrations
- [x] Cloudflare deployment
- [x] Health endpoint verified

### What's NOT done yet

- [ ] End-to-end smoke test with real `god-code ask` command
- [ ] Add Anthropic key to `backend_provider_keys` for cross-model review
- [ ] Dashboard for routing/quality data (D1 queries for now)
- [ ] Repo → public + README
- [ ] OAuth phase (future)
- [ ] Consensus mode / premium tier (future)

### Config location

```
~/.config/god-code/config.json
  backend_url: "https://god-code-api.nano122090.workers.dev"
  backend_provider_keys: { "openai": "sk-..." }
  backend_cost_preference: "balanced"
```

### Design doc

`docs/plans/2026-04-04-api-backend-design.md` — covers full architecture, router logic, quality scoring, session DO, API contract, deployment plan, cost estimates.

### Implementation plan

`docs/plans/2026-04-04-api-backend-impl.md` — 19 tasks across 8 phases, all completed except Task 19 (e2e smoke test).

---

## C. v0.7 Demo-Ready Upgrade — NOT STARTED

### Plan document

`docs/plans/2026-04-04-demo-ready-upgrade.md` (revised version)

### Prerequisite

Workstream A (v0.6.1 uncommitted changes) must be merged first.

### Execution order (sequential, NOT parallel)

```
WS 1 → WS 2 → WS 3 → WS 4
```

### Workstream 1: Runtime Evidence Bridge Hardening

**Goal**: Every playtest/reviewer verdict distinguishes live_editor / headless / synthetic evidence. Synthetic-only evidence caps at PARTIAL.

**Key changes**:
- Add `source`, `evidence_level`, `bridge_connected`, `captured_at` to RuntimeSnapshot
- Live editor snapshots → `evidence_level="high"`
- Headless snapshots → `evidence_level="medium"`
- Synthetic → capped to PARTIAL verdict

**Files**: runtime_bridge.py, editor_bridge.py, playtest_harness.py, gameplay_reviewer.py, reviewer.py, engine.py
**Risk**: Medium (changes verdict semantics)

### Workstream 2: Typed TSCN Property Serialization

**Goal**: Add a Variant codec for the subset of Godot values needed by UI/audio advisors. Keep raw-string backward compat.

**Key changes**:
- New `godot/variant_codec.py` — parse_variant() / serialize_variant()
- Supported: bool, int, float, String, StringName, Vector2, Color
- Unsupported falls back to raw string
- Scene tools accept typed values

**Files**: variant_codec.py (new), scene_parser.py, scene_writer.py, scene_tools.py
**Risk**: Medium (internal refactor, unblocks WS 3)

### Workstream 3: Presentation Layer Advisors (UI + Audio)

**Goal**: Deterministic UI layout advisor + audio scaffolder, integrated into quality gate.

**Key changes**:
- `godot/ui_layout_advisor.py` — 6 presets (hud_overlay, pause_menu, dialog_box, inventory_grid, title_screen, health_bar) + validate_ui_layout()
- `godot/audio_scaffolder.py` — 3 presets (minimal, standard, positional) + validate_audio_nodes()
- Playbook "Audio System" section
- Quality gate + reviewer auto-run UI/audio validators on changed scenes
- MCP tools: plan_ui_layout, scaffold_audio, validate_ui_layout

**Files**: ui_layout_advisor.py (new), audio_scaffolder.py (new), analysis_tools.py, mcp_server.py, cli.py, modes.py, quality_gate.py, reviewer.py, godot_playbook.py
**Risk**: Low-Medium (after WS 2)

### Workstream 4: Scenario Coverage + Skill Expansion

**Goal**: Auto-generated playtest scenarios (advisory, not authoritative) + 4 new domain skills.

**Key changes**:
- `generate_scenario_specs()` in playtest_harness.py — scans .tscn, infers scenarios from node types/signals
- ScenarioSpec extended: `source`, `confidence`, `evidence_policy`, `source_scene`
- 4 new skills: ui_layout, animation_pipeline, scene_transition, game_state
- Generated scenarios respect evidence_level for verdict

**Files**: playtest_harness.py, skill_library.py, skill_selector.py, gameplay_reviewer.py
**Risk**: Low-Medium (after WS 1-2)

### Success criteria

God-code can add a pause menu to a project and prove it with: headless validation + UI validator + audio validator + reviewer pass + non-synthetic screenshot evidence.

---

## D. Bullet Hell / Sprite QA / Demo Polish — NOT STARTED

### Plan document

`docs/plans/2026-04-04-bullet-hell-sprite-qa-demo-polish-backlog.md`

### Prerequisite

v0.7 Workstreams 1-2 must be done first (runtime evidence + typed serialization).

### Execution order

```
Batch 1: Asset & Quality Contracts
Batch 2: Sprite QA Gate
Batch 3: Bullet Hell Template Library
Batch 4: Demo Polish Rubric
```

### Batch 1: Asset & Quality Contracts

- `asset_spec` model in design memory (size, background key, alpha, palette, import filter)
- `quality_target` model (demo vs prototype)
- TUI visibility for these fields
- `/quality` and `/assetspec` commands

### Batch 2: Sprite QA Gate

- `tools/sprite_qa.py` — file-level checks (size, alpha, key-color remnants), style checks (palette cardinality, edge blur), import checks
- Failure artifacts: original.png, keyed.png, final.png, mask.png, qa.json
- Pipeline: generate → post-process → QA → accept or repair → import

### Batch 3: Bullet Hell Template Library

- `prompts/genre_templates.py` — movement patterns (6), fire patterns (6), phase transitions (5), wave specs (5)
- Structured data model: genre, enemy_model, boss_model, combat_profile
- Scenario specs for wave progression, phase transition, pattern readability
- Skill guidance and design memory integration

### Batch 4: Demo Polish Rubric

- `runtime/polish_rubric.py` — combat feedback, encounter pacing, readability, presentation checks
- Reviewer integration: distinguish "works" from "demo-ready"
- Scenario-based polish warnings
- TUI display of quality_target

### Definition of done

1. bullet_hell tasks route to pattern-first architecture
2. sprites can be rejected for spec violations before import
3. demo-quality projects get presentation warnings even when they technically run
4. TUI shows active quality/asset constraints

---

## E. Dogfooding Inventory — REFERENCE

### Plan document

`docs/plans/2026-04-05-dogfooding-inventory.md`

### Purpose

Separates what belongs in god-code (product capability) from what should stay in starfall_demo (project-specific tuning). Not a task list — a decision framework.

### Already upstreamed

1. Scene smoke validation + ANSI-safe parsing
2. Sprite QA with reimport (auto-reimport in generation workflows)
3. Design intent persistence (gameplay intent, quality target, asset spec)

### Not yet fully solved (next upstream candidates)

1. **Scripted combat playtest layer** — action sequences, timed input scripts, wave checkpoints
2. **Demo polish rubric v1** — hit clarity, death confirmation, boss transition readability
3. **Bullet hell template library v1** — entry movement, bullet families, phase cleanup, density contracts

### Working rule

- Correctness/observability/validation/import failures → upstream quickly
- Content taste/balance/pacing/genre tuning → keep in demo until patterns repeat

---

## Recommended Execution Priority

```
1. Commit v0.6.1 changes (Workstream A)
2. E2E smoke test of API backend (Workstream B remaining)
3. v0.7 WS 1: Runtime Evidence Bridge
4. v0.7 WS 2: Typed TSCN Serialization
5. v0.7 WS 3: UI + Audio Advisors
6. v0.7 WS 4: Scenario + Skill Expansion
7. Bullet Hell / Sprite QA (Workstream D, Batch 1-2)
8. Demo Polish Rubric (Workstream D, Batch 3-4)
9. API Backend → public + README
10. Next starfall_demo slice → upstream proven patterns
```

---

## Quick Start for a Fresh Session

### "I want to work on the API backend"
```
cd ~/projects/god-code-api
Read: docs/plans/2026-04-04-api-backend-design.md
Read: docs/plans/2026-04-04-api-backend-impl.md
Status: deployed, Task 19 (e2e smoke) pending
```

### "I want to work on v0.7 demo-ready"
```
cd ~/projects/god-code
Read: docs/plans/2026-04-04-demo-ready-upgrade.md
Prerequisite: commit v0.6.1 changes first
Start: Workstream 1 (runtime evidence bridge)
```

### "I want to work on bullet hell / sprite QA"
```
cd ~/projects/god-code
Read: docs/plans/2026-04-04-bullet-hell-sprite-qa-demo-polish-backlog.md
Read: docs/plans/2026-04-05-dogfooding-inventory.md
Prerequisite: v0.7 WS 1-2 done first
```

### "I want to resume starfall_demo"
```
Read: docs/plans/2026-04-05-dogfooding-inventory.md
Focus: scripted combat playtest, boss progression coverage
Rule: upstream repeated failures, keep content tuning local
```

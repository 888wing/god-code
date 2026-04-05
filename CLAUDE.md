# CLAUDE.md — God Code Development Guide

> AI coding agent specialized for Godot 4.4 game development. This file guides Claude Code when working on the god-code codebase itself.

## Project Identity

**god-code** — a Python CLI agent that understands GDScript, .tscn scenes, collision layers, and Godot architecture patterns. Multi-provider LLM support with 41 Godot-specific tools, AI sprite generation, vision-driven UI iteration, live Godot runtime bridge, and incremental build-and-verify discipline.

**GitHub**: https://github.com/888wing/god-code
**Backend API**: https://github.com/888wing/god-code-api (Cloudflare Workers)
**License**: GPL-3.0

## Tech Stack

- **Language**: Python 3.12+ (`from __future__ import annotations` throughout)
- **CLI**: click
- **HTTP**: httpx (async)
- **Models**: pydantic v2 (tool schemas, config, structured outputs)
- **Image**: Pillow + ImageChops (screenshot, sprite QA, visual regression)
- **TUI**: rich (panels, markdown, diff, tables, spinner) + prompt_toolkit (history, autocomplete)
- **Test**: pytest + pytest-asyncio (620 tests)
- **Build**: hatchling
- **Install**: `pipx install -e .` (editable dev), `pipx install god-code` (release)

## Current Version: 0.8.1

**Stats**: 103 source files, 83 test files, ~20K lines, 620 tests, 41 tools.

**v0.8 additions**: Vision iteration loop (screenshot → analyze → fix → score), platform API key auth, live TCP bridge to running Godot, CLI package split, ImageChops perf, ValidationSuite.

## Architecture

```
godot_agent/
├── cli/                               # CLI package (split from monolithic cli.py in v0.8)
│   ├── __init__.py                    # Re-exports for backward compat
│   ├── __main__.py                    # python -m godot_agent.cli
│   ├── commands.py                    # Click commands + setup wizard + chat loop
│   ├── menus.py                       # Menu option builders
│   ├── engine_wiring.py               # build_engine, build_registry, config loading
│   └── helpers.py                     # Toolbar, project details, skill helpers
├── agents/                            # Multi-agent system
│   ├── configs.py                     # Agent role configurations
│   ├── dispatcher.py                  # Planner/worker/reviewer dispatch
│   └── results.py                     # Agent result types
├── runtime/
│   ├── engine.py                      # Conversation loop (tools, streaming, quality gates, review, visual iteration)
│   ├── config.py                      # AgentConfig (pydantic) + env overrides
│   ├── session.py                     # Session persistence with metadata
│   ├── validation_checks.py           # ValidationSuite — shared check runner with caching
│   ├── live_client.py                 # LiveRuntimeClient — TCP bridge to GodCodeBridge.gd
│   ├── context_manager.py             # Smart compression with working memory (1.05M context)
│   ├── events.py                      # Engine event system for TUI
│   ├── modes.py                       # Interaction modes (apply/plan/explain/review/fix)
│   ├── providers.py                   # Provider detection (openai/anthropic/gemini/xai/openrouter)
│   ├── quality_gate.py                # Post-tool validation pipeline (uses ValidationSuite)
│   ├── reviewer.py                    # Automated code review (uses ValidationSuite)
│   ├── visual_regression.py           # ImageChops-based pixel comparison
│   ├── intent_resolver.py             # Intent detection with token cache
│   ├── design_memory.py               # Persistent design decisions
│   ├── runtime_bridge.py              # Runtime state snapshots
│   ├── playtest_harness.py            # Automated gameplay testing
│   ├── gameplay_reviewer.py           # Gameplay quality analysis
│   ├── oauth.py                       # Codex refresh token flow
│   ├── error_loop.py                  # Godot output parsing + fix suggestions
│   └── auth.py                        # Auth context
├── llm/
│   ├── client.py                      # LLMClient (direct + backend dual-path)
│   ├── types.py                       # Message, ToolCall, TokenUsage, ChatResponse, LLMConfig
│   ├── streaming.py                   # SSE streaming with tool call assembly
│   ├── vision.py                      # Image encoding (base64)
│   └── adapters/                      # Provider-specific adapters
│       ├── base.py                    # Adapter interface
│       ├── openai.py                  # OpenAI/OpenRouter adapter
│       └── anthropic.py               # Anthropic adapter
├── tools/                             # 41 function-calling tools
│   ├── base.py                        # BaseTool ABC (strict mode support)
│   ├── registry.py                    # ToolRegistry with security pipeline
│   ├── file_ops.py                    # read_file, write_file, edit_file (path-contained)
│   ├── script_tools.py                # read_script, edit_script, lint_script
│   ├── scene_tools.py                 # read_scene, scene_tree, add/write/remove scene nodes
│   ├── analysis_tools.py              # validate_project, check_consistency, dependency_graph, impact
│   ├── search.py                      # grep, glob
│   ├── list_dir.py                    # list_dir
│   ├── git.py                         # git (shlex-parsed)
│   ├── shell.py                       # run_shell (3 safety levels)
│   ├── godot_cli.py                   # run_godot (GUT, validate, output parser)
│   ├── screenshot.py                  # screenshot_scene (headless)
│   ├── vision_analysis.py             # analyze_screenshot (LLM vision, structured suggestions)
│   ├── vision_scoring.py              # score_screenshot (5-dimension scoring, before/after)
│   ├── sprite_qa.py                   # Sprite QA with ImageChops (key-color, alpha)
│   ├── image_gen.py                   # generate_sprite (AI pixel art + post-processing)
│   ├── web_search.py                  # web_search (Godot docs, web)
│   ├── memory_tool.py                 # design memory read/write
│   └── editor_bridge.py               # runtime snapshot, playtest
├── godot/                             # Godot-specific analysis
│   ├── project.py                     # project.godot parser
│   ├── scene_parser.py                # .tscn → TscnScene
│   ├── scene_writer.py                # Structured .tscn modification
│   ├── tscn_validator.py              # Format validation + auto-fix
│   ├── gdscript_linter.py             # Style, naming, type annotations
│   ├── collision_planner.py           # Standard 8-layer scheme
│   ├── consistency_checker.py         # Cross-file checks
│   ├── dependency_graph.py            # Project-wide file graph
│   ├── pattern_advisor.py             # Design pattern suggestions
│   ├── impact_analysis.py             # Change impact analysis
│   └── resource_validator.py          # res:// path checks
├── prompts/
│   ├── system.py                      # Compatibility wrapper
│   ├── assembler.py                   # Full prompt assembly pipeline
│   ├── godot_playbook.py              # 17 knowledge sections
│   ├── knowledge_selector.py          # Context-aware section scoring
│   ├── skill_library.py               # Skill definitions
│   ├── skill_selector.py              # Dynamic skill activation
│   ├── build_discipline.py            # Build-and-verify rules
│   ├── image_templates.py             # Pixel art prompt templates
│   └── vision_templates.py            # Vision analysis/scoring/iteration prompts
├── addons/
│   └── god_code_bridge/               # Godot 4.4 EditorPlugin (GDScript)
│       ├── god_code_bridge.gd         # TCP JSON-RPC server on port 9394
│       └── plugin.cfg                 # Plugin descriptor
├── security/
│   ├── classifier.py                  # Tool risk classification
│   ├── hooks.py                       # Pre/post execution hooks
│   ├── policies.py                    # Execution context + policies
│   ├── protected_paths.py             # Path protection rules
│   └── tool_pipeline.py               # Tool execution pipeline
├── testing/
│   └── scenario_runner.py             # Automated test scenarios
└── tui/
    ├── display.py                     # Rich TUI components
    └── input_handler.py               # prompt_toolkit input + autocomplete
```

## Two-Repo Architecture

| Repo | Purpose | Stack | Deploy |
|------|---------|-------|--------|
| **god-code** | Python CLI agent | Python 3.12+, pytest | `pipx install` |
| **god-code-api** | Backend orchestration | TypeScript, Vitest, CF Workers/D1/KV | `npx wrangler deploy` |

**god-code-api** provides:
- LLM request routing (OpenAI, Anthropic, Gemini, xAI)
- Gemini native vision adapter (generateContent + inline_data)
- Platform API key auth (`gc_live_*` keys) + quota tracking
- Admin key management (`POST /v1/admin/keys`)
- Usage tracking (`GET /v1/usage`)
- Version check for CLI updates (`GET /v1/version`)

## Key Patterns

### Tool System
Every tool inherits `BaseTool`. Supports `strict` mode for GPT-5+ structured outputs. Security pipeline validates path containment and safety level before execution.

### Provider Adapters
`llm/adapters/` handles provider-specific request/response formats:
- OpenAI: `max_completion_tokens` for gpt-5+, `max_tokens` for others
- Anthropic: `thinking` budget for reasoning models
- Gemini: `reasoning_effort` parameter

### LLM Client Dual-Path
`llm/client.py` supports two modes:
- **Direct**: client → provider API (BYOK)
- **Backend**: client → god-code-api → provider API (platform key, `backend_api_key` in config)

### Vision Model Capabilities
- **GPT-5.4**: Native vision. PRIMARY vision model for game screenshot analysis.
- **Gemini 3 Flash**: Native vision via generateContent API (god-code-api routes automatically). Fast for bulk scoring.
- Vision image detail: use `"detail": "high"` for game screenshots (pixel art needs full resolution).

### Engine Loop Phases
```
PREPARE_CONTEXT → CALL_MODEL → EXECUTE_TOOLS → RUN_QUALITY_GATE → RUN_REVIEWER → RUN_VISUAL_ITERATION → NEXT_ROUND → DONE
```

- **PREPARE_CONTEXT**: Tries live bridge to Godot (`_try_live_bridge`, silent on failure)
- **RUN_QUALITY_GATE + RUN_REVIEWER**: Share a `ValidationSuite` to avoid duplicate checks
- **RUN_VISUAL_ITERATION**: Screenshot → analyze → fix → re-screenshot → score (max 3 iterations)

### Live Runtime Bridge
GodCodeBridge.gd (Godot plugin) ↔ LiveRuntimeClient (Python) over TCP port 9394.
- JSON-RPC 2.0 protocol, newline-delimited
- Methods: `ping`, `get_scene_tree`, `get_node_properties`, `capture_viewport`, `inject_action`, `get_signals`
- Install: `god-code setup-bridge <project>`

### Context Management (1.05M window)
Smart compression at 75% (787K tokens):
1. Extract working memory (modified files, decisions, errors)
2. Keep 20 recent messages intact
3. Replace old turns with memory summary
4. Tell LLM to re-read files if needed

### Interaction Modes
- `apply`: Full tool access, write code (includes vision tools)
- `plan`: Read-only tools, design first
- `explain`: Read-only, educational
- `review`: Read-only, quality analysis
- `fix`: Full tools, error-focused (includes vision tools)

## Development Rules

### CRITICAL: Python 3.12+ Required
`pyproject.toml` specifies `requires-python = ">=3.12"`. Do not downgrade.

Rules:
- Every `.py` file MUST have `from __future__ import annotations` as first import
- Use `dataclass(slots=True)` where appropriate (3.10+)
- `match`/`case` allowed (3.10+)

### Adding a New Tool
1. Create in `godot_agent/tools/your_tool.py` inheriting `BaseTool`
2. Define `Input`/`Output` as pydantic `BaseModel` (all fields must have defaults for strict mode)
3. Implement `async execute()`, `is_read_only()`, `is_destructive()`
4. Register in `cli/engine_wiring.py:build_registry()`
5. Add to appropriate mode allowlists in `runtime/modes.py`
6. Add tests in `tests/tools/`

### Adding a Provider
1. Create adapter in `godot_agent/llm/adapters/`
2. Register in `runtime/providers.py`
3. Add detection rules (model prefix, base_url pattern)

## Config Reference

`~/.config/god-code/config.json`:

| Field | Default | Description |
|-------|---------|-------------|
| api_key | "" | LLM API key |
| provider | "openai" | openai, anthropic, gemini, xai, openrouter |
| model | "gpt-5.4" | Model ID |
| reasoning_effort | "high" | low, medium, high |
| mode | "apply" | apply, plan, explain, review, fix |
| language | "en" | en, zh-TW, ja, ko |
| verbosity | "normal" | concise, normal, detailed |
| auto_validate | true | Run Godot after file changes |
| auto_commit | false | Suggest git commit |
| token_budget | 0 | Max tokens (0=unlimited) |
| safety | "normal" | strict, normal, permissive |
| streaming | true | Stream responses |
| extra_prompt | "" | Custom instructions |
| backend_url | "" | god-code-api URL (for backend mode) |
| backend_api_key | "" | Platform API key (`gc_live_*`) |
| max_visual_iterations | 3 | Max vision iteration cycles per round |

## Testing

```bash
# god-code (Python)
cd ~/projects/god-code
.venv/bin/python -m pytest tests/ -v          # Full suite (620 tests)
.venv/bin/python -m pytest tests/tools/ -v    # Tool tests only
.venv/bin/python -m pytest tests/runtime/ -v  # Runtime tests

# god-code-api (TypeScript)
cd ~/projects/god-code-api
npx vitest run                                # Full suite (134 tests)
```

## Release Process

```bash
# 1. Bump version — single source of truth
cd ~/projects/god-code
# Edit pyproject.toml: version = "X.Y.Z"
# _VERSION in commands.py reads from importlib.metadata automatically

# 2. Commit, push
git commit -am "release: vX.Y.Z"
git push

# 3. Update backend version endpoint
cd ~/projects/god-code-api
# Edit wrangler.toml: LATEST_VERSION = "X.Y.Z"
# Optional: UPDATE_MESSAGE = "vX.Y: new feature summary"
npx wrangler deploy

# 4. Users update via:
pipx upgrade god-code
```

**Version sync**: `_VERSION` in `commands.py` reads from `importlib.metadata.version("god-code")` which reads `pyproject.toml`. No hardcoded version strings.

**Update notifications**: CLI checks `GET /v1/version` on startup. Backend returns `latest`, `min_supported`, `update_url`, `message`. Outdated users see yellow prompt; unsupported users see red warning.

## Backend API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/v1/health` | GET | None | Health check |
| `/v1/version` | GET | None | Version check for CLI updates |
| `/v1/models` | GET | None | List available models |
| `/v1/orchestrate` | POST | BYOK or `gc_live_*` | LLM request routing |
| `/v1/admin/keys` | POST | `X-Admin-Secret` | Create platform API key |
| `/v1/usage` | GET | `Bearer gc_live_*` | Query usage and quota |

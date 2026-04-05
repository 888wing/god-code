# CLAUDE.md — God Code Development Guide

> AI coding agent specialized for Godot 4.4 game development. This file guides Claude Code when working on the god-code codebase itself.

## Project Identity

**god-code** — a Python CLI agent that understands GDScript, .tscn scenes, collision layers, and Godot architecture patterns. Multi-provider LLM support with 29 Godot-specific tools, AI sprite generation, and incremental build-and-verify discipline.

**PyPI**: `pip install god-code`
**GitHub**: https://github.com/888wing/god-code
**License**: GPL-3.0

## Tech Stack

- **Language**: Python 3.9+ (uses `from __future__ import annotations` for 3.10+ syntax)
- **CLI**: click
- **HTTP**: httpx (async)
- **Models**: pydantic v2 (tool schemas, config, structured outputs)
- **Image**: Pillow (screenshot + sprite post-processing)
- **TUI**: rich (panels, markdown, diff, tables, spinner) + prompt_toolkit (history, autocomplete)
- **Test**: pytest + pytest-asyncio (383 tests)
- **Build**: hatchling
- **CI**: GitHub Actions (auto-publish to PyPI on tag)

## Current Version: 0.5.1

**Stats**: 70 source files, 55 test files, ~11K lines, 383 tests, 29 tools.

## Architecture

```
godot_agent/
├── cli.py                          # Click CLI + setup wizard + chat loop
├── agents/                         # Multi-agent system
│   ├── configs.py                  # Agent role configurations
│   ├── dispatcher.py               # Planner/worker/reviewer dispatch
│   └── results.py                  # Agent result types
├── runtime/
│   ├── engine.py                   # Conversation loop (tools, streaming, quality gates, review)
│   ├── config.py                   # AgentConfig (pydantic) + env overrides
│   ├── session.py                  # Session persistence with metadata
│   ├── oauth.py                    # Codex refresh token flow
│   ├── error_loop.py               # Godot output parsing + fix suggestions
│   ├── context_manager.py          # Smart compression with working memory (1.05M context)
│   ├── events.py                   # Engine event system for TUI
│   ├── modes.py                    # Interaction modes (apply/plan/explain/review/fix)
│   ├── providers.py                # Provider detection (openai/anthropic/gemini/xai/openrouter)
│   ├── quality_gate.py             # Post-tool validation pipeline
│   ├── reviewer.py                 # Automated code review
│   ├── playtest_harness.py         # Automated gameplay testing
│   ├── gameplay_reviewer.py        # Gameplay quality analysis
│   ├── runtime_bridge.py           # Runtime state snapshots
│   ├── design_memory.py            # Persistent design decisions
│   └── auth.py                     # Auth context
├── llm/
│   ├── client.py                   # LLMClient with retry, content filter handling
│   ├── types.py                    # Message, ToolCall, TokenUsage, ChatResponse, LLMConfig
│   ├── streaming.py                # SSE streaming with tool call assembly
│   ├── vision.py                   # Image encoding
│   └── adapters/                   # Provider-specific adapters
│       ├── base.py                 # Adapter interface
│       ├── openai.py               # OpenAI/OpenRouter adapter
│       └── anthropic.py            # Anthropic adapter
├── tools/                          # 29 function-calling tools
│   ├── base.py                     # BaseTool ABC (strict mode support)
│   ├── registry.py                 # ToolRegistry with security pipeline
│   ├── file_ops.py                 # read_file, write_file, edit_file (path-contained)
│   ├── script_tools.py             # read_script, edit_script, lint_script
│   ├── scene_tools.py              # read_scene, scene_tree, add/write/remove scene nodes
│   ├── analysis_tools.py           # validate_project, check_consistency, dependency_graph, impact
│   ├── search.py                   # grep, glob
│   ├── list_dir.py                 # list_dir
│   ├── git.py                      # git (shlex-parsed)
│   ├── shell.py                    # run_shell (3 safety levels)
│   ├── godot_cli.py                # run_godot (GUT, validate, output parser)
│   ├── screenshot.py               # screenshot_scene (headless)
│   ├── image_gen.py                # generate_sprite (AI pixel art + post-processing)
│   ├── web_search.py               # web_search (Godot docs, web)
│   ├── memory_tool.py              # design memory read/write
│   └── editor_bridge.py            # runtime snapshot, playtest
├── godot/                          # Godot-specific analysis
│   ├── project.py                  # project.godot parser
│   ├── scene_parser.py             # .tscn → TscnScene
│   ├── scene_writer.py             # Structured .tscn modification
│   ├── tscn_validator.py           # Format validation + auto-fix
│   ├── gdscript_linter.py          # Style, naming, type annotations
│   ├── collision_planner.py        # Standard 8-layer scheme
│   ├── consistency_checker.py      # Cross-file checks
│   ├── dependency_graph.py         # Project-wide file graph
│   ├── pattern_advisor.py          # Design pattern suggestions
│   ├── impact_analysis.py          # Change impact analysis
│   └── resource_validator.py       # res:// path checks
├── prompts/
│   ├── system.py                   # Compatibility wrapper
│   ├── assembler.py                # Full prompt assembly pipeline
│   ├── godot_playbook.py           # 17 knowledge sections
│   ├── knowledge_selector.py       # Context-aware section scoring
│   ├── skill_library.py            # Skill definitions
│   ├── skill_selector.py           # Dynamic skill activation
│   ├── build_discipline.py         # Build-and-verify rules
│   └── image_templates.py          # Pixel art prompt templates
├── security/
│   ├── classifier.py               # Tool risk classification
│   ├── hooks.py                    # Pre/post execution hooks
│   ├── policies.py                 # Execution context + policies
│   ├── protected_paths.py          # Path protection rules
│   └── tool_pipeline.py            # Tool execution pipeline
├── testing/
│   └── scenario_runner.py          # Automated test scenarios
└── tui/
    ├── display.py                  # Rich TUI components
    └── input_handler.py            # prompt_toolkit input + autocomplete
```

## Key Patterns

### Tool System
Every tool inherits `BaseTool`. Supports `strict` mode for GPT-5+ structured outputs. Security pipeline validates path containment and safety level before execution.

### Provider Adapters
`llm/adapters/` handles provider-specific request/response formats:
- OpenAI: `max_completion_tokens` for gpt-5+, `max_tokens` for others
- Anthropic: `thinking` budget for reasoning models
- Gemini: `reasoning_effort` parameter

### Vision Model Capabilities
- **GPT-5.4**: Native vision support. Accepts `image_url` in chat completions messages. Use for game screenshot analysis, UI iteration, visual QA. This is the PRIMARY vision model — do NOT fall back to gpt-4o.
- **Gemini 2.5 Flash**: Vision via OpenAI-compatible endpoint. Fast and cheap. Use for quality scoring and bulk screenshot analysis.
- **GPT-4o**: DEPRECATED for god-code. Use gpt-5.4 instead — it has superior vision AND tool-calling.
- Vision image detail: use `"detail": "high"` for game screenshots (pixel art needs full resolution).

### Engine Loop Phases
```
PREPARE_CONTEXT → CALL_MODEL → EXECUTE_TOOLS → RUN_QUALITY_GATE → RUN_REVIEWER → NEXT_ROUND → DONE
```

### Context Management (1.05M window)
Smart compression at 75% (787K tokens):
1. Extract working memory (modified files, decisions, errors)
2. Keep 20 recent messages intact
3. Replace old turns with memory summary
4. Tell LLM to re-read files if needed

### Interaction Modes
- `apply`: Full tool access, write code
- `plan`: Read-only tools, design first
- `explain`: Read-only, educational
- `review`: Read-only, quality analysis
- `fix`: Full tools, error-focused

## Development Rules

### CRITICAL: Python 3.9 Compatibility
`pyproject.toml` MUST keep `requires-python = ">=3.9"`. macOS ships Python 3.9 via Xcode — users run `pip install god-code` with it. Never change this.

Rules:
- No `dataclass(slots=True)` — Python 3.10+ only
- No `match`/`case` statements — Python 3.10+ only
- Every `.py` file MUST have `from __future__ import annotations` as first import
- Use `eval_type_backport` dependency for pydantic `str | None` on 3.9
- **Before every release**: verify `grep "requires-python" pyproject.toml` shows `>=3.9`

### Adding a New Tool
1. Create in `godot_agent/tools/your_tool.py` inheriting `BaseTool`
2. Define `Input`/`Output` as pydantic `BaseModel` (all fields must have defaults for strict mode)
3. Implement `async execute()`, `is_read_only()`, `is_destructive()`
4. Register in `cli.py:build_registry()`
5. Add to `prompts/system.py` active_tools list
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

## Testing

```bash
python -m pytest tests/ -v          # Full suite (383 tests)
python -m pytest tests/tools/ -v    # Tool tests only
python -m pytest tests/e2e/ -v      # E2E integration tests
```

## Release

```bash
# Bump version in pyproject.toml + cli.py _VERSION
git commit -am "release: v0.5.1"
git tag v0.5.1
git push && git push --tags
# → GitHub Actions auto-publishes to PyPI
```

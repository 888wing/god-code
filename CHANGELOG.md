# Changelog

All notable changes to God Code will be documented in this file.

## [1.0.0rc1] — 2026-04-07

**v1.0 is the first release where god-code is comfortable to use day-to-day without needing to know its quirks.** This is a coordinated UX overhaul. No new features, no breaking API changes — every change makes the existing tool feel less broken in everyday use.

This release closes 27 of 28 UX issues identified in the v1.0 audit (see `docs/plans/2026-04-07-v1.0.0-ux-upgrade-design.md`). The 28th was already fixed in v0.9.2.

### Headline fixes

- **Streaming "thinking" indicator** — gpt-5.4 with `reasoning_effort=high` has a 30-60s silent reasoning phase before any token streams. Previously you saw an empty cyan panel and assumed god-code was frozen. Now you see a `thinking…` spinner that animates until the first token arrives. (A1)
- **`max_tokens` default raised from 16384 → 65536** — long technical reports were silently truncated mid-section because the cap was way below gpt-5.4's 128K output capability. Override with `/set max_tokens 16384` if you prefer the old conservative limit. (B1)
- **Token count works in backend mode** — `_stream_via_backend` was missing `stream_options.include_usage`, so backend-mode users (anyone with `backend_url` + `gc_live_*`) saw `0 tokens / $0.00` after every turn. Now matches direct-mode behaviour. (B5)
- **Real Ctrl+C cleanup** — cancelled turns no longer leave their partial messages polluting the next turn's context. New `engine.rollback_current_turn()` drops everything appended since the most recent `submit()` began. (C2)
- **Tool progress spinner** — long-running tools (validation, sprite generation, screenshot — typically 10-60s) now show an auto-animating spinner via `rich.console.status` instead of going silent between `tool: started` and `tool: ok`. (A2)
- **Planner agent stops claiming "I'm in PLAN mode"** — the planner sub-agent system prompt was triggering an LLM hallucination where the model would announce "我目前是 PLAN 模式" / "I am in plan mode" in its response, confusing users into thinking the CLI was stuck in plan interaction mode. Prompt rewritten to explicitly disavow that wording and clarify the planner is a sub-agent inside god-code. (F1)

### Fixed (full list — 27 issues across 11 commits)

- **A1** Streaming thinking spinner (`tui/display.py`)
- **A2** Tool execution status spinner
- **A3** Blank line between successive streamed turns
- **A4** Planner sub-agent output bracketed with `Rule` separators
- **A5** Autosave success/failure events + activity log entries
- **B1** `max_tokens` default 16384 → 65536
- **B2 / G2** `tool_result_truncated` event when tool output is silently capped
- **B3** API error detail bumped 200 → 500 chars with `[…truncated]` marker
- **B4** Tool args truncated at 100 chars to prevent terminal overflow
- **B5** Backend streaming now sends `stream_options.include_usage`
- **C1** Diff read failures emit `diff_failed` event instead of `except: pass`
- **C2** `rollback_current_turn()` cleans message state after Ctrl+C
- **C4** Version check offline state surfaced as dim activity line
- **C5** `is_known_model_pricing()` helper; usage line shows `~$unknown` for unknown models
- **C6** `/resume <invalid_id>` now actionable error
- **D1** `god-code setup` confirmation prompt before overwriting existing config
- **D2** Loud yellow warning when Godot binary auto-detection fails
- **D3** Welcome panel reduced to 4 essential fields
- **D4** Multiline continuation prompt cancel hint
- **E1** `/help` table reorganized into 6 sections
- **E2** Activity log slice mismatch (10 vs 8) fixed
- **E4** Mode embedded in input prompt with mode-specific colour
- **F1** Planner prompt rewrite — disavows "PLAN mode" wording
- **F2** Planner prompt enforces structured output format
- **G3** New events: `session_autosaved`, `session_autosave_failed`, `diff_failed`, `version_check_offline`, `turn_cancelled`
- **H2** Tab-completion hint added to welcome banner

### Test count

665 → 681 (+16 regression tests across 5 test files)

### Known scope notes

- **C2 partial implementation** — `rollback_current_turn()` cleans up message state but the full `asyncio.create_task` cancellation pattern (true task termination of in-flight HTTP streams and subprocess tools) is deferred to v1.0.1. The existing CLI flow tests depend on the simpler synchronous-await pattern. In practice CPython's signal handling unwinds the await stack on Ctrl+C correctly, so the user-visible behaviour is fixed even without true task termination.
- **A2 layer 2 deferred** — universal spinner (Layer 1) ships in v1.0.0; per-tool `tool_progress` events for finer-grained reporting (Layer 2) deferred since they require per-tool instrumentation.
- **Subprocess termination on cancel deferred** — if a tool has already spawned a subprocess (Godot validation, sprite generation), cancelling the Python coroutine doesn't kill the subprocess. v1.0.1 will add per-tool subprocess registration + termination.

### What changed since v0.6.1 (the last PyPI release before v0.9.2)

> **PyPI was stuck at v0.6.1 from early April 2026 until v0.9.2 in this same release cycle.** Anyone who installed god-code via `pipx install god-code` between v0.6.1 and v0.9.2 was on a version that predates everything below. v1.0.0rc1 is the first PyPI release that includes all v0.7 / v0.8 / v0.9 / v1.0 work.

- **v0.7** — Demo-ready foundation: genre detection (`runtime/intent_resolver.py`), sprite QA pipeline (`tools/sprite_qa.py`), polish rubric, scenario engine (`testing/scenario_runner.py`)
- **v0.8** — Vision iteration loop (screenshot → analyze → fix → score), live runtime bridge to Godot 4.4 over TCP 9394, backend dual-path LLM client, platform API key auth (`gc_live_*`), CLI package split, ImageChops perf, ValidationSuite
- **v0.9** — Pre-launch security audit (shell hardening, session paths, MCP path containment, log redaction), OpenAI strict-mode pydantic compatibility, hatch wheel cleanup
- **v0.9.1** — `assistant_preview` extraction guard against empty LLM responses (was crashing the planner pass)
- **v0.9.2** — `AgentDispatcher` propagates streaming callbacks to sub-engines (planner pass now streams to TUI instead of blocking 60-120s)
- **v1.0.0rc1** — this release; the full 27-fix UX overhaul above

## [Unreleased]

### Security
- **run_shell hardened** against credential exfiltration: subprocess environment is now filtered to drop any variable whose name contains KEY/TOKEN/SECRET/PASSWORD/PASSWD/CREDENTIAL/AUTH/PRIVATE/CERT, and `env`, `printenv`, `set`, `export`, and reads of `.config/god-code`, `.codex/auth`, `.aws/credentials`, `.ssh/id_*`, `.ssh/authorized_keys`, `.netrc`, `.npmrc`, `.pypirc` are now blocked at all safety levels.
- **Session files** (`~/.agent_sessions/*.json`) are now `chmod 0o600` on write so tool outputs captured in conversation history are not world-readable.
- **Atomic secure writes** for `~/.config/god-code/config.json` and `~/.config/god-code/auth.json`: files are created via `tempfile` + `os.fchmod(0o600)` + `os.replace`, eliminating the TOCTOU window where an earlier `write_text` produced a briefly 0o644 file.
- **MCP server path containment**: every `file_path` argument to MCP tools is validated against the active project root with `Path.relative_to`, and a `.gd/.tscn/.tres/.cfg/.gdshader/.json/.md/.txt/.import` extension allowlist, preventing a misbehaving MCP client from reading or writing arbitrary files such as `~/.config/god-code/config.json`.
- **Prefix confusion fix** in `file_ops._validate_path`: `startswith` replaced with `Path.relative_to`, so a project rooted at `/proj/my-game` no longer accidentally permits access to `/proj/my-game-secrets/`.
- **Log redaction** (`godot_agent/llm/redact.py`): a new `redact_secrets` helper masks Bearer tokens, `sk-*` keys, `gc_live_*` keys, and JWT triples in any error string before it is handed to `log.error`/`log.warning`. Applied to backend, streaming, and computer-use error paths in `llm/client.py` and `llm/streaming.py`.

### Added
- Workspace-style chat TUI with session snapshot, recent activity, and live streaming panels
- Interaction modes (`apply`, `plan`, `explain`, `review`, `fix`) with mode-aware tool availability
- Autosaved session metadata with `/sessions`, `/resume`, `/new`, and project-aware restore flow
- Gameplay intent resolver with persistent profile storage in design memory
- `/intent` commands and TUI intent panel for confirming genre/combat/enemy direction
- Genre-aware internal skills: `bullet_hell`, `topdown_shooter`, `platformer_enemy`, `tower_defense`, `stealth_guard`
- Profile-aware playtest selection and report context
- MkDocs documentation site skeleton with getting-started, TUI, validation, provider, and MCP guides

### Changed
- Unified `ask` and `chat` rendering pipeline, including tool progress and validation feedback
- Improved post-tool validation visibility and tool result summaries in interactive sessions
- Session persistence now preserves assistant tool calls and richer metadata for restore
- Prompt assembly, skill routing, planner/reviewer/playtest flows, and workspace state now consume shared gameplay intent

## [0.1.0] - 2026-04-02

### Added
- CLI with `ask`, `chat`, `info`, `login`, `logout`, `status` commands
- 10 tools: read_file, write_file, edit_file, list_dir, grep, glob, git, run_shell, run_godot, screenshot_scene
- OpenAI-compatible API client with streaming and vision support
- OAuth login via Codex CLI refresh token
- Godot project parser (project.godot, autoloads, resolution)
- .tscn scene parser, writer, and format validator with auto-fix
- GDScript linter (naming, ordering, type annotations, anti-patterns)
- Collision layer planner (standard 8-layer scheme)
- Cross-file consistency checker (collision, signals, resource paths, groups)
- Project dependency graph builder
- Design pattern advisor (object pool, component, state machine)
- Godot Playbook knowledge system (17 sections, context-aware injection)
- Build discipline rules (incremental build-and-verify)
- Error detection loop with Godot output parsing and fix suggestions
- Conversation context compaction for long sessions
- Path containment security (file ops restricted to project root)
- Shell command sandboxing (dangerous pattern blocking)
- API retry with exponential backoff (429 rate limits)
- Content filter graceful handling (400 errors)
- Session persistence to JSON

### Security
- File operations restricted to project root directory
- Shell commands blocked for dangerous patterns (rm -rf /, sudo, etc.)
- Git argument parsing via shlex.split()
- OAuth tokens stored with 600 permissions
- API key/token masked in status output

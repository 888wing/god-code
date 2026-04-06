# Changelog

All notable changes to God Code will be documented in this file.

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

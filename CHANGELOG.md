# Changelog

All notable changes to God Code will be documented in this file.

## [Unreleased]

### Added
- Workspace-style chat TUI with session snapshot, recent activity, and live streaming panels
- Interaction modes (`apply`, `plan`, `explain`, `review`, `fix`) with mode-aware tool availability
- Autosaved session metadata with `/sessions`, `/resume`, `/new`, and project-aware restore flow

### Changed
- Unified `ask` and `chat` rendering pipeline, including tool progress and validation feedback
- Improved post-tool validation visibility and tool result summaries in interactive sessions
- Session persistence now preserves assistant tool calls and richer metadata for restore

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

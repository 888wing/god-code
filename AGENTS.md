# AGENTS.md — God Code Development Guide

> AI coding agent specialized for Godot 4.4 game development. This file guides Codex when working on the god-code codebase itself.

## Project Identity

**god-code** — a Python CLI agent that understands GDScript, .tscn scenes, collision layers, and Godot architecture patterns. It calls LLM APIs with Godot-specific tools and enforces incremental build-and-verify discipline.

**PyPI**: `pip install god-code`
**GitHub**: https://github.com/888wing/god-code
**License**: GPL-3.0

## Tech Stack

- **Language**: Python 3.12+
- **CLI**: click
- **HTTP**: httpx (async)
- **Models**: pydantic v2 (tool schemas, config)
- **Image**: Pillow (screenshot encoding)
- **Test**: pytest + pytest-asyncio
- **Build**: hatchling
- **CI**: GitHub Actions (auto-publish to PyPI on tag)

## Current Version: 0.1.0

**Completed**: CLI (ask/chat/info/setup/login/logout/status), 10 tools, LLM client with OpenAI-compatible API, Godot Playbook knowledge system (17 sections), .tscn parser/writer/validator, GDScript linter, collision planner, dependency graph, pattern advisor, consistency checker, error loop, context manager, first-run setup wizard, PyPI published.

**157 tests**, ~4,000 lines production code.

## Architecture

```
godot_agent/
├── cli.py                        # Click CLI entry point + setup wizard
├── runtime/
│   ├── engine.py                 # Conversation loop (tool calling + context compaction + error loop)
│   ├── config.py                 # AgentConfig (pydantic) + load from file/env
│   ├── session.py                # Session persistence (.agent_sessions/*.json)
│   ├── oauth.py                  # Codex refresh token flow
│   ├── error_loop.py             # Godot output parsing + fix suggestions
│   ├── context_manager.py        # Message compaction + file relevance scoring
│   └── auth.py                   # AuthContext dataclass
├── llm/
│   ├── client.py                 # LLMClient (OpenAI-compatible, retry, content filter handling)
│   ├── streaming.py              # SSE streaming
│   └── vision.py                 # Image → base64 encoding
├── tools/                        # 10 function-calling tools
│   ├── base.py                   # BaseTool ABC + ToolResult
│   ├── registry.py               # ToolRegistry (register, execute, to_openai_tools)
│   ├── file_ops.py               # read_file, write_file, edit_file (path-contained)
│   ├── search.py                 # grep, glob
│   ├── list_dir.py               # list_dir
│   ├── git.py                    # git (shlex-parsed)
│   ├── shell.py                  # run_shell (blocked patterns)
│   ├── godot_cli.py              # run_godot (GUT, validate, output parser)
│   └── screenshot.py             # screenshot_scene (headless)
├── godot/                        # Godot-specific analysis
│   ├── project.py                # project.godot parser → GodotProject
│   ├── scene_parser.py           # .tscn → TscnScene (nodes, resources, connections)
│   ├── scene_writer.py           # add_node, set_property, remove_node, add_connection
│   ├── tscn_validator.py         # Format validation + auto-fix ordering
│   ├── gdscript_linter.py        # Naming, ordering, type annotations, anti-patterns
│   ├── collision_planner.py      # Standard 8-layer scheme
│   ├── consistency_checker.py    # Cross-file collision/signal/resource/group checks
│   ├── dependency_graph.py       # Project-wide scene→script→resource graph
│   ├── pattern_advisor.py        # Object pool, component, state machine suggestions
│   └── resource_validator.py     # res:// path existence check
└── prompts/
    ├── system.py                 # Builds system prompt (identity + knowledge + discipline + context)
    ├── godot_playbook.py         # 17 indexed knowledge sections
    ├── knowledge_selector.py     # Context-aware section scoring + injection
    └── build_discipline.py       # Incremental build-and-verify rules
```

## Key Patterns

### Tool System
Every tool inherits `BaseTool` with pydantic `Input`/`Output` models. The registry auto-generates OpenAI function calling schemas.

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something"
    class Input(BaseModel):
        param: str = Field(description="...")
    class Output(BaseModel):
        result: str
    async def execute(self, input: Input) -> ToolResult:
        return ToolResult(output=self.Output(result="done"))
```

Register in `cli.py:build_registry()`.

### Path Containment
`file_ops.py` has a module-level `_project_root` set by CLI on startup. All read/write/edit operations validate paths are within project root. `set_project_root()` is called in `build_engine()`.

### Engine Flow
```
user message → _maybe_compact() → client.chat() → tool_calls?
  → yes: execute tools → _post_tool_validate() → loop
  → no: return content
```
- Compaction triggers at ~80K estimated tokens
- Post-tool validation runs `godot --headless --quit` after write_file/edit_file
- Max tool rounds default: 20

### Knowledge Injection
`knowledge_selector.py` scores Playbook sections by keyword overlap with user prompt + file extensions. Top 4 sections injected (~2K tokens instead of full ~15K).

### Error Loop Integration
After any file-mutating tool call, engine runs Godot headless validation. If errors found, injects a system message telling the LLM to fix them before proceeding.

## Development Rules

### CRITICAL: Read Before Modify
Never modify files without reading them first. This applies to both god-code source AND Godot project files the agent operates on.

### Adding a New Tool
1. Create `godot_agent/tools/your_tool.py` inheriting `BaseTool`
2. Define `Input` and `Output` as pydantic `BaseModel`
3. Implement `async execute()`
4. Register in `cli.py:build_registry()`
5. Add tests in `tests/tools/test_your_tool.py`
6. Update README tool list

### Adding Godot Knowledge
Edit `godot_agent/prompts/godot_playbook.py`:
- Each section: `(title, [keywords], content_string)`
- Keywords drive auto-selection in `knowledge_selector.py`
- Keep sections concise (~200 tokens each)

### Adding Godot Analysis
New analyzers go in `godot_agent/godot/`. Follow existing patterns:
- Pure functions, no side effects
- Return structured dataclasses
- Include `format_*()` for LLM-readable output

### Config
`~/.config/god-code/config.json` with `GODOT_AGENT_*` env overrides:

| Field | Default | Env Var |
|-------|---------|---------|
| api_key | "" | GODOT_AGENT_API_KEY |
| base_url | https://api.openai.com/v1 | GODOT_AGENT_BASE_URL |
| model | gpt-5.4 | GODOT_AGENT_MODEL |
| godot_path | godot | GODOT_AGENT_GODOT_PATH |
| oauth_token | null | GODOT_AGENT_OAUTH_TOKEN |

OAuth client_id configurable via `GODOT_AGENT_OAUTH_CLIENT_ID`.

## Testing

```bash
# Full suite (157 tests)
python -m pytest tests/ -v

# Specific module
python -m pytest tests/godot/test_tscn_validator.py -v

# E2E with mocked LLM
python -m pytest tests/test_e2e.py -v
```

All tests use `tmp_path` fixture for isolation. LLM tests mock `httpx` responses. No real API calls in tests.

## Release Process

Automated via GitHub Actions:

```bash
# 1. Bump version in pyproject.toml
# 2. Commit + tag
git commit -am "release: v0.2.0"
git tag v0.2.0
git push && git push --tags
# → GitHub Actions runs tests → publishes to PyPI
```

Requires `PYPI_API_TOKEN` in GitHub repo secrets.

## Security Model

- **File ops**: Restricted to project root (symlink-aware)
- **Shell**: Blocked patterns (rm -rf /, sudo, curl|sh, etc.)
- **Git**: shlex.split() for proper argument parsing
- **API keys**: Stored with 600 permissions, masked in CLI output
- **Content filter**: 400 errors retried, graceful fallback message

## Roadmap

### Phase 2: Editor Plugin Bridge
- Godot EditorPlugin with WebSocket server
- `editor_bridge.py` Python WebSocket client
- Tier 1 operations: scene tree, properties, signals, run/stop game
- Live viewport screenshots from editor

### Phase 3: Hosted API
- Cloudflare Worker proxy with Google OAuth
- Free tier (50 req/day, gpt-4o-mini)
- Pro tier ($12/mo, gpt-5.4 + vision)
- Small model routing for simple tasks
- Prompt caching for session continuity

## Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, version, dependencies |
| `CHANGELOG.md` | Version history |
| `README.md` | User-facing documentation |
| `CONTRIBUTING.md` | Contributor guide |
| `.github/workflows/publish.yml` | Auto-publish to PyPI on tag |
| `godot_agent/cli.py` | CLI commands + setup wizard |
| `godot_agent/runtime/engine.py` | Core conversation loop |
| `godot_agent/prompts/godot_playbook.py` | Godot knowledge base |

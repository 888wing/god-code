# God Code

AI coding agent specialized for Godot 4.4 game development. Unlike generic coding agents, God Code understands GDScript, .tscn scene files, collision layers, and Godot architecture patterns — and enforces incremental build-and-verify discipline.

## Features

- **29 tools**: file ops, scene manipulation, script editing, search, git, shell, Godot headless runner, screenshot, AI sprite generation, web search
- **AI sprite generation**: pixel art pipeline with chroma key removal, auto-crop, nearest-neighbor resize, style presets
- **Structured Outputs**: strict JSON schemas for gpt-5+ models — zero tool call parse errors
- **Web search**: query Godot docs and web when built-in knowledge isn't enough
- **Workspace-style chat TUI**: session snapshot, activity timeline, live tool feedback, streaming output
- **Interaction modes**: `apply`, `plan`, `explain`, `review`, `fix` with mode-aware prompts and tool access
- **Multi-provider**: OpenAI (gpt-5.4), Anthropic (claude-sonnet-4.6), Google (gemini), xAI (grok), OpenRouter, local models
- **Session recovery**: autosave, `/sessions`, `/resume`, project-aware session metadata
- **Godot-native understanding**: project.godot parser, .tscn scene parser/writer/validator, collision layer planner
- **Code quality**: GDScript linter, cross-file consistency checker, design pattern advisor, impact analysis
- **Smart knowledge injection**: 17 Godot Playbook sections auto-selected by task context + skill system
- **Build discipline**: incremental build-and-verify with quality gates and automated review
- **Security**: path containment, shell command blocking (3 safety levels), tool execution pipeline
- **1.05M context window**: smart compression with working memory extraction at 75% threshold

## Install

```bash
pip install god-code
```

With MCP support (for Claude Code / Codex integration):

```bash
pip install god-code[mcp]
```

Requires Python 3.9+.

### Claude Code Skill (one-click setup)

If you use Claude Code, install the god-code skill for automated setup:

```bash
# Copy the skill to your Claude Code skills directory
mkdir -p ~/.claude/skills/god-code-setup
curl -sL https://raw.githubusercontent.com/888wing/god-code/main/skills/god-code-setup/SKILL.md \
  -o ~/.claude/skills/god-code-setup/SKILL.md
```

Then in Claude Code, just say: **"install god-code and configure MCP"** — it will handle everything automatically.

### From Source

```bash
git clone https://github.com/888wing/god-code.git
cd god-code
pip install -e ".[dev,mcp]"
```

## Quick Start

### 1. Configure API key (BYOK — Bring Your Own Key)

```bash
# Option A: Environment variable
export GODOT_AGENT_API_KEY="sk-proj-..."

# Option B: Config file
mkdir -p ~/.config/god-code
cat > ~/.config/god-code/config.json << 'EOF'
{
  "api_key": "sk-proj-your-key-here",
  "model": "gpt-5.4",
  "godot_path": "/path/to/godot"
}
EOF
```

### 2. Use

```bash
# Single prompt
god-code ask "Add a health bar to the player scene" --project ./my-game

# Script-friendly plain output
god-code ask "Summarize this project" --project ./my-game --plain

# Interactive chat
god-code chat --project ./my-game

# Project info
god-code info --project ./my-game

# With reference image
god-code ask "Make the UI match this design" --project ./my-game -i reference.png
```

## API Configuration

### Supported Providers (BYOK)

God Code uses the OpenAI-compatible chat completions API. Any provider that supports this format works:

| Provider | Base URL | Model Example |
|----------|----------|---------------|
| **OpenAI** | `https://api.openai.com/v1` (default) | `gpt-4o`, `gpt-4o-mini` |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `openai/gpt-4o`, `anthropic/claude-sonnet-4-6` |
| **Anthropic** | Via OpenRouter or compatible proxy | `anthropic/claude-sonnet-4-6` |
| **Local models** | `http://localhost:11434/v1` (Ollama) | `llama3`, `codestral` |

```bash
# OpenRouter example (access all models with one key)
export GODOT_AGENT_API_KEY="sk-or-..."
export GODOT_AGENT_BASE_URL="https://openrouter.ai/api/v1"
export GODOT_AGENT_MODEL="anthropic/claude-sonnet-4-6"
```

### OAuth (Experimental)

God Code can use Codex CLI's refresh token for OAuth-based access:

```bash
# First login via Codex CLI
codex login

# Then god-code can use the cached credentials
god-code login    # Refreshes token from ~/.codex/auth.json
god-code status   # Shows current auth status
god-code logout   # Removes stored credentials
```

> **Note**: OAuth via Codex subscription tokens has limited API scope. For full API access (tool calling, vision), use an API key.

### Config File Reference

`~/.config/god-code/config.json`:

```json
{
  "api_key": "",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-5.4",
  "oauth_token": null,
  "mode": "apply",
  "max_turns": 20,
  "max_tokens": 4096,
  "temperature": 0.0,
  "auto_validate": true,
  "auto_commit": false,
  "streaming": true,
  "autosave_session": true,
  "screenshot_max_iterations": 5,
  "godot_path": "godot",
  "session_dir": ".agent_sessions"
}
```

All fields can be overridden with `GODOT_AGENT_` prefixed environment variables.

## Chat Commands

Interactive chat supports:

- `/mode [name]` — interactive mode menu (apply/plan/explain/review/fix)
- `/provider [name]` — interactive provider switcher with menu
- `/model [name]` — interactive model selection menu
- `/effort [level]` — reasoning effort (auto/minimal/low/medium/high/xhigh)
- `/settings` — interactive settings editor with menus for each option
- `/set <key> <value>` — quick inline setting change
- `/sessions` and `/resume [session-id]`
- `/new` to start a fresh session
- `/workspace` to re-render the session snapshot
- `/set <key> <value>` for live configuration changes

## System Prompt & Output Quality

God Code's system prompt is dynamically assembled from:

1. **Core identity** — Godot expert agent with composition-over-inheritance philosophy
2. **Godot Playbook** — 17 knowledge sections auto-selected by task keywords (collision, UI, animation, etc.)
3. **Build discipline** — mandatory incremental build-and-verify workflow
4. **Project context** — parsed from project.godot (name, autoloads, resolution, renderer)
5. **Tool catalog** — available tools with usage guidance

### Prompt Optimization

- Knowledge sections are scored by keyword relevance — only top 4 are injected per request (~2K tokens instead of ~15K)
- Build discipline rules prevent "write everything then test" anti-patterns
- Common Mistakes section is always included as a safety net
- Project context gives the LLM awareness of autoloads, resolution, and file structure

### Output Quality Tools

After the LLM generates code, God Code provides:

| Tool | What it checks |
|------|---------------|
| **tscn_validator** | .tscn format rules (sub_resource ordering, load_steps count) |
| **gdscript_linter** | Naming conventions, code ordering, type annotations, anti-patterns |
| **collision_planner** | Standard 8-layer collision scheme |
| **consistency_checker** | Cross-file collision/signal/resource path consistency |
| **pattern_advisor** | Object pool, component pattern, state machine suggestions |
| **dependency_graph** | Project-wide file dependency mapping |

## Security

God Code executes tools on your local machine. The LLM decides which tools to call.

**Path containment**: File operations (read/write/edit) are restricted to the project root directory. The agent cannot access files outside your project.

**Shell commands**: `run_shell` executes commands within the project directory. Review commands in the chat output before approving.

**API keys**: Stored in `~/.config/god-code/config.json` with `600` permissions. Never committed to git.

## MCP Server (for Claude Code / Codex / AI Agents)

God Code can run as an MCP (Model Context Protocol) server, exposing 12 Godot tools directly to AI agents. **No LLM middleman, zero token cost** — tools run locally.

### Install

```bash
pip install god-code[mcp]
```

### Configure in Claude Code

Add to `~/.claude.json` or Claude Desktop config:

```json
{
  "mcpServers": {
    "god-code": {
      "command": "god-code",
      "args": ["mcp", "--project", "/path/to/your/godot/project"]
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `validate_project` | Run Godot headless validation, return errors/warnings |
| `validate_tscn` | Check .tscn format, optionally auto-fix ordering |
| `lint_script` | GDScript style, naming, type annotation checks |
| `check_consistency` | Cross-file collision/signal/resource consistency |
| `plan_collision` | Generate standard 8-layer collision config |
| `analyze_dependencies` | Build project-wide dependency graph |
| `suggest_patterns` | Object pool, component, state machine suggestions |
| `parse_scene` | Parse .tscn into structured node tree |
| `project_info` | Read project.godot metadata |
| `godot_knowledge` | Query Godot 4.4 Playbook (17 knowledge sections) |
| `generate_sprite` | AI pixel art generation + post-processing |
| `validate_resources` | Check all res:// paths exist |

### How it works

```
Claude Code / Codex
    ↓ (MCP protocol over stdio)
god-code mcp process (local)
    ↓ (direct function calls)
Godot analysis tools (no LLM needed)
```

The AI agent gets Godot-native intelligence without you paying for an extra LLM layer.

## Architecture

```
godot_agent/
├── cli.py              # Click CLI (ask, chat, info, login, logout, status)
├── runtime/
│   ├── engine.py       # Conversation loop with tool calling
│   ├── config.py       # Config loading (file + env vars)
│   ├── session.py      # Session persistence
│   ├── oauth.py        # Codex OAuth token refresh
│   ├── error_loop.py   # Godot error detection and fix suggestions
│   └── context_manager.py  # Context window management
├── llm/
│   ├── client.py       # OpenAI-compatible API client
│   ├── streaming.py    # SSE streaming
│   └── vision.py       # Image encoding for multimodal
├── tools/              # 10 function-calling tools
├── godot/              # Godot-specific analysis
│   ├── project.py      # project.godot parser
│   ├── scene_parser.py # .tscn reader
│   ├── scene_writer.py # .tscn modifier
│   ├── tscn_validator.py
│   ├── gdscript_linter.py
│   ├── collision_planner.py
│   ├── consistency_checker.py
│   ├── dependency_graph.py
│   ├── pattern_advisor.py
│   └── resource_validator.py
└── prompts/            # System prompt construction
    ├── system.py
    ├── godot_playbook.py   # 17 knowledge sections
    ├── knowledge_selector.py
    └── build_discipline.py
```

## License

GPL-3.0 — see [LICENSE](LICENSE)

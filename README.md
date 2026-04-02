# God Code

AI coding agent specialized for Godot 4.4 game development. Unlike generic coding agents, God Code understands GDScript, .tscn scene files, collision layers, and Godot architecture patterns — and enforces incremental build-and-verify discipline.

## Features

- **10 tools**: read/write/edit files, grep/glob search, git, shell, Godot headless runner, screenshot capture
- **Godot-native understanding**: project.godot parser, .tscn scene parser/writer/validator, collision layer planner
- **Code quality**: GDScript linter (naming, ordering, type annotations), cross-file consistency checker, design pattern advisor
- **Smart knowledge injection**: 17 Godot Playbook sections auto-selected by task context
- **Build discipline**: incremental build-and-verify rules enforced via system prompt
- **Vision support**: send screenshots + reference images to multimodal LLMs

## Install

```bash
pip install god-code
```

Or from source:

```bash
git clone https://github.com/chuisiufai/god-code.git
cd god-code
pip install -e ".[dev]"
```

Requires Python 3.12+.

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
  "model": "gpt-4o",
  "godot_path": "/path/to/godot"
}
EOF
```

### 2. Use

```bash
# Single prompt
god-code ask "Add a health bar to the player scene" --project ./my-game

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
  "model": "gpt-4o",
  "oauth_token": null,
  "max_turns": 20,
  "max_tokens": 4096,
  "temperature": 0.0,
  "screenshot_max_iterations": 5,
  "godot_path": "godot",
  "session_dir": ".agent_sessions"
}
```

All fields can be overridden with `GODOT_AGENT_` prefixed environment variables.

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

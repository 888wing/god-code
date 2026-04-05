# God Code

[![GitHub stars](https://img.shields.io/github/stars/888wing/god-code?style=social)](https://github.com/888wing/god-code/stargazers)
[![Website](https://img.shields.io/badge/website-godcode.dev-39ff14)](https://godcode.dev)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-1f6feb)](https://888wing.github.io/god-code/)

**AI coding agent for Godot 4.x game development.** Understands GDScript, `.tscn` scenes, collision layers, and Godot architecture patterns. 41 tools, vision-driven UI iteration, live runtime bridge, automated quality gates.

**Website:** [godcode.dev](https://godcode.dev)

## What It Does

- **41 Godot-specific tools** — scene parser, GDScript linter, collision planner, dependency graph, sprite generation, visual regression
- **Vision loop** — screenshots your game, analyzes with LLM vision, suggests fixes, re-screenshots, scores the result
- **Live bridge** — TCP connection to running Godot via GodCodeBridge plugin (port 9394)
- **Quality gates** — validates, lints, reviews, and playtests after every change
- **Design memory** — remembers gameplay intent, control rules, visual style across sessions
- **MCP server** — expose all tools to Claude Code, Codex, and other agent hosts

## Install

Requires **Python 3.12+**.

```bash
# Recommended
pipx install god-code

# Or with pip
pip install god-code

# For development
git clone https://github.com/888wing/god-code.git
cd god-code && pip install -e ".[dev,mcp]"
```

## Quick Start

```bash
god-code chat --project ./my-game
```

First run launches a setup wizard for provider and API key.

## Upgrade

```bash
# Check your version
god-code --version

# Inside chat, check for updates
/version

# Upgrade
pipx upgrade god-code          # if installed via pipx
pip install --upgrade god-code  # if installed via pip
git pull                        # if cloned from GitHub
```

god-code checks for updates on startup and shows a yellow prompt when a new version is available.

## Chat Commands

| Command | Description |
|---------|-------------|
| `/help` | show all commands |
| `/version` | show current version and check for updates |
| `/mode [name]` | show or change mode (apply/plan/explain/review/fix) |
| `/provider [name]` | switch LLM provider |
| `/model [name]` | switch model |
| `/effort [level]` | switch reasoning effort |
| `/skills [cmd]` | list or toggle internal skills |
| `/intent [cmd]` | show or confirm gameplay intent |
| `/cd <path>` | change project directory |
| `/menu` | interactive command palette |
| `/settings` | show all settings |
| `/set <key> <val>` | change a setting |
| `/save` | save session |
| `/resume [id]` | resume a saved session |
| `/new` | start a fresh session |
| `/exit` | exit (also: `/quit`, Ctrl+C) |

## Who It's For

- Godot developers who want an AI pair-programmer that understands game code and scene structure
- Teams iterating on mechanics, UI flows, and gameplay systems inside an existing Godot project
- Agent users who want local Godot tools via MCP without an extra LLM layer

## Providers

| Provider | Default Model | Notes |
|----------|---------------|-------|
| OpenAI | `gpt-5.4` | Primary, vision support |
| Anthropic | `claude-sonnet-4.6` | Direct API |
| Gemini | `gemini-3.1-pro` | Native vision via backend |
| OpenRouter | `openai/gpt-5.4` | Aggregated routing |
| xAI | `grok-4` | xAI API |
| Custom | — | Local/self-hosted endpoints |

## Backend Orchestration

god-code can route LLM requests through the [god-code-api](https://github.com/888wing/god-code-api) backend for smart model routing, quality scoring, and usage tracking.

```json
{
  "backend_url": "https://god-code-api.nano122090.workers.dev",
  "backend_api_key": "gc_live_..."
}
```

**BYOK** (Bring Your Own Key) users get all features for free. Platform keys provide managed infrastructure with usage dashboards.

## MCP Server

Expose Godot tools to Claude Code and other agent hosts:

```bash
god-code mcp --project /path/to/project
god-code tools  # list available tools
```

### Claude Code Skill

```bash
mkdir -p ~/.claude/skills/god-code-setup
curl -sL https://raw.githubusercontent.com/888wing/god-code/main/skills/god-code-setup/SKILL.md \
  -o ~/.claude/skills/god-code-setup/SKILL.md
```

## Architecture

```
godot_agent/
├── cli/                    # CLI package (commands, menus, engine wiring, helpers)
├── runtime/                # Engine loop, quality gates, reviewer, live bridge, design memory
├── llm/                    # LLM client (dual-path: direct + backend), streaming, adapters
├── tools/                  # 41 tools: file ops, scene, script, vision, sprite, search, git
├── godot/                  # Parsers, validators, linters, collision planner
├── prompts/                # Prompt assembly, skills, playbook, vision templates
├── addons/                 # GodCodeBridge Godot plugin (GDScript)
├── security/               # Tool pipeline, policies, protected paths
└── tui/                    # Rich display, input handling
```

## Testing

```bash
.venv/bin/pytest -q          # 620+ tests
```

## Support

- Star the repo: [github.com/888wing/god-code](https://github.com/888wing/god-code/stargazers)
- Website: [godcode.dev](https://godcode.dev)
- Docs: [888wing.github.io/god-code](https://888wing.github.io/god-code/)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

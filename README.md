# God Code

[![GitHub stars](https://img.shields.io/github/stars/888wing/god-code?style=social)](https://github.com/888wing/god-code/stargazers)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-1f6feb)](https://888wing.github.io/god-code/)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/nano122090n)

God Code is an AI coding agent for **Godot 4.x game development**. It understands GDScript, `.tscn` scene files, resources, collision layers, and common Godot architecture patterns, then wraps model output in a local tool pipeline with validation, review, and playtest-oriented checks.

The project is aimed at developers building **original Godot games**, not just template projects. The goal is to help you turn design intent into working gameplay without losing control of your codebase.

## What God Code Is Good At

- Reading and editing Godot projects with **Godot-aware tools**
- Understanding `.gd`, `.tscn`, `project.godot`, resources, signals, and scene trees
- Keeping track of **design memory**, gameplay intent, and change impact
- Inferring **gameplay direction** and confirming genre/combat/enemy profiles in the TUI when needed
- Running **quality gates** after changes: validation, linting, consistency checks, dependency analysis
- Running **reviewer / playtest-style passes** instead of stopping at “code looks fine”
- Giving you a **workspace-style chat TUI** with sessions, menus, and live configuration
- Exposing the same Godot-native capabilities over **MCP** for Claude Code, Codex, and other agent hosts

## Who It's For

- Godot developers who want an AI pair-programmer that understands game code and scene structure
- Teams iterating on mechanics, UI flows, and gameplay systems inside an existing Godot project
- Agent users who want **local Godot tools** via MCP without paying for an extra LLM layer

## What It's Not

- Not a no-code game generator
- Not a template-only game builder
- Not a replacement for playtesting, art direction, or core game design decisions
- Not a sandbox for arbitrary system access outside your project root

## Core Capabilities

- **Interactive CLI agent**
  `chat`, `ask`, `setup`, `status`, `info`, `tools`, session recovery, mode switching, provider/model switching, inline settings, gameplay intent checkpoints
- **Godot-native editing**
  scene tree inspection, scene mutation, script editing, file ops, search, project scanning
- **Validation and review**
  project validation, GDScript linting, scene/resource consistency, dependency graph, impact analysis, reviewer and gameplay reviewer stages
- **Runtime and playtest tooling**
  runtime snapshot bridge, profile-aware playtest harness, viewport capture, baseline comparison, failure bundle reporting
- **Gameplay-intent system**
  genre/combat/enemy-profile inference, `/intent` commands, persistent design-memory intent storage, profile-aware skill routing
- **Asset helpers**
  sprite generation, sprite sheet slicing, sprite import validation, visual regression artifacts
- **Provider flexibility**
  OpenAI, Anthropic, OpenRouter, Gemini, xAI, GLM / Z.AI, MiniMax, and custom/self-hosted endpoints
- **MCP server**
  expose Godot-native tools directly to other agents with no built-in LLM in the loop

## Install

God Code requires **Python 3.12+**.

```bash
pip install god-code
```

With MCP support:

```bash
pip install "god-code[mcp]"
```

For local development:

```bash
git clone https://github.com/888wing/god-code.git
cd god-code
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
```

If you want validation, playtest, or screenshot flows to work, you also need a usable **Godot executable** on your machine.

## First Run

The easiest way to start is:

```bash
god-code chat --project ./my-game
```

If you are in an interactive terminal and have not configured credentials yet, God Code will launch a **setup wizard** and ask for:

1. provider
2. API key or OAuth path
3. optional base URL / model overrides

You can also run setup explicitly:

```bash
god-code setup
```

Once inside chat, use:

- `/menu` for the interactive command menu
- `/provider` to switch provider
- `/model` to switch model
- `/intent` to inspect or confirm gameplay direction
- `/settings` to edit all config fields
- `/resume` to restore a saved session
- `"""` to start multiline input

If the project sends mixed gameplay signals, God Code may pause to ask 1 to 3 short **intent confirmation** questions before making architecture-level combat or enemy changes.

## Common Workflows

### 1. Ask for a one-shot change

```bash
god-code ask "Add a health bar to the player HUD" --project ./my-game
```

### 2. Work interactively inside a project

```bash
god-code chat --project ./my-game
```

Typical chat flow:

1. inspect project context
2. confirm gameplay intent if needed
3. switch mode if needed
4. make a request
5. let God Code edit and validate
6. review results or resume later

### 3. From an empty project to the first verified change

If you want a concrete walkthrough instead of isolated commands, start here:

- [From Empty Project To First Verified Change](docs/empty-project-to-first-verified-change.md)
- [Docs Site](https://888wing.github.io/god-code/)

This example covers:

1. creating the smallest valid Godot project root
2. launching `god-code chat`
3. handling first-run BYOK setup
4. making a safe first scene/script change
5. checking what counts as a verified result

## Documentation

- Docs site: [888wing.github.io/god-code](https://888wing.github.io/god-code/)
- Docs source: [`docs/`](docs/)
- Local preview:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[docs]"
mkdocs serve
```

## Gameplay Intent And Genre Skills

God Code does not assume one universal enemy AI model for every game. It now tries to infer a **gameplay profile** from:

- `project.godot`
- input actions
- scene and script naming
- design memory
- the current request

If confidence is low, or if the project mixes signals such as shooter and tower-defense mechanics, use:

```text
/intent
/intent confirm
/intent edit
/intent clear
```

The confirmed profile is stored in project design memory and reused by planning, implementation, review, and playtest flows.

### Current genre-aware internal skills

- `bullet_hell`
- `topdown_shooter`
- `platformer_enemy`
- `tower_defense`
- `stealth_guard`
- `collision`
- `physics`

### Current support boundary

For open-source users, it is important to treat the genre system as **tiered support**, not universal gameplay generation.

First-class genre support currently targets:

- `bullet_hell`
- `topdown_shooter`
- `platformer_enemy`
- `tower_defense`

For these genres, God Code is intended to infer a stable gameplay profile, route to matching internal skills, and steer enemy/combat work toward the correct architecture.

Everything else currently falls back to more general Godot-aware reasoning. That means God Code may still help, but it does **not** yet guarantee a complete genre-specific enemy-system scaffold for:

- stealth-heavy guard AI
- 3D action combat
- RTS / squad tactics
- turn-based tactics or card battlers
- multiplayer / netcode-driven combat
- economy or simulation-heavy games

If you are working on enemies, bosses, combat loops, waves, or gameplay architecture, use `/intent` early in chat to confirm direction before asking for large system changes.

God Code does not aim to generate one universal enemy AI for every game. It first tries to identify the gameplay profile, then applies the most appropriate architecture for that genre.

### 4. Plan before editing

Inside chat:

```text
/mode plan
```

Then ask for the change. In `plan` mode, God Code should inspect and propose an implementation strategy without mutating files.

### 5. Review or debug an existing change

```text
/mode review
```

or

```text
/mode fix
```

Use `review` for bug/risk-finding and `fix` for reproduce-repair-validate loops.

## BYOK, Providers, and Model Switching

God Code supports both **interactive BYOK** and config/env-based setup.

### Interactive

Inside chat:

- `/menu -> Switch provider`
- `/menu -> Switch model`
- `/menu -> Edit setting -> api_key`
- `/menu -> Edit setting -> oauth_token`

Sensitive fields use hidden input. If you switch to a provider that needs a different key, God Code will prompt for it.

### Environment variables

```bash
export GODOT_AGENT_API_KEY="sk-..."
export GODOT_AGENT_MODEL="gpt-5.4"
export GODOT_AGENT_BASE_URL="https://api.openai.com/v1"
```

### Config file

Default path:

```text
~/.config/god-code/config.json
```

Example:

```json
{
  "provider": "openai",
  "api_key": "sk-...",
  "model": "gpt-5.4",
  "godot_path": "godot",
  "mode": "apply",
  "streaming": true,
  "autosave_session": true
}
```

### Built-in provider presets

| Provider | Default Model | Notes |
|----------|---------------|-------|
| OpenAI | `gpt-5.4` | Supports OAuth and computer-use settings |
| Anthropic | `claude-sonnet-4.6` | Direct Anthropic preset |
| OpenRouter | `openai/gpt-5.4` | Aggregated routing |
| Gemini | `gemini-3.1-pro` | OpenAI-compatible Google endpoint |
| xAI | `grok-4` | xAI API |
| GLM / Z.AI | `glm-5` | Z.AI platform |
| MiniMax | `MiniMax-M2.5` | MiniMax API |
| Custom | none | For local/self-hosted/other compatible endpoints |

For a `custom` provider, API keys are optional at the tool level because some local/self-hosted endpoints do not require them.

## CLI vs MCP

### Use the CLI when you want:

- a full LLM-driven agent
- interactive chat
- provider/model switching
- sessions and `/resume`
- quality gates, reviewer flow, and chat UX

### Use MCP when you want:

- local Godot-native tools exposed to another agent host
- no built-in chat loop
- no additional LLM layer inside God Code itself

Start the MCP server with:

```bash
god-code mcp --project /path/to/project
```

List available MCP tools with:

```bash
god-code tools
```

### Claude Code skill setup

If you use Claude Code, install the bundled setup skill:

```bash
mkdir -p ~/.claude/skills/god-code-setup
curl -sL https://raw.githubusercontent.com/888wing/god-code/main/skills/god-code-setup/SKILL.md \
  -o ~/.claude/skills/god-code-setup/SKILL.md
```

Then ask Claude Code to install and configure God Code for you.

## How a Change Flows Through the System

At a high level, an `apply` or `fix` request looks like this:

1. build prompt from project context, design memory, mode, and selected skills
2. inspect project files and scene/script structure
3. execute local tools through the security/tool pipeline
4. run validation and quality gates after mutations
5. run reviewer / gameplay review / playtest-style checks when applicable
6. return a summary that distinguishes verified outcomes from assumptions

This is the main difference between God Code and a plain “LLM that edits files”.

## Chat Commands

Core commands inside chat:

- `/menu` interactive command palette
- `/mode [apply|plan|explain|review|fix]`
- `/provider [name]`
- `/model [name]`
- `/effort [auto|minimal|low|medium|high|xhigh]`
- `/skills [list|on <name>|off <name>|auto|clear]`
- `/settings`
- `/set <key> <value>`
- `/status`
- `/workspace`
- `/sessions`
- `/resume [session-id|latest]`
- `/new`
- `/save`
- `/cd <path>`
- `/help`
- `/quit`

Top-level CLI commands:

- `god-code`
- `god-code chat`
- `god-code ask`
- `god-code setup`
- `god-code status`
- `god-code info`
- `god-code login`
- `god-code logout`
- `god-code mcp`
- `god-code tools`

## Safety and Limits

- **Project-root containment**
  file tools are restricted to the active project root
- **Mode-aware tool access**
  `plan` and `review` are intended for inspection, not broad mutation
- **Shell safety**
  shell commands go through a safety policy instead of raw unrestricted execution
- **Interactive setup only in interactive terminals**
  non-interactive CLI usage will not launch setup prompts for you
- **Runtime features depend on local environment**
  validation, runtime harness, screenshots, and playtests need a working Godot setup
- **Custom providers must still be compatible with the flows you use**
  especially tool calling, structured outputs, and multimodal features

## Architecture Overview

```text
godot_agent/
├── cli.py                    # chat/ask/setup/status/mcp entrypoints
├── entrypoint.py             # Python-version guard before importing cli
├── agents/                   # planner / explorer / reviewer / playtest analyst configs
├── runtime/
│   ├── engine.py             # main agent loop and orchestration
│   ├── quality_gate.py       # post-change validation aggregation
│   ├── reviewer.py           # technical review pass
│   ├── gameplay_reviewer.py  # gameplay-oriented review pass
│   ├── playtest_harness.py   # scenario and runtime-based verification
│   ├── runtime_bridge.py     # runtime snapshot bridge
│   ├── design_memory.py      # gameplay/design memory
│   ├── config.py             # config loading and defaults
│   └── session.py            # autosave and resume
├── security/                 # tool pipeline, policies, hooks, protected paths
├── tools/                    # file, scene, script, analysis, runtime, asset, web tools
├── godot/                    # Godot parsers, validators, analyzers
├── prompts/                  # prompt assembly, skills, playbook, selection
└── mcp_server.py             # MCP tool server
```

## Testing

The repository includes unit, integration, TUI, CLI, runtime, and end-to-end style tests.

Run the full suite with the project virtualenv:

```bash
.venv/bin/pytest -q
```

Do not rely on a random system `pytest` if it points to an older Python runtime than the project supports.

## Support

If God Code is useful in your Godot workflow:

- Star the repo: [github.com/888wing/god-code/stargazers](https://github.com/888wing/god-code/stargazers)
- Share the docs: [888wing.github.io/god-code](https://888wing.github.io/god-code/)
- Support development: [buymeacoffee.com/nano122090n](https://buymeacoffee.com/nano122090n)
- Use the repo `Sponsor` button for the same support links

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

---
name: god-code-setup
description: Install and configure God Code — the AI coding agent for Godot 4.4 game development. Use when the user wants to set up god-code, configure MCP server for Claude Code, or start a Godot project with AI assistance. Triggers on keywords like god-code, godot agent, godot mcp, godot ai, setup godot tools.
---

# God Code Setup

Automated installation and MCP server configuration for God Code — the Godot 4.4 AI development toolkit.

## What This Does

1. Installs god-code from PyPI (with MCP support)
2. Configures MCP server so Claude Code gets 12 Godot tools
3. Verifies everything works

## Step 1: Install

```bash
pip install god-code[mcp]
```

If pip fails on macOS (externally-managed-environment):
```bash
pip install --user god-code[mcp]
```

Verify:
```bash
god-code --version
```

## Step 2: Configure API Key (if not already set)

Run the setup wizard:
```bash
god-code setup
```

Or set manually:
```bash
mkdir -p ~/.config/god-code
cat > ~/.config/god-code/config.json << 'EOF'
{
  "api_key": "YOUR_API_KEY_HERE",
  "model": "gpt-5.4",
  "godot_path": "/Applications/Godot.app/Contents/MacOS/Godot"
}
EOF
chmod 600 ~/.config/god-code/config.json
```

## Step 3: Configure MCP Server for Claude Code

Add god-code as an MCP server so Claude Code gets Godot tools directly:

```bash
# Find the Claude Code config location
CONFIG_DIR="${HOME}/.claude"
mkdir -p "$CONFIG_DIR"

# Check if settings file exists, create or update
SETTINGS_FILE="$CONFIG_DIR/settings.json"
```

The MCP server config that needs to be added:

```json
{
  "mcpServers": {
    "god-code": {
      "command": "god-code",
      "args": ["mcp", "--project", "."]
    }
  }
}
```

For project-specific setup, the `--project` arg should point to the Godot project root.

## Step 4: Verify MCP Connection

After configuring, Claude Code will have these tools available:

| Tool | Description |
|------|-------------|
| `validate_project` | Run Godot headless validation |
| `validate_tscn` | Check .tscn format + auto-fix |
| `lint_script` | GDScript quality checks |
| `check_consistency` | Cross-file consistency |
| `plan_collision` | Standard collision layers |
| `analyze_dependencies` | Project dependency graph |
| `suggest_patterns` | Design pattern suggestions |
| `parse_scene` | Parse .tscn structure |
| `project_info` | Read project.godot |
| `godot_knowledge` | Query Godot Playbook |
| `generate_sprite` | AI pixel art generation |
| `validate_resources` | Check res:// paths |

## Usage After Setup

### As CLI (interactive chat):
```bash
god-code
cd ~/Projects/my-godot-game
# Start chatting with the agent
```

### As MCP Server (Claude Code uses tools directly):
Claude Code automatically calls god-code tools when working on Godot projects. No extra commands needed.

### Key CLI Commands:
- `/mode [apply|plan|explain|review|fix]` — change interaction mode
- `/provider [name]` — switch LLM provider
- `/settings` — view/change all settings
- `/usage` — token usage and cost

## Troubleshooting

**god-code not found**: Make sure pip installed to a directory in your PATH. Try `python3 -m pip install --user god-code[mcp]`.

**MCP tools not appearing**: Restart Claude Code after adding the MCP config. Check `god-code mcp --help` works.

**Godot validation fails**: Set the correct Godot path in config: `god-code setup` or `/set godot_path /path/to/godot`.

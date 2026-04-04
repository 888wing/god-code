# MCP Overview

God Code can run as an MCP server so other agent hosts can call its Godot-native tools directly.

## Start The Server

```bash
god-code mcp --project /path/to/project
```

## List Tools

```bash
god-code tools
```

## When To Use MCP

Use MCP when:

- you already have another host agent such as Claude Code or Codex
- you want direct local tool execution
- you do not need God Code's own chat UX

## When To Use CLI Instead

Use `god-code chat` or `god-code ask` when you want:

- the built-in interactive workflow
- session restore
- provider/model switching in the same tool
- God Code's own prompt assembly and orchestration loop

## Claude Code Example

```json
{
  "mcpServers": {
    "god-code": {
      "command": "god-code",
      "args": ["mcp", "--project", "/path/to/project"]
    }
  }
}
```

MCP is the right choice when you want God Code's Godot intelligence as infrastructure for another agent, not as the chat frontend itself.

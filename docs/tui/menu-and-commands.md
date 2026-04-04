# Menu And Commands

The interactive TUI is designed so common operations do not require memorizing every slash command.

## Main Entry

```text
/menu
```

This opens the command palette for:

- mode changes
- provider/model switching
- settings edits
- session resume
- workspace refresh
- status/settings display

## Core Commands

- `/menu`
- `/mode`
- `/provider`
- `/model`
- `/effort`
- `/skills`
- `/intent`
- `/settings`
- `/set <key> <value>`
- `/sessions`
- `/resume`
- `/new`
- `/save`
- `/cd <path>`
- `/status`
- `/workspace`

## Multiline Input

Start a multiline prompt with:

```text
"""
```

Finish with another line containing only:

```text
"""
```

If you cancel before completion, the message is not submitted.

## Best Practice

Use `/menu` for discovery and hidden-input flows, but keep `/set ...` for fast repeat operations once you already know the exact key.

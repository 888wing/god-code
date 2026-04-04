# Chat

Use `chat` when you want the full interactive agent loop: menus, sessions, provider/model switching, validation feedback, and follow-up turns in the same workspace.

## Command

```bash
god-code chat --project ./my-game
```

## When To Use It

- you are iterating on a Godot project
- you expect multiple back-and-forth turns
- you want `/menu`, `/resume`, `/intent`, `/settings`, or live mode switching

## What Happens

1. config is loaded
2. setup wizard runs if needed and interactive
3. project context is scanned if a Godot project is detected
4. the workspace TUI renders
5. your request goes through planning, tool execution, validation, and review as applicable

## Typical Session

```text
/status
/mode apply
Create a minimal main menu scene and validate it.
/resume
/settings
```

## Verified vs Inferred

`chat` can surface both verified and inferred information in the same session. Treat these differently:

- verified: tool output, validation, reviewer output, playtest/runtime evidence
- inferred: design intent guesses, skill selection, model reasoning before validation

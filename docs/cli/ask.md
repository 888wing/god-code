# Ask

Use `ask` when you want a **single-shot agent turn** instead of an interactive session.

## Command

```bash
god-code ask "Add a health bar to the player HUD" --project ./my-game
```

## Good Use Cases

- quick project inspection
- one small code or scene change
- scriptable shell usage
- CI-style helper flows with `--plain`

## Examples

```bash
god-code ask "Summarize this project" --project ./my-game --plain
god-code ask "Create a minimal pause menu scene and validate it" --project ./my-game
god-code ask "Match this HUD layout" --project ./my-game -i reference.png
```

## When Not To Use It

Prefer `chat` if you need:

- provider/model switching during the session
- `/resume`
- multiple iterative requests
- TUI workflow features

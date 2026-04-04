# First Run

## Fastest Path

```bash
god-code chat --project ./my-game
```

If no usable credentials are configured and the terminal is interactive, God Code launches the setup wizard.

## What First Run Asks For

1. provider
2. API key or OAuth path
3. optional model/base URL adjustments

## What To Check Immediately After Setup

Run inside chat:

```text
/status
```

Check:

- provider
- model
- auth state
- project path
- `godot_path` if you expect validation to work

## Common First-Run Fixes

### Godot executable is missing

Set it inside chat:

```text
/set godot_path /absolute/path/to/godot
```

or:

```text
/menu -> Edit setting -> godot_path
```

### Wrong provider or model

Use:

```text
/provider
/model
```

### Need to edit API key later

Use:

```text
/menu -> Edit setting -> api_key
```

Sensitive values use hidden input.

# Settings And BYOK

God Code supports both configuration-file setup and live interactive updates from inside chat.

## Best Interactive Path

Use:

```text
/menu -> Edit setting
```

This exposes all common config fields, including:

- `api_key`
- `oauth_token`
- `provider`
- `model`
- `base_url`
- `godot_path`
- `mode`
- `reasoning_effort`
- `streaming`
- `session_dir`

## Sensitive Fields

These use hidden input:

- `api_key`
- `oauth_token`

They are also masked in status/settings output.

## Switching Provider

Inside chat:

```text
/provider
```

or:

```text
/menu -> Switch provider
```

If the new provider requires a different key, God Code will prompt for it.

## Inline Overrides

Examples:

```text
/set model gpt-5.4
/set godot_path /Applications/Godot.app/Contents/MacOS/Godot
/set streaming false
```

Use inline commands when you already know the exact setting name and value.

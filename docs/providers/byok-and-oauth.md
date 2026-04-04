# BYOK And OAuth

God Code supports provider API keys and limited OAuth-based flows.

## API Key Setup

Interactive:

```text
/menu -> Edit setting -> api_key
```

Environment:

```bash
export GODOT_AGENT_API_KEY="sk-..."
```

Config file:

```json
{
  "provider": "openai",
  "api_key": "sk-..."
}
```

## OAuth

For OpenAI-related flows, God Code can use Codex CLI refresh-token login paths:

```bash
god-code login
god-code status
god-code logout
```

## Provider Switching

When switching provider, also verify:

- the key matches the provider
- the model is valid for that provider
- the endpoint supports the features you want to use

## Custom Provider

`custom` is intended for local or self-hosted compatible endpoints. In that mode, credentials may be optional depending on your server.

# Privacy

`god-code` is designed around two principles:

1. **Local-first** — your code, your API keys, your conversations, and your session history all live on your machine. We do not upload them.
2. **Data minimization** — when data does leave your machine, it's only what the LLM provider needs to do its job, and only what you explicitly chose to send.

This document explains what happens to your data at every step.

## What god-code handles on your machine

When you use `god-code`, the CLI reads and writes files on your local disk:

| Location | Content | Permissions |
|----------|---------|-------------|
| `~/.config/god-code/config.json` | Your provider API keys, preferences | `0o600` (owner-only) |
| `~/.config/god-code/auth.json` | OAuth tokens (if you use `god-code login`) | `0o600` (owner-only) |
| `<project>/.agent_sessions/*.json` | Conversation history per session | `0o600` (owner-only) |

None of these files are ever uploaded by `god-code` itself. If you delete them, all local god-code state is gone.

## Data flow

### BYOK mode (default)

When you configure a provider API key in setup:

```
your CLI → LLM provider (OpenAI / Anthropic / Gemini / xAI / OpenRouter)
```

`god-code-api` is **not involved**. Your request goes straight from your machine to the provider you chose. The provider's privacy policy applies to that traffic.

### Platform mode (opt-in, requires `gc_live_*` key)

When you authenticate with a platform API key:

```
your CLI → god-code-api → LLM provider
```

`god-code-api` routes your request to an appropriate provider and tracks token usage for billing, but **does not persist the request content**.

## What god-code-api stores server-side

Verified against the source code as of this document's date. Specifically, the only `INSERT INTO` statements in the backend source tree write to two tables:

| Table | Fields | Content? |
|-------|--------|----------|
| `api_keys` | `id`, `user_id`, `key_hash`, `label`, `quota_total`, `quota_remaining`, `quota_reset_at`, `is_active`, `created_at`, `last_used_at` | No. Key is stored as a **hash** — the plaintext `gc_live_*` value is never persisted. |
| `usage_log` | `id`, `api_key_id`, `timestamp`, `agent_role`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_estimate`, `quality_score` | No. Only counts and metadata. |

### Explicitly NOT stored by god-code-api

- **Prompt content** — the messages you send to the LLM
- **Completion content** — the model's responses
- **Your Godot project files** — the code the agent reads or modifies
- **Your session history** — every turn of your conversation
- **Your IP address** — does not appear in any D1 table
- **Your plaintext API keys** — neither platform nor provider keys are stored in plaintext

The only user data anywhere on god-code infrastructure beyond the above is waitlist email addresses (see below).

## Waitlist

If you joined the waitlist at **godcode.dev**, we store your email address and the join timestamp in Cloudflare KV.

- **What**: `{email, joined_at}`
- **Where**: Cloudflare KV, `waitlist:{email}` key
- **Retention**: **Until the public launch concludes**, then purged
- **Deletion on request**: email `info@do-va.com` and we will remove your entry immediately

## Third-party LLM providers

When you send a request through a provider, whether BYOK or platform mode, that provider sees:

- Your messages (the conversation)
- Any tool calls and their results
- Any project file contents you told the agent to read
- Any screenshots the agent captured

Each provider has its own privacy policy. Review the provider you choose. Examples:

- OpenAI: https://openai.com/policies/privacy-policy
- Anthropic: https://www.anthropic.com/legal/privacy
- Google Gemini: https://ai.google.dev/gemini-api/terms

## Your rights and controls

You can, at any time:

- **Delete all local state** — remove `~/.config/god-code/` and `.agent_sessions/` directories
- **Revoke a platform key** — contact `info@do-va.com` (self-service dashboard is a post-launch feature)
- **Query your usage** — `GET /v1/usage` with `Authorization: Bearer gc_live_*`
- **Request waitlist deletion** — email `info@do-va.com`
- **Request a copy of stored data** (GDPR/CCPA Access Right) — email `info@do-va.com`
- **Request deletion of stored data** (GDPR/CCPA Right to Erasure) — email `info@do-va.com`

## What we do not do

- No telemetry
- No analytics scripts in the CLI
- No background data collection
- No advertising third parties
- No data sales

## Changes to this policy

We may revise this policy. Material changes will be announced in the project `README.md` and `CHANGELOG.md`. The policy version in effect at the time you use the tool applies.

## Contact

Data protection inquiries, privacy questions, access/deletion requests: **info@do-va.com**

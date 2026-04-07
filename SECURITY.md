# Security Policy

## Supported versions

Security fixes are released for the current minor version only. Older versions do not receive patches.

| Version | Supported |
|---------|-----------|
| 0.9.x   | Yes       |
| < 0.9   | No — please upgrade |

`god-code` checks for updates on startup via `GET /v1/version`. Outdated users see a yellow update prompt; unsupported users see a red warning.

## Reporting a vulnerability

**Email:** `info@do-va.com`

Please include:

- Affected version (output of `god-code --version`)
- Operating system and Python version
- Reproduction steps, or a minimal proof-of-concept
- Your assessment of impact (data at risk, attack prerequisites)
- Whether you plan to disclose publicly, and your preferred timeline

We aim to acknowledge reports within **5 business days** and provide an initial assessment within 10 business days. Fix timeline depends on severity and complexity.

## Disclosure policy

Please hold public disclosure until a fix is released. We will credit reporters in the release notes unless they request otherwise. If you believe a vulnerability is actively being exploited, state this clearly in the email subject.

## Scope

### In scope

- `god-code` Python package (this repo): https://github.com/888wing/god-code
- `god-code-api` backend: https://github.com/888wing/god-code-api
- `god-code-site` landing page: https://github.com/888wing/god-code-site
- Any infrastructure directly operated by the `god-code` project (Cloudflare Workers, D1, KV, Pages)

### Out of scope

- **User-supplied BYOK LLM provider vulnerabilities** (OpenAI, Anthropic, Gemini, xAI, OpenRouter). Report these to the provider directly.
- **Vulnerabilities in user's own Godot projects** that god-code operates on. god-code is a development tool — the code it reads and writes is the user's responsibility.
- **Social engineering** targeting god-code users or maintainers.
- **Denial-of-service** against public endpoints without demonstrated impact on confidentiality or integrity.
- **Issues in upstream dependencies** unless the vulnerable path is reachable through god-code's public API or CLI surface.

## What we consider a security issue

Examples we would want to know about:

- A way to read another user's API key, config, or session file
- A path traversal or command injection reachable through any tool (file_ops, shell, git, godot_cli)
- Insufficient redaction of secrets in error messages or logs returned to clients
- Improper validation on `POST /v1/orchestrate` or `POST /v1/admin/keys`
- Any way for an unauthenticated caller to consume platform quota
- Leakage of `gc_live_*` plaintext keys in any code path

## Data handling

For details on what data god-code handles, where it is stored, and how long it is retained, see [`PRIVACY.md`](PRIVACY.md).

## Contact

`info@do-va.com`

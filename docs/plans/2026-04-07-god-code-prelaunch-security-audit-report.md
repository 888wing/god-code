# God Code Pre-launch Security Audit Report

**Date completed:** 2026-04-07
**Auditor:** Claude (Opus 4.6) with user-in-loop decisions
**Design doc:** [`2026-04-07-god-code-prelaunch-security-audit-design.md`](./2026-04-07-god-code-prelaunch-security-audit-design.md) (`95aef4f`)
**Plan doc:** [`2026-04-07-god-code-prelaunch-security-audit.md`](./2026-04-07-god-code-prelaunch-security-audit.md) (`b4a4f87`)

## Summary

**Launch decision: READY.**

Three-track audit of `god-code`, `god-code-api`, and `god-code-site` found **zero active security risks**. All three repositories and their published/deployed artifacts are clean of secrets, the backend does not store user content, and the landing page has no tracking or analytics. Pre-launch hardening is complete.

**Findings statistics:**

| Severity | Count | Status |
|----------|-------|--------|
| 🔴 Active leak | 0 | — |
| 🟠 Serious risk | 0 | — |
| 🟡 Hygiene | 1 | Corrected (see Audit Correction below) |
| ℹ️ Informational | 2 | Documented, out of security scope |

## Scope

Three audit tracks per the design document:

- **Track A** — Secrets in repos and published artifacts
- **Track B** — Deployment secrets and runtime log hygiene
- **Track C** — User data handling (CLI, backend, waitlist)

The following were explicitly out of scope and deferred to post-launch hardening:

- CLI local storage upgrade to OS Keychain
- OAuth device flow between CLI and godcode.dev
- Website self-serve key issuance
- CI integration of `gitleaks` (GitHub Actions)
- Dependency vulnerability scanning (`pip-audit`, `npm audit`)
- Rate limiting on `/v1/admin/keys`
- Responsible disclosure program beyond email contact

## Track A — Repo and published artifact secrets

### A.1 Full-history secret scans (gitleaks)

| Repo | Commits scanned | Raw findings | Actionable |
|------|-----------------|--------------|------------|
| `god-code` | 110 | 3 | 0 |
| `god-code-api` | 25 | 1 | 0 |
| `god-code-site` | 2 | 0 | 0 |

All 4 raw findings triaged to false positive:

1. `god-code/docs/plans/2026-04-05-v08-impl.md:761` — `gc_live_testkey123` (design doc example)
2. `god-code/docs/plans/2026-04-05-v08-impl.md:809` — `gc_live_xxx` (curl example)
3. `god-code/tests/test_runtime_switch_commands.py:108` — `sk-1234567890` (test fixture for the secret-masking function `_format_setting_display_value`)
4. `god-code-api/tests/util/redact.test.ts:11,16,22,44` — fake JWT/Bearer/sk-/gc_live_ tokens (test fixtures for the `redactSecrets()` utility)

All 4 are intentional test fixtures or documentation examples for security-utility code paths. They cannot be removed without breaking the tests that validate the masking/redaction features. They are allowlisted in the per-repo `.gitleaks.toml` files added in Phase 7.

### A.2 PyPI wheel inspection

- **Published version audited:** 0.6.1 (users currently install this via `pipx install god-code`)
- **Local repo version at audit time:** 0.9.1 (not yet on PyPI)
- **Files in 0.6.1 wheel:** 91 (86 under `godot_agent/` package + 5 dist-info)
- **Sensitive file scan (config.json / auth.json / .env / .key / .pem / agent_sessions / .codetape):** 0 matches
- **Decision:** Pass. Belt-and-suspenders exclude list added to `pyproject.toml` for future releases (commit `f34b716`).

### A.3 Test fixture credential scan

- `god-code/tests/`: 0 matches
- `god-code-api/tests/`: 3 matches (all in `redact.test.ts`, same false-positive pattern as A.1)
- `god-code-site`: no tests directory

### A.4 Environment template files

- All 3 repos: **0 `.env.example` / template files found**. Cleanest possible outcome — no risk of a template accidentally containing real values.

**Track A verdict:** PASS

## Track B — Deployment secrets and log hygiene

### B.1 god-code-api secret inventory

Deployed secrets (per `wrangler secret list`, post-correction):

| Secret | Referenced in source | Status |
|--------|---------------------|--------|
| `ADMIN_SECRET` | Yes (admin auth) | OK |
| `OPENAI_API_KEY` | Yes (provider pool) | OK |
| `SCORING_API_KEY` | No direct reference | **Reserved** — planned scoring feature (see Audit Correction) |

Source-referenced but not currently deployed (functional gap, not security issue):

- `ANTHROPIC_API_KEY` — declared in provider pool, not deployed
- `GEMINI_API_KEY` — declared in provider pool, not deployed
- `XAI_API_KEY` — declared in provider pool, not deployed

Impact: platform-mode callers selecting Claude/Gemini/xAI will receive upstream 401/403 until these are deployed. **Not a security issue** (missing keys = less to leak). Deploy before launch only if the landing page promises those providers in platform mode.

### B.2 Workers log hygiene

- **`console.*` calls in `src/`:** **0**
- **`redactSecrets()` utility wired into error paths:** Yes, 4 call sites (lines 305, 338, 358, 369 of `src/index.ts`)
- **Live `wrangler tail` review:** Not performed. Justification: source audit already confirms zero application logs possible; tail would only capture Cloudflare platform logs outside our control.

### B.3 god-code-site Pages env vars

- **`import.meta.env.*` references in `src/`:** 0
- **`process.env.*` references in `src/`:** 0
- **Secrets embedded in built `dist/`:** 0
- **Source file count in `src/`:** 1 (`src/pages/index.astro`)

Pages dashboard env vars were not inspected via CLI (not possible for CF Pages via wrangler). Not a blocker because source has zero env-var ingestion points.

**Track B verdict:** PASS

## Track C — User data handling

### C.1 D1 schema — content storage check

- **Tables defined in schema/:** 5 (`route_decisions`, `quality_alerts`, `quality_scores`, `api_keys`, `usage_log`)
- **Tables with actual `INSERT INTO` statements in `src/`:** 2 (`api_keys`, `usage_log`)
- **Tables that store user content:** **0**

`api_keys` stores key hashes (not plaintext). `usage_log` stores token counts and metadata (not content). The other three tables are orphan — defined in schema but not written to by current code (informational finding, not security).

### C.2 CLI session upload audit

- **Network calls in `godot_agent/runtime/session.py`:** 0
- **`chmod 0o600` on session files:** Yes, already present (pre-existing hardening in v0.9)
- **What `godot_agent/llm/client.py` sends upstream:** Current-turn messages only. Never reads or uploads the saved session file.

### C.3 Waitlist PII minimization

- **Before:** KV entries stored `{email, joined_at, source: referer}`. `referer` could contain tracking parameters and campaign IDs.
- **After:** KV entries store `{email, joined_at}` only.
- **Implementation:** `src/index.ts` waitlist handler edited to remove `referer` field (commit `4cfcb21`). 152/152 tests pass. Deployed to production.
- **Historical data cleanup:** No-op. KV was empty at audit time (pre-launch, no real signups yet).
- **Retention policy:** Until public launch concludes, then purged. Purge procedure documented in `god-code-api/docs/DEPLOYMENT.md`.

### C.4 Data flow table

Produced in `.audit/data-flow-table.md` and embedded into `god-code/PRIVACY.md`. Covers every data point from CLI to backend to provider, including what is stored where and for how long.

**Track C verdict:** PASS

## Audit Correction — Finding B1 methodology flaw

**What happened**

During Phase 3.1, `SCORING_API_KEY` was flagged as an "orphan secret" and a recommendation to delete was made to the user. The recommendation was based on a grep that found zero references to the secret name across `src/`, `tests/`, `wrangler.toml`, and `docs/`. The user approved deletion. After deletion, the user noted that `SCORING_API_KEY` was in fact **reserved for a planned scoring feature** that is not yet wired up in the main branch. The user immediately re-set the secret via `wrangler secret put`. No production code path depended on it during the ~2-minute window of absence, so there was no outage.

**Root cause**

The audit equated "zero references in current source" with "orphan, safe to delete". These are not the same. A secret with no source references can also mean:

- A feature that is planned but not yet implemented
- A feature that is implemented in a branch or PR but not yet merged
- A dependency injection pattern where the secret is passed via a different identifier
- A debugging secret held in reserve for emergency access

**Correction applied**

- `SCORING_API_KEY` restored by the user
- `god-code-api/docs/DEPLOYMENT.md` updated to mark the secret as "Reserved for the scoring feature (planned). Do not delete." (commit `f39c65c`)
- `.audit/track-b-secrets.md` updated with the full incident record and methodology correction

**Methodology improvement for future audits**

Before recommending deletion of any secret, the auditor must answer all three of the following with "no":

1. Is the secret referenced in the current source tree?
2. Is the secret referenced in any open branch, PR, or design document describing a planned feature?
3. Does the feature owner confirm that the secret is not reserved for planned work?

Only if all three answers are "no" should a secret be flagged for deletion. The default posture should be **conservative retention** — it is cheaper to keep an unused secret than to accidentally remove a reserved one.

## Remediation actions applied

| Repo | Commit | What |
|------|--------|------|
| god-code | `f34b716` | Added hatch wheel exclude list to `pyproject.toml` |
| god-code-api | `4cfcb21` | Removed `referer` field from waitlist handler |
| god-code-api | (user) | `wrangler deploy` for the waitlist handler change |
| god-code-api | `f39c65c` | Corrected `SCORING_API_KEY` classification in `DEPLOYMENT.md` |

No git history was rewritten (per design policy: revoke only).

## Documentation published

| Repo | Artifact | Commit |
|------|----------|--------|
| god-code | `SECURITY.md` | `19a7335` |
| god-code | `PRIVACY.md` | `fd2baab` |
| god-code-api | `SECURITY.md` | `36a7f03` |
| god-code-api | `docs/DEPLOYMENT.md` | `c48ddc1` (+ `f39c65c` correction) |
| god-code-site | `SECURITY.md` | `5dd48b2` |
| god-code-site | `PRIVACY.md` | `a69a01c` |
| god-code-site | `docs/DEPLOYMENT.md` | `364e9ed` |

## Local regression prevention installed

| Repo | `.gitleaks.toml` | `scripts/install-hooks.sh` | Commit |
|------|------------------|---------------------------|--------|
| god-code | Yes | Yes | `5589622` |
| god-code-api | Yes | Yes | `b094e81` |
| god-code-site | Yes | Yes | `1824ba8` |

Each repo's pre-commit hook scans staged changes with `gitleaks protect --staged --config .gitleaks.toml`. Verified live on the initial commit that installed it — zero findings. Any future contributor running `./scripts/install-hooks.sh` after cloning gets the same protection.

## Non-goals (deferred to post-launch hardening sprint)

- **CLI Keychain storage** — `~/.config/god-code/config.json` remains plain JSON with `chmod 0o600`. Adequate for Level A+B threat model but not Level C (local malware).
- **OAuth device flow** — replace manual copy-paste key entry with a device-flow authentication between CLI and godcode.dev.
- **Website self-serve key issuance** — landing page currently only has waitlist, no signup/dashboard for creating `gc_live_*` keys.
- **CI `gitleaks` integration** — add GitHub Actions workflow to all 3 repos for regression prevention beyond local pre-commit hooks.
- **Dependency vulnerability scanning** — `pip-audit` for god-code, `npm audit` for god-code-api and god-code-site.
- **Rate limiting** — `/v1/admin/keys` and other public endpoints currently have no explicit rate limiting beyond Cloudflare's platform defaults.
- **SCORING_API_KEY full wire-up** — the scoring feature that reserves this secret still needs to be implemented end-to-end.
- **Missing platform pool keys** — deploy `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY` if the landing page advertises Claude/Gemini/xAI in platform mode.

## Success criteria (from design doc)

| Criterion | Met? |
|-----------|------|
| Gitleaks full-history scan zero actionable findings | ✅ |
| PyPI wheel audited, no sensitive files | ✅ |
| `pyproject.toml` has explicit exclude list, local build clean | ✅ |
| `wrangler secret list` inspected | ✅ |
| 3 × SECURITY.md published | ✅ |
| 2 × PRIVACY.md published with data-flow table | ✅ |
| 2 × DEPLOYMENT.md published | ✅ |
| Waitlist PII decision made and applied | ✅ |
| Local `.gitleaks.toml` + pre-commit hook in all 3 repos | ✅ |

All 9 success criteria met.

## Final verdict

**Pre-launch security audit complete. Launch-ready from a security and privacy standpoint.**

Remaining work is product / marketing / release logistics, not security. The audit's posture is **conservative**: zero active risks were found, but the audit explicitly notes what is out of scope so the next security review knows where to dig deeper.

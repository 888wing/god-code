# God Code Pre-launch Security Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete a pre-launch security audit of 3 repos (god-code, god-code-api, god-code-site) + published artifacts, remediate findings, and publish baseline security/privacy documentation before public launch.

**Architecture:** 8-phase sequential flow. Phase 1 installs tooling. Phases 2-4 run audits on each track (A: repo+wheel, B: deployment, C: data handling). Phase 5 remediates any findings from audits. Phase 6 writes public docs. Phase 7 installs local regression prevention. Phase 8 writes the internal audit report and commits. Each phase commits independently so progress survives interruptions.

**Tech Stack:** `gitleaks` for secret scanning, `wrangler` CLI for Cloudflare inspection, `pip download` + `unzip` for PyPI artifact inspection, plain Markdown for all docs, standard `git` + shell tooling.

**Design doc:** `docs/plans/2026-04-07-god-code-prelaunch-security-audit-design.md` (committed in `95aef4f`)

**Decisions from design phase (authoritative):**
- Waitlist retention: until launch ends (then purge)
- Security contact email: `info@do-va.com`
- History rewrite: **revoke only**, no force-push
- Post-fix re-audit: not required

**Repo paths:**
- `~/Projects/god-code` (Python CLI, the main repo — this plan lives here)
- `~/Projects/god-code-api` (TypeScript, Cloudflare Workers)
- `~/Projects/god-code-site` (Astro, Cloudflare Pages)

---

## Phase 1: Tooling setup

### Task 1.1: Install gitleaks

**Step 1: Check if gitleaks is already installed**

Run: `which gitleaks && gitleaks version`
Expected: either a path + version, or "not found"

**Step 2: Install if missing**

If missing, run: `brew install gitleaks`
Expected: install completes, `gitleaks version` returns `v8.x.x` or later.

**Step 3: No commit** — tooling install is not a repo change.

---

## Phase 2: Track A — repo + published artifact secret audit

### Task 2.1: Scan god-code full git history with gitleaks

**Files:**
- Create: `~/Projects/god-code/.audit/gitleaks-god-code.txt` (audit artifact, gitignored)

**Step 1: Run gitleaks on full history**

```bash
cd ~/Projects/god-code
mkdir -p .audit
gitleaks detect --source . --log-opts="--all" --report-path=.audit/gitleaks-god-code.json --verbose 2>&1 | tee .audit/gitleaks-god-code.txt
```

Expected: exit 0 (no leaks) or exit 1 (leaks found). Either way, the JSON report is written.

**Step 2: Record summary**

```bash
echo "=== gitleaks summary for god-code ===" >> .audit/gitleaks-god-code.txt
jq '. | length' .audit/gitleaks-god-code.json 2>/dev/null || echo "no findings file"
```

**Step 3: Add `.audit/` to .gitignore**

Modify `~/Projects/god-code/.gitignore` — add a new line `.audit/` if not present. Verify with `grep '^\.audit/$' .gitignore`.

**Step 4: No commit yet** — audit artifacts stay local; we commit documentation changes later.

---

### Task 2.2: Scan god-code-api full git history with gitleaks

**Files:**
- Create: `~/Projects/god-code-api/.audit/gitleaks-god-code-api.json` (gitignored)

**Step 1: Run gitleaks**

```bash
cd ~/Projects/god-code-api
mkdir -p .audit
gitleaks detect --source . --log-opts="--all" --report-path=.audit/gitleaks-god-code-api.json --verbose 2>&1 | tee .audit/gitleaks-god-code-api.txt
```

**Step 2: Add `.audit/` to `.gitignore`** (same as Task 2.1 Step 3 but for this repo).

**Step 3: No commit yet.**

---

### Task 2.3: Scan god-code-site full git history with gitleaks

**Files:**
- Create: `~/Projects/god-code-site/.audit/gitleaks-god-code-site.json` (gitignored)

**Step 1: Run gitleaks**

```bash
cd ~/Projects/god-code-site
mkdir -p .audit
gitleaks detect --source . --log-opts="--all" --report-path=.audit/gitleaks-god-code-site.json --verbose 2>&1 | tee .audit/gitleaks-god-code-site.txt
```

**Step 2: Add `.audit/` to `.gitignore`**.

**Step 3: No commit yet.**

---

### Task 2.4: Triage gitleaks findings

**Step 1: Read each report**

```bash
for f in ~/Projects/god-code/.audit/gitleaks-*.json \
         ~/Projects/god-code-api/.audit/gitleaks-*.json \
         ~/Projects/god-code-site/.audit/gitleaks-*.json; do
  echo "=== $f ==="
  jq 'length' "$f" 2>/dev/null
done
```

**Step 2: Classify each finding**

For each finding, classify:
- **False positive** (test fixture placeholder, example in docs): annotate the finding file path + line, no action.
- **Real active secret**: must be **revoked at provider immediately** before continuing. Document the revocation in Phase 5.
- **Real but already revoked/inactive**: document in Phase 5's audit report, no further action.

**Step 3: If any real active secret found, STOP and revoke**

- Identify the provider (OpenAI / Anthropic / Cloudflare / etc.)
- Go to the provider dashboard and revoke the key
- Wait for confirmation before continuing
- Record in a scratch file `~/Projects/god-code/.audit/revocations.txt`

**Step 4: No commit yet** — all actions are either local or at third-party providers.

---

### Task 2.5: Download and inspect the live PyPI wheel

**Files:**
- Create: `~/Projects/god-code/.audit/pypi-wheel-inspection.txt`

**Step 1: Download the latest published wheel from PyPI**

```bash
cd ~/Projects/god-code/.audit
rm -rf pypi-check && mkdir pypi-check && cd pypi-check
pip download god-code --no-deps -d .
ls *.whl
```

Expected: one `god_code-0.8.x-py3-none-any.whl` file (the version actually published).

**Step 2: Extract and list contents**

```bash
mkdir extracted
unzip -q *.whl -d extracted
find extracted -type f | sort > ../pypi-wheel-contents.txt
wc -l ../pypi-wheel-contents.txt
```

**Step 3: Scan for suspicious filenames**

```bash
grep -iE '(config\.json|auth\.json|\.env|\.key|\.pem|secret|credentials|\.pypirc|agent_sessions|\.codetape)' ../pypi-wheel-contents.txt | tee ../pypi-wheel-suspicious.txt
```

Expected: empty output. If anything is listed, inspect the file and decide if it needs to be excluded.

**Step 4: Write inspection summary**

Append to `~/Projects/god-code/.audit/pypi-wheel-inspection.txt`:
```
Wheel version: [version from step 1]
File count: [from step 2]
Suspicious matches: [paste grep output or "none"]
Decision: [pass | needs-exclude-list-update | needs-republish]
```

**Step 5: No commit yet.**

---

### Task 2.6: Add hatch exclude list to pyproject.toml

**Files:**
- Modify: `~/Projects/god-code/pyproject.toml` (currently has only `[tool.hatch.build.targets.wheel] packages = ["godot_agent"]`)

**Step 1: Read current hatch section**

Read `pyproject.toml` and locate the `[tool.hatch.build.targets.wheel]` block.

**Step 2: Add explicit exclude**

Append or modify so the block becomes:

```toml
[tool.hatch.build.targets.wheel]
packages = ["godot_agent"]
exclude = [
  "**/__pycache__",
  "**/*.pyc",
  "**/.DS_Store",
  "**/config.json",
  "**/auth.json",
  "**/.env",
  "**/.env.*",
  "**/*.key",
  "**/*.pem",
  "**/.agent_sessions",
  "**/.codetape",
  "**/tests",
  "**/test_*",
  "**/.audit",
]
```

**Step 3: Test the build locally**

```bash
cd ~/Projects/god-code
python -m build --wheel --outdir .audit/local-build 2>&1 | tail -10
```

Expected: wheel builds successfully into `.audit/local-build/`. If `python -m build` is not installed, use `uv build --wheel` or `pipx run build`.

**Step 4: Verify the local wheel matches expectations**

```bash
cd .audit/local-build
unzip -q -l *.whl | tee ../local-build-contents.txt
grep -iE '(config\.json|auth\.json|\.env|\.key|\.pem|\.agent_sessions|\.codetape)' ../local-build-contents.txt
```

Expected: grep returns nothing.

**Step 5: Commit**

```bash
cd ~/Projects/god-code
git add pyproject.toml .gitignore
git commit -m "$(cat <<'EOF'
build: add hatch wheel exclude list for pre-launch audit

Explicit exclude list prevents accidental packaging of local
config, auth, env, key, and session files into future wheels.
Verified with local build; no sensitive files in output.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.7: Grep for hardcoded credentials in test fixtures (3 repos)

**Step 1: Run scoped grep on all 3 repos**

```bash
for repo in ~/Projects/god-code ~/Projects/god-code-api ~/Projects/god-code-site; do
  echo "=== $repo ==="
  cd "$repo"
  grep -rEn '(sk-[a-zA-Z0-9]{20,}|gc_live_[a-zA-Z0-9]{20,}|Bearer [a-zA-Z0-9]{20,})' \
    --include='*.json' --include='*.yaml' --include='*.yml' --include='*.ts' --include='*.py' \
    tests/ 2>/dev/null || echo "(no matches)"
done
```

Expected: `(no matches)` for each repo, OR only obvious placeholder strings like `sk-test-xxx`.

**Step 2: Record findings**

Append results to `~/Projects/god-code/.audit/track-a-fixtures.txt`.

**Step 3: If real secret found in fixtures**

Revoke at provider, remove from file, replace with placeholder, and plan commit for Phase 5.

**Step 4: No commit yet** — this is an audit action, any fix goes in Phase 5.

---

### Task 2.8: Check `.env.example` and similar template files

**Step 1: Find template files**

```bash
for repo in ~/Projects/god-code ~/Projects/god-code-api ~/Projects/god-code-site; do
  echo "=== $repo ==="
  cd "$repo"
  find . -maxdepth 3 -type f \( -name '.env.example' -o -name '.env.sample' -o -name '.env.template' -o -name 'env.example' \) -not -path './node_modules/*' -not -path './.venv/*'
done
```

**Step 2: Read each one (if any) and verify safety**

For each template file found, read it and confirm it contains only placeholder strings like `YOUR_KEY_HERE`, not real values.

**Step 3: Record in audit log**

Append to `~/Projects/god-code/.audit/track-a-env-templates.txt`.

**Step 4: No commit yet.**

---

## Phase 3: Track B — deployment secrets audit

### Task 3.1: Verify god-code-api Cloudflare Workers secrets

**Step 1: Log in to wrangler if needed**

```bash
cd ~/Projects/god-code-api
npx wrangler whoami
```

Expected: shows the logged-in account. If not, run `npx wrangler login`.

**Step 2: List secrets**

```bash
npx wrangler secret list | tee ~/Projects/god-code/.audit/wrangler-secrets-api.txt
```

Expected output includes at minimum: `ADMIN_SECRET`. Likely also: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY` (whichever providers are enabled).

**Step 3: Cross-check source references**

```bash
cd ~/Projects/god-code-api
grep -rEn 'env\.[A-Z_]+' src/ | grep -oE 'env\.[A-Z_]+' | sort -u > ~/Projects/god-code/.audit/env-vars-referenced.txt
cat ~/Projects/god-code/.audit/env-vars-referenced.txt
```

Every entry should either be in the wrangler secret list (Step 2) or be a public `[vars]` entry in `wrangler.toml` (look at `wrangler.toml` — `SCORING_MODEL`, `LATEST_VERSION`, etc. are public).

**Step 4: Flag gaps**

If a secret env var is referenced in source but not set as a wrangler secret, record in `~/Projects/god-code/.audit/track-b-gaps.txt` and plan to fix in Phase 5.

**Step 5: No commit yet.**

---

### Task 3.2: Review Cloudflare Workers logs for header leakage

**Step 1: Tail live logs briefly**

```bash
cd ~/Projects/god-code-api
npx wrangler tail --format=pretty 2>&1 | tee ~/Projects/god-code/.audit/wrangler-tail.txt &
TAIL_PID=$!
sleep 30
kill $TAIL_PID 2>/dev/null
```

**Step 2: Grep for header leakage**

```bash
grep -iE '(authorization|bearer|api[_-]?key|x-admin-secret)' ~/Projects/god-code/.audit/wrangler-tail.txt || echo "no header leakage detected in 30s window"
```

Expected: no matches. If matches found, inspect the source location and plan a log-redaction fix in Phase 5.

**Step 3: Grep source for known leak patterns**

```bash
cd ~/Projects/god-code-api
grep -rEn 'console\.(log|error|warn).*request\.headers' src/ || echo "no direct header logging"
grep -rEn 'JSON\.stringify.*request' src/ || echo "no full-request serialization"
```

Any hit here is a concrete risk — flag for Phase 5 remediation.

**Step 4: Record findings**

Append to `~/Projects/god-code/.audit/track-b-log-review.txt`.

**Step 5: No commit yet.**

---

### Task 3.3: Verify god-code-site Pages build env vars

**Step 1: Check for build-time env references**

```bash
cd ~/Projects/god-code-site
grep -rEn 'import\.meta\.env\.[A-Z_]+|process\.env\.[A-Z_]+' src/ astro.config.* 2>/dev/null | tee ~/Projects/god-code/.audit/site-env-refs.txt
```

Expected: either empty, or only public env vars (prefixed with `PUBLIC_` in Astro convention).

**Step 2: Check Pages project settings manually**

Open the Cloudflare dashboard → Pages → god-code-site → Settings → Environment variables. Record the list of env vars and mark which are secrets. Paste into `~/Projects/god-code/.audit/site-pages-env.txt`.

**Step 3: Verify no build-time secret in committed files**

```bash
grep -rEn '(sk-|gc_live_|bearer )' src/ --include='*.astro' --include='*.ts' --include='*.js' 2>/dev/null || echo "(none)"
```

Expected: `(none)`.

**Step 4: No commit yet.**

---

### Task 3.4: Write DEPLOYMENT.md for god-code-api

**Files:**
- Create: `~/Projects/god-code-api/docs/DEPLOYMENT.md`

**Step 1: Ensure the docs directory exists**

```bash
mkdir -p ~/Projects/god-code-api/docs
```

**Step 2: Write the deployment runbook**

Create `~/Projects/god-code-api/docs/DEPLOYMENT.md` with this structure:

```markdown
# Deployment Runbook

## Overview

`god-code-api` is deployed to Cloudflare Workers. Bindings are declared in `wrangler.toml`. Secrets are managed via `wrangler secret put` (never committed).

## Secret inventory

| Secret | Purpose | How to set |
|---|---|---|
| `ADMIN_SECRET` | Gates `/v1/admin/keys` and `/v1/waitlist` GET endpoints | `npx wrangler secret put ADMIN_SECRET` |
| `OPENAI_API_KEY` | Upstream provider for GPT models | `npx wrangler secret put OPENAI_API_KEY` |
| `ANTHROPIC_API_KEY` | Upstream provider for Claude models | `npx wrangler secret put ANTHROPIC_API_KEY` |
| `GEMINI_API_KEY` | Upstream provider for Gemini models | `npx wrangler secret put GEMINI_API_KEY` |
| `XAI_API_KEY` | Upstream provider for xAI models | `npx wrangler secret put XAI_API_KEY` |
| `OPENROUTER_API_KEY` | Upstream provider for OpenRouter | `npx wrangler secret put OPENROUTER_API_KEY` |

(Update this table to match the actual Phase 3.1 Step 2 output.)

## Public bindings (in wrangler.toml, NOT secrets)

- `SCORING_MODEL`, `SCORING_SAMPLE_RATE`, `AB_TRAFFIC_PERCENTAGE`, `LATEST_VERSION`, `MIN_SUPPORTED_VERSION`, `UPDATE_MESSAGE` — public configuration.
- `DB` (D1 binding), `ROUTING_KV` (KV binding), `SESSION_DO` (Durable Object binding) — resource identifiers, not secrets.

## Deploy

```bash
npx wrangler deploy
```

## Rotate a secret

1. Generate new secret at provider.
2. `npx wrangler secret put SECRET_NAME` and paste the new value.
3. `npx wrangler deploy` to force a new version (secrets take effect on next deploy).
4. Verify with `npx wrangler tail` and a smoke-test request.
5. Revoke the old secret at provider.

## Emergency revocation

If a secret is suspected leaked:

1. Revoke at provider **immediately**.
2. `npx wrangler secret put SECRET_NAME` with a new value.
3. `npx wrangler deploy`.
4. Review `wrangler tail` for abuse patterns.
5. Post-mortem in `docs/SECURITY-HISTORY.md`.

## Contact

Security contact: `info@do-va.com`
```

**Step 3: Commit**

```bash
cd ~/Projects/god-code-api
git add docs/DEPLOYMENT.md
git commit -m "$(cat <<'EOF'
docs: add deployment runbook for pre-launch audit

Documents secret inventory, rotation, and emergency revocation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.5: Write DEPLOYMENT.md for god-code-site

**Files:**
- Create: `~/Projects/god-code-site/docs/DEPLOYMENT.md`

**Step 1: Ensure directory exists**

```bash
mkdir -p ~/Projects/god-code-site/docs
```

**Step 2: Write the runbook**

Create `~/Projects/god-code-site/docs/DEPLOYMENT.md` with this structure:

```markdown
# Deployment Runbook

## Overview

`god-code-site` is an Astro static site deployed to Cloudflare Pages at **godcode.dev**.

## Build

```bash
npx astro build
```

Output: `dist/`

## Deploy

```bash
npx wrangler pages deploy dist --project-name god-code-site
```

## Environment variables

Cloudflare Pages build env vars are managed in the CF dashboard:
**Pages → god-code-site → Settings → Environment variables**.

| Variable | Purpose | Secret? |
|---|---|---|
| (fill from Task 3.3 Step 2 output) | | |

**Rule:** Only `PUBLIC_*` prefixed variables may be referenced in client-side code. Anything else is a build-time secret and must not appear in `dist/` output.

## Rotate a secret

1. Update the value in CF dashboard → Settings → Environment variables.
2. Trigger a new build (redeploy).
3. Verify the old value does not appear in production traffic.

## Contact

Security contact: `info@do-va.com`
```

**Step 3: Commit**

```bash
cd ~/Projects/god-code-site
git add docs/DEPLOYMENT.md
git commit -m "$(cat <<'EOF'
docs: add deployment runbook for pre-launch audit

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4: Track C — user data handling audit

### Task 4.1: Verify `usage_log` D1 schema does not store content

**Files:**
- Read: `~/Projects/god-code-api/schema/` (look for `.sql` files)
- Read: `~/Projects/god-code-api/src/admin/handlers.ts` (search for INSERT INTO usage_log)

**Step 1: Find the schema**

```bash
cd ~/Projects/god-code-api
find schema -name '*.sql' -exec grep -l 'usage_log' {} \;
```

**Step 2: Read the table definition**

Read the schema file. Verify the `usage_log` columns contain only: `id`, `api_key_id`, `timestamp`, `agent_role`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_estimate`, `quality_score`. There should be **no** column storing prompt text or completion text.

**Step 3: Record finding**

Append to `~/Projects/god-code/.audit/track-c-usage-log.txt`:
```
usage_log schema columns: [list]
Stores prompt content: [yes/no]
Stores completion content: [yes/no]
Decision: [pass | needs-schema-change]
```

**Step 4: If content is stored**

Flag in Phase 5 for remediation (schema migration to drop the columns).

**Step 5: No commit yet.**

---

### Task 4.2: Grep god-code CLI for session upload paths

**Files:**
- Read: `~/Projects/god-code/godot_agent/runtime/session.py`
- Read: `~/Projects/god-code/godot_agent/llm/client.py`

**Step 1: Grep for upload-shaped calls in the session module**

```bash
cd ~/Projects/god-code
grep -rEn 'backend_url|upload|post.*session' godot_agent/runtime/session.py
```

Expected: no upload calls. `session.py` should only write to local disk.

**Step 2: Confirm session files go to local disk only**

```bash
grep -rEn 'session_dir|\.agent_sessions|write_text|json\.dump' godot_agent/runtime/session.py
```

Confirm writes target `config.session_dir` (local path).

**Step 3: Check llm/client.py for what it sends upstream**

```bash
grep -rEn 'messages|json=|httpx' godot_agent/llm/client.py | head -20
```

Confirm only the **current request messages** are sent upstream (per LLM call), not the saved session file.

**Step 4: Record finding**

Append to `~/Projects/god-code/.audit/track-c-session.txt`:
```
session.py uploads: [none | list]
llm/client.py sends: [per-request messages only | includes session file]
Decision: [pass | needs-fix]
```

**Step 5: No commit yet.**

---

### Task 4.3: Review waitlist KV handler for PII

**Files:**
- Read: `~/Projects/god-code-api/src/index.ts:587-617` (waitlist handlers)

**Step 1: Confirm current behavior**

Read `src/index.ts` lines 587-617. Current code stores `{email, joined_at, source: referer}` to KV. The `referer` may include tracking params.

**Step 2: Decision**

Per the design decision: **remove the `referer` field**. It provides marginal value and is a PII/tracking-surface risk.

**Step 3: Modify the handler**

In `src/index.ts` around line 596, change:

```typescript
await env.ROUTING_KV.put(`waitlist:${email}`, JSON.stringify({
  email,
  joined_at: new Date().toISOString(),
  source: request.headers.get("referer") || "direct",
}));
```

to:

```typescript
await env.ROUTING_KV.put(`waitlist:${email}`, JSON.stringify({
  email,
  joined_at: new Date().toISOString(),
}));
```

**Step 4: Update the admin list handler if it echoes source**

Check `src/index.ts:608-617`. If the list response includes the `source` field, no change needed (it just reads KV). The removal in Step 3 is sufficient.

**Step 5: Run tests**

```bash
cd ~/Projects/god-code-api
npx vitest run --reporter=dot 2>&1 | tail -20
```

Expected: all tests pass. If any test asserts on the `source` field, update the test to not expect it.

**Step 6: Commit**

```bash
git add src/index.ts
git commit -m "$(cat <<'EOF'
fix(waitlist): drop referer field to reduce PII surface

Pre-launch privacy audit: referer header can include tracking
params. Drop the field since it provides no operational value.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.4: Purge existing waitlist entries with referer field

**Step 1: List existing entries**

```bash
curl -s -H "X-Admin-Secret: $ADMIN_SECRET" \
  https://god-code-api.nano122090.workers.dev/v1/waitlist \
  | jq '.entries | length'
```

(Requires `ADMIN_SECRET` in env. If unknown, retrieve from 1Password / wrangler secret before continuing.)

**Step 2: Decide rewrite strategy**

Since KV supports put-by-key, the cleanest fix is to re-put each entry with the new shape. Write a small one-shot script:

```bash
cat > ~/Projects/god-code/.audit/waitlist-rewrite.sh <<'EOF'
#!/bin/bash
set -euo pipefail
API="https://god-code-api.nano122090.workers.dev/v1/waitlist"
ENTRIES=$(curl -s -H "X-Admin-Secret: $ADMIN_SECRET" "$API" | jq -c '.entries[]')
echo "$ENTRIES" | while IFS= read -r entry; do
  email=$(echo "$entry" | jq -r '.email')
  joined=$(echo "$entry" | jq -r '.joined_at')
  # Re-put by POSTing same email; handler now writes new shape
  curl -s -X POST "$API" -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\"}" > /dev/null
  echo "rewrote $email"
done
EOF
chmod +x ~/Projects/god-code/.audit/waitlist-rewrite.sh
```

**Step 3: Deploy the handler change first**

```bash
cd ~/Projects/god-code-api
npx wrangler deploy
```

Expected: deploy completes, new version is live.

**Step 4: Run the rewrite script**

```bash
export ADMIN_SECRET=<paste from wrangler secret>
~/Projects/god-code/.audit/waitlist-rewrite.sh
```

Note: re-POSTing the same email will **update** `joined_at` to the current time. This is acceptable for PII cleanup — the original join time was stored alongside a PII field we're trying to purge. If original timestamps matter, use `wrangler kv:key put` with the old shape instead.

**Step 5: Verify**

```bash
curl -s -H "X-Admin-Secret: $ADMIN_SECRET" \
  "https://god-code-api.nano122090.workers.dev/v1/waitlist" \
  | jq '.entries[0]'
```

Expected: the entry has only `email` and `joined_at`, no `source` field.

**Step 6: No commit** — all actions are against production infrastructure, not repo.

---

### Task 4.5: Document waitlist retention policy + purge mechanism

**Files:**
- Modify: `~/Projects/god-code-api/docs/DEPLOYMENT.md`

**Step 1: Append retention section**

Open `~/Projects/god-code-api/docs/DEPLOYMENT.md` (created in Task 3.4). Append a new section:

```markdown
## Waitlist data retention

**Policy:** Waitlist emails are retained **until public launch concludes**, then purged.

**Purge procedure:**

1. Back up the list (optional): `curl -H "X-Admin-Secret: $ADMIN_SECRET" https://god-code-api.nano122090.workers.dev/v1/waitlist > waitlist-backup-$(date +%Y%m%d).json`
2. For each key under the `waitlist:` prefix, delete via wrangler:
   ```bash
   npx wrangler kv:key list --binding=ROUTING_KV --prefix=waitlist: | \
     jq -r '.[].name' | \
     xargs -I{} npx wrangler kv:key delete --binding=ROUTING_KV "{}"
   ```
3. Verify: `curl -H "X-Admin-Secret: $ADMIN_SECRET" .../v1/waitlist | jq '.count'` → `0`.
4. Record the purge date in `docs/SECURITY-HISTORY.md`.
```

**Step 2: Commit**

```bash
cd ~/Projects/god-code-api
git add docs/DEPLOYMENT.md
git commit -m "$(cat <<'EOF'
docs: document waitlist retention policy

Retention: until launch ends. Purge procedure uses wrangler kv
bulk delete. Part of pre-launch privacy audit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.6: Build the data flow table for PRIVACY.md

**Files:**
- Create: `~/Projects/god-code/.audit/data-flow-table.md` (draft, used in Task 6.x)

**Step 1: Read relevant sources**

- `~/Projects/god-code/godot_agent/llm/client.py` — what gets sent to providers
- `~/Projects/god-code/godot_agent/runtime/session.py` — what gets saved locally
- `~/Projects/god-code-api/src/index.ts` — what the API persists
- `~/Projects/god-code-api/schema/*.sql` — what the DB stores

**Step 2: Draft the table**

Write `~/Projects/god-code/.audit/data-flow-table.md`:

```markdown
# Data Flow

| Stage | Data | Destination | Stored? | Retention |
|---|---|---|---|---|
| CLI reads Godot project | Source files (.gd, .tscn, screenshots) | LLM provider (via BYOK or god-code-api) | Not stored by god-code | Provider-dependent |
| CLI saves session | Conversation history, tool calls | Local: `.agent_sessions/*.json` | On user's machine only | User-controlled |
| CLI calls LLM | Current-turn messages | Provider API | Not stored server-side | Provider-dependent |
| API logs usage | `{agent_role, provider, model, prompt_tokens, completion_tokens, cost_estimate, quality_score}` | D1 `usage_log` table | Yes | Indefinite (aggregate stats only) |
| API serves waitlist | `{email, joined_at}` | KV `waitlist:{email}` | Yes | Until launch ends |

**Explicitly NOT stored by god-code-api:**
- Prompt content
- Completion content
- User's Godot project files
- User's session history
- IP addresses (beyond Cloudflare's platform logs)
```

**Step 3: No commit yet** — this draft gets embedded into PRIVACY.md in Phase 6.

---

## Phase 5: Remediation of Phase 2-4 findings

### Task 5.1: Consolidate findings

**Files:**
- Create: `~/Projects/god-code/.audit/findings-summary.md`

**Step 1: Collect all findings**

For each audit artifact under `.audit/` (gitleaks-*.json, track-*.txt, pypi-*.txt), list the actionable findings (not the "pass" ones).

**Step 2: Write the summary**

Write `~/Projects/god-code/.audit/findings-summary.md`:

```markdown
# Pre-launch Audit Findings

## Track A (repo + wheel)
- [finding 1 or "no actionable findings"]

## Track B (deployment)
- [finding 1 or "no actionable findings"]

## Track C (data handling)
- [finding 1 or "no actionable findings"]

## Remediation completed
- [Task 4.3: dropped referer from waitlist — committed in god-code-api]
- [any other fixes applied inline in Phases 2-4]

## Remediation required (not yet applied)
- [anything that requires a commit in this phase]
```

**Step 3: No commit** — this is an internal audit artifact.

---

### Task 5.2: Apply any outstanding remediation

For each entry under "Remediation required", execute the fix now.

**Patterns:**

- **Revoked historical secret**: add a line to `docs/SECURITY-HISTORY.md` in the affected repo:
  ```markdown
  ## YYYY-MM-DD: Historical secret revoked

  A [provider] key was found in git history via gitleaks pre-launch
  scan. The key has been revoked at the provider and is no longer
  active. Git history was **not** rewritten per project policy.
  ```
  Commit with message: `docs: record revoked historical secret`

- **Wrangler secret gap (Task 3.1)**: `npx wrangler secret put SECRET_NAME`, paste value, then `npx wrangler deploy`. No repo commit.

- **Log leakage (Task 3.2)**: write a log-redaction helper and swap out the offending log line. Commit to `god-code-api`.

- **Any other fix**: smallest possible diff, one commit per logical fix.

**Step 1: For each fix, apply and commit independently**

Use commit message pattern: `fix(security): <what was fixed>` with a `Why:` line in the body.

**Step 2: Update findings-summary.md**

Move each remediation from "required" to "completed" as you finish it.

---

## Phase 6: Public documentation

### Task 6.1: Write SECURITY.md for god-code

**Files:**
- Create: `~/Projects/god-code/SECURITY.md`

**Step 1: Write the file**

```markdown
# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.8.x | Yes |
| < 0.8 | No |

## Reporting a vulnerability

Email: **info@do-va.com**

Please include:
- Affected version
- Reproduction steps
- Impact assessment

We aim to acknowledge reports within **5 business days**.

## Disclosure policy

Please hold public disclosure until a fix is released. We will credit
reporters (unless they request otherwise) in the release notes.

## Scope

**In scope:**
- `god-code` Python package (this repo)
- `god-code-api` backend (separate repo)
- `god-code-site` landing page (separate repo)

**Out of scope:**
- Vulnerabilities in user-supplied BYOK LLM providers (OpenAI, Anthropic, etc.)
- Vulnerabilities in user's own Godot projects
- Social engineering targeting god-code users or maintainers
- Denial-of-service against public endpoints without demonstrated impact

## Contact

`info@do-va.com`
```

**Step 2: Commit**

```bash
cd ~/Projects/god-code
git add SECURITY.md
git commit -m "$(cat <<'EOF'
docs: add SECURITY.md for public launch

Documents supported versions, vulnerability reporting process,
and scope. Contact: info@do-va.com.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6.2: Write SECURITY.md for god-code-api

**Files:**
- Create: `~/Projects/god-code-api/SECURITY.md`

**Step 1: Write the file** (same structure as Task 6.1, but "Supported versions" reads "Latest deployed worker only" and "Scope" emphasizes backend).

**Step 2: Commit**

```bash
cd ~/Projects/god-code-api
git add SECURITY.md
git commit -m "docs: add SECURITY.md for public launch

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6.3: Write SECURITY.md for god-code-site

**Files:**
- Create: `~/Projects/god-code-site/SECURITY.md`

**Step 1: Write the file** (same structure, scope emphasizes landing page only).

**Step 2: Commit**

```bash
cd ~/Projects/god-code-site
git add SECURITY.md
git commit -m "docs: add SECURITY.md for public launch

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6.4: Write PRIVACY.md for god-code

**Files:**
- Create: `~/Projects/god-code/PRIVACY.md`
- Read: `~/Projects/god-code/.audit/data-flow-table.md` (drafted in Task 4.6)

**Step 1: Compose the file**

```markdown
# Privacy

`god-code` is designed with **local-first** and **data-minimization** principles. This document explains what data is handled, where it goes, and how long it is kept.

## What god-code handles

When you use the `god-code` CLI:

- **Your Godot project files** are read locally by the agent and sent to the LLM provider you configured (BYOK) or via the god-code platform backend (if you use a platform key).
- **Screenshots** captured by vision tools follow the same path.
- **Conversation history** is saved to `.agent_sessions/` on your local machine. It is **never uploaded** to god-code's servers.
- **API keys** you paste into the setup wizard are saved to `~/.config/god-code/config.json` on your local machine.

## Data flow

[Embed the table from `.audit/data-flow-table.md`]

## What the god-code backend stores

`god-code-api` persists **only usage statistics**, never content:

- Per-request: `agent_role`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_estimate`, `quality_score`
- Aggregated: quota remaining, last-used timestamp

**We do not store**: prompt content, completion content, your project files, your session history, or your IP address (beyond platform infrastructure logs that we do not query).

## Waitlist

If you joined the waitlist via godcode.dev, we store your email and join timestamp in Cloudflare KV. **Retention: until public launch concludes**, then purged. Email `info@do-va.com` for earlier deletion.

## Your rights

Under GDPR / CCPA (where applicable), you have the right to:

- **Access**: request a copy of data we hold about you
- **Delete**: request permanent removal
- **Portability**: request data in machine-readable form

To exercise any right, email `info@do-va.com`.

## Third-party providers

When you use BYOK, your data goes directly to the LLM provider you selected. Their privacy policy applies to that traffic. god-code-api does not proxy BYOK traffic unless you explicitly opt in via `backend_url`.

## Changes

This policy may change before or after public launch. Material changes will be announced via the project README.

## Contact

`info@do-va.com`
```

**Step 2: Replace the data-flow table placeholder with the actual table content from `.audit/data-flow-table.md`.**

**Step 3: Commit**

```bash
cd ~/Projects/god-code
git add PRIVACY.md
git commit -m "$(cat <<'EOF'
docs: add PRIVACY.md for public launch

Documents data flow, storage policy, waitlist retention, and
user rights under GDPR/CCPA.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6.5: Write PRIVACY.md for god-code-site

**Files:**
- Create: `~/Projects/god-code-site/PRIVACY.md`

**Step 1: Write a scoped version**

The site-specific PRIVACY.md should cover:
- Waitlist data handling (email + join timestamp, retention until launch)
- Cookies (if any — Astro static site likely has none; verify)
- Analytics (if any)
- Link to `god-code/PRIVACY.md` for CLI data handling

**Step 2: Commit**

```bash
cd ~/Projects/god-code-site
git add PRIVACY.md
git commit -m "docs: add PRIVACY.md for public launch

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7: Local regression prevention

### Task 7.1: Add .gitleaks.toml to god-code

**Files:**
- Create: `~/Projects/god-code/.gitleaks.toml`

**Step 1: Write a minimal config**

```toml
[extend]
useDefault = true

[[rules]]
id = "god-code-platform-key"
description = "God Code platform API key"
regex = '''gc_live_[a-zA-Z0-9]{32,}'''
tags = ["key", "god-code"]

[allowlist]
paths = [
  '''docs/.*\.md''',
  '''tests/.*fixtures.*''',
  '''\.audit/''',
]
```

**Step 2: Test the config**

```bash
cd ~/Projects/god-code
gitleaks detect --config .gitleaks.toml --no-git 2>&1 | tail -5
```

Expected: exit 0, no findings on working tree.

---

### Task 7.2: Add pre-commit hook to god-code

**Files:**
- Create: `~/Projects/god-code/.git/hooks/pre-commit` (not committed — it's per-clone)
- Create: `~/Projects/god-code/scripts/install-hooks.sh` (committed, installs the hook)

**Step 1: Write the hook installer script**

```bash
mkdir -p ~/Projects/god-code/scripts
cat > ~/Projects/god-code/scripts/install-hooks.sh <<'EOF'
#!/bin/bash
# Install git hooks for this repo
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK="$REPO_ROOT/.git/hooks/pre-commit"
cat > "$HOOK" <<'HOOK_EOF'
#!/bin/bash
# Pre-commit: run gitleaks on staged changes
set -e
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed — skipping secret scan"
  exit 0
fi
gitleaks protect --staged --config .gitleaks.toml --verbose
HOOK_EOF
chmod +x "$HOOK"
echo "Installed pre-commit hook at $HOOK"
EOF
chmod +x ~/Projects/god-code/scripts/install-hooks.sh
```

**Step 2: Run it**

```bash
~/Projects/god-code/scripts/install-hooks.sh
```

**Step 3: Test the hook**

```bash
cd ~/Projects/god-code
git commit --allow-empty -m "test: verify pre-commit hook runs"
```

Expected: gitleaks runs, exits 0 (no staged changes = no secrets), commit succeeds. Delete the test commit:

```bash
git reset HEAD~1
```

**Step 4: Commit the installer**

```bash
cd ~/Projects/god-code
git add .gitleaks.toml scripts/install-hooks.sh
git commit -m "$(cat <<'EOF'
chore: add gitleaks config + pre-commit hook installer

Local regression prevention for secret leakage. Run
scripts/install-hooks.sh after clone to activate.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7.3: Repeat .gitleaks.toml + hook for god-code-api

**Step 1: Copy config**

Copy `~/Projects/god-code/.gitleaks.toml` to `~/Projects/god-code-api/.gitleaks.toml` and adjust allowlist paths (remove python-specific ones, add `node_modules/`).

**Step 2: Copy install script**

Copy `scripts/install-hooks.sh` similarly.

**Step 3: Install and test**

```bash
cd ~/Projects/god-code-api
./scripts/install-hooks.sh
```

**Step 4: Commit**

```bash
git add .gitleaks.toml scripts/install-hooks.sh
git commit -m "chore: add gitleaks config + pre-commit hook installer

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7.4: Repeat for god-code-site

Same as Task 7.3 but in `~/Projects/god-code-site`. Adjust allowlist for Astro conventions.

---

## Phase 8: Audit report + final commit

### Task 8.1: Write the internal audit report

**Files:**
- Create: `~/Projects/god-code/docs/plans/2026-04-07-god-code-prelaunch-security-audit-report.md`

**Step 1: Compose the report**

```markdown
# Pre-launch Security Audit Report

**Date completed:** 2026-04-07
**Design doc:** `2026-04-07-god-code-prelaunch-security-audit-design.md`
**Plan doc:** `2026-04-07-god-code-prelaunch-security-audit.md`

## Summary

[Pass / Pass-with-remediation / Findings-outstanding]

## Track A — Repo + artifact secrets

### A.1 gitleaks scans
- god-code: [N findings, M actionable]
- god-code-api: [N findings, M actionable]
- god-code-site: [N findings, M actionable]

### A.2 PyPI wheel 0.8.x inspection
- Inspected version: [x]
- File count: [n]
- Suspicious files: [none / list]
- pyproject.toml exclude list updated: [yes]
- Local test build clean: [yes]

### A.3 Fixture + template file audit
- god-code: [pass / findings]
- god-code-api: [pass / findings]
- god-code-site: [pass / findings]

## Track B — Deployment secrets

### B.1 wrangler secret list
- Expected secrets present: [yes / gaps: list]

### B.2 Workers log review
- No header logging in source: [confirmed / issue: ...]
- 30s tail sample: [no leaks / issue: ...]

### B.3 Pages env vars
- No embedded secrets in dist: [confirmed]

## Track C — Data handling

### C.1 usage_log schema
- No content columns: [confirmed / issue: ...]

### C.2 Session upload paths
- Local-only: [confirmed]

### C.3 Waitlist referer field
- Dropped: [yes, deploy: <version>]
- Existing entries rewritten: [yes, count: N]

## Remediation actions applied
- [list commits by repo]

## Remediation deferred
- CLI local Keychain upgrade (post-launch)
- OAuth device flow (post-launch)
- Website self-serve key issuance (post-launch)
- CI gitleaks integration (post-launch)
- Dependency vulnerability scanning (post-launch)

## Documentation published
- god-code: SECURITY.md, PRIVACY.md
- god-code-api: SECURITY.md, docs/DEPLOYMENT.md
- god-code-site: SECURITY.md, PRIVACY.md, docs/DEPLOYMENT.md

## Local prevention installed
- 3 × .gitleaks.toml
- 3 × pre-commit hook installer

## Launch decision

[Ready / Not ready — blockers: ...]
```

**Step 2: Fill in the real numbers from the audit artifacts under `.audit/`**

**Step 3: Commit**

```bash
cd ~/Projects/god-code
git add docs/plans/2026-04-07-god-code-prelaunch-security-audit-report.md
git commit -m "$(cat <<'EOF'
docs: add pre-launch security audit report

Internal record of checks, findings, and remediation actions
taken across god-code, god-code-api, and god-code-site.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8.2: Final verification

**Step 1: Confirm all deliverables exist**

```bash
ls ~/Projects/god-code/SECURITY.md \
   ~/Projects/god-code/PRIVACY.md \
   ~/Projects/god-code/.gitleaks.toml \
   ~/Projects/god-code/scripts/install-hooks.sh \
   ~/Projects/god-code-api/SECURITY.md \
   ~/Projects/god-code-api/docs/DEPLOYMENT.md \
   ~/Projects/god-code-api/.gitleaks.toml \
   ~/Projects/god-code-api/scripts/install-hooks.sh \
   ~/Projects/god-code-site/SECURITY.md \
   ~/Projects/god-code-site/PRIVACY.md \
   ~/Projects/god-code-site/docs/DEPLOYMENT.md \
   ~/Projects/god-code-site/.gitleaks.toml \
   ~/Projects/god-code-site/scripts/install-hooks.sh \
   ~/Projects/god-code/docs/plans/2026-04-07-god-code-prelaunch-security-audit-report.md
```

Expected: every file exists.

**Step 2: Confirm success criteria from design doc**

Re-read `docs/plans/2026-04-07-god-code-prelaunch-security-audit-design.md` section 5, verify each checkbox against the report.

**Step 3: Final commit if needed**

If any success criterion is not met, apply the fix and commit. Otherwise, the audit is complete.

**Step 4: Announce done**

Print: `Pre-launch security audit complete. Ready for launch.`

---

## Summary

**8 phases, 22 tasks, ~4-6 hours of focused work.**

- Phase 1: tooling (1 task)
- Phase 2: Track A audits (8 tasks)
- Phase 3: Track B audits (5 tasks)
- Phase 4: Track C audits (6 tasks)
- Phase 5: remediation (2 tasks, variable based on findings)
- Phase 6: public docs (5 tasks)
- Phase 7: local prevention (4 tasks)
- Phase 8: audit report + final verification (2 tasks)

**Commit cadence:** one commit per task where a repo change occurs. Audit artifacts under `.audit/` are never committed.

**If this plan is executed without finding any real secrets:** expect ~15-18 commits across 3 repos and no emergency actions.

**If real secrets are found:** Phase 5 expands with revocation steps and incident documentation; history is **not** rewritten per design decision.

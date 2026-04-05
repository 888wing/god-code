# God Code API Backend: Orchestration Layer Design

**Date**: 2026-04-04
**Goal**: Build a dedicated API backend (god-code-api) that intelligently routes god-code's LLM calls across multiple providers, eliminates cognitive blind spots through cross-model review, and establishes a data-driven quality optimization loop.
**Architecture**: Cloudflare Workers + D1 + Durable Objects + KV
**Repo**: `888wing/god-code-api` (separate from god-code)
**License**: GPL-3.0 (code open-source, routing weights/quality data are operational)

---

## Strategic Context

### Two-Phase Rollout

1. **Phase 1 (Now)**: Internal version → open-source BYOK. Users bring their own API keys, self-deploy Workers, use default routing rules.
2. **Phase 2 (Post-validation)**: Official OAuth service at `api.god-code.dev`. Centralized routing with accumulated quality data. Premium tier: consensus mode (multi-model voting).

### Core Problems Solved

1. **Model selection blindness** — Different tasks suit different models (Claude plans well, GPT-5.4 has stable tool use, Gemini is fast and cheap). Currently users pick one provider and use it for everything.
2. **Cognitive blind spots** — Single-provider usage creates a monoculture of reasoning patterns. Cross-model review catches errors the original model is blind to.
3. **Cost waste** — Simple tasks (lint, file reads) use top-tier models. Late-round fix iterations don't need the most expensive model.
4. **Monetization path** — Proxy-based billing + premium consensus mode.

### Open Source Strategy

```
Open source (code):              Closed source (data + service):
├── Workers routing framework     ├── Quality score history
├── Provider adapters             ├── Optimized routing weights (from A/B)
├── D1 schema                     ├── Hosted service (api.god-code.dev)
├── Quality scoring pipeline      ├── OAuth user management
├── A/B testing framework         └── Consensus mode aggregation logic
└── Default routing rules
```

The moat is accumulated data, not code.

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    god-code CLI                      │
│                                                     │
│  Engine Loop                                        │
│  ┌──────────┐   ┌───────────┐   ┌────────────────┐ │
│  │ Planner  │   │  Worker   │   │   Reviewer     │ │
│  └────┬─────┘   └─────┬─────┘   └───────┬────────┘ │
│       └───────────────┼──────────────────┘          │
│                       ▼                              │
│              OrchestrationClient                     │
│          (replaces direct LLMClient path)             │
│            POST /v1/orchestrate                      │
│            + agent_role, skill, round, changeset_size│
└───────────────────────┬─────────────────────────────┘
                        │ HTTPS
                        ▼
┌─────────────────────────────────────────────────────┐
│              god-code-api (CF Workers)               │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Auth Guard  │→ │ Task Router  │→ │  Provider  │  │
│  │ (API key /  │  │ (3-layer     │  │  Dispatch  │  │
│  │  OAuth)     │  │  engine)     │  │            │  │
│  └─────────────┘  └──────┬───────┘  └─────┬──────┘  │
│                          │                │         │
│                          ▼                ▼         │
│                   ┌────────────┐   ┌───────────┐    │
│                   │ D1 (SQLite)│   │ Provider  │    │
│                   │ - route log│   │  APIs     │    │
│                   │ - quality  │   │ OpenAI    │    │
│                   │ - A/B      │   │ Anthropic │    │
│                   │ - usage    │   │ Gemini    │    │
│                   └────────────┘   │ xAI       │    │
│                                    └───────────┘    │
│  ┌──────────────────┐  ┌────────────────────────┐   │
│  │ Durable Objects  │  │ Quality Scorer         │   │
│  │ - Session state  │  │ (async pipeline)       │   │
│  │ - Route context  │  │ - Gemini Flash grading │   │
│  │ - Consensus (v2) │  │ - Write to D1          │   │
│  └──────────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Core Data Flow

```
1. god-code sends orchestrate request
   → messages, tools, metadata (role, skill, round, changeset_size)

2. Auth Guard validates
   → BYOK: passthrough user's provider API keys
   → OAuth (future): use platform-managed keys

3. Session DO provides route context
   → previous_models, quality_trend, available_providers, cost

4. Task Router decides
   → Layer 1 (constraints) → Layer 2 (policy) → Layer 3 (intelligence)
   → Output: provider + model + reason + fallback_chain

5. Provider Dispatch
   → Format conversion (OpenAI ↔ Anthropic etc.)
   → Call provider API, stream response back

6. Async Quality Scorer (waitUntil)
   → Compress context → Gemini Flash scores 5 dimensions → D1
   → Route weights auto-adjust
```

### BYOK Key Management

User keys are passed via encrypted header per-request. Workers never store them — keys are used only for the current provider call and discarded.

```yaml
god-code config:
  backend_url: "https://api.god-code.dev"
  backend_provider_keys:
    openai: "sk-xxx"
    anthropic: "sk-ant-xxx"
    gemini: "AIza-xxx"
```

---

## Task Router: 3-Layer Decision Engine

### Input: RouteContext

```typescript
interface RouteContext {
  // From god-code agent system
  agent_role: "planner" | "worker" | "reviewer" | "playtest_analyst"
  skill: string | null
  mode: "apply" | "plan" | "review" | "fix" | "explain"
  round_number: number
  changeset_size: number
  estimated_tokens: number

  // From Session DO
  session_id: string
  previous_models: { role: string; provider: string; model: string }[]
  quality_trend: number[]

  // From user config
  provider_keys: string[]
  cost_preference: "economy" | "balanced" | "quality"
}
```

### Output: RouteDecision

```typescript
interface RouteDecision {
  provider: string
  model: string
  reason: string
  experiment_id: string | null
  fallback_chain: string[]
}
```

### Layer 1: Constraints (Hard Rules)

Never overridden. Encoded in source code.

```typescript
const HARD_RULES: ConstraintRule[] = [
  {
    // Core blind-spot elimination: reviewer must differ from worker
    name: "cross_model_review",
    condition: (ctx) => ctx.agent_role === "reviewer",
    action: (ctx, candidate) => {
      const worker_model = ctx.previous_models.find(m => m.role === "worker")
      return candidate.provider !== worker_model?.provider
    },
  },
  {
    // Only route to providers the user has keys for
    name: "key_availability",
    condition: () => true,
    action: (ctx, candidate) => ctx.provider_keys.includes(candidate.provider),
  },
  {
    // Image generation: OpenAI only
    name: "image_gen_openai_only",
    condition: (ctx) => ctx.tool_requested === "generate_sprite",
    action: () => ({ provider: "openai", model: "gpt-image-1" }),
  },
  {
    // Computer use: GPT-5.4 only
    name: "computer_use_gpt54",
    condition: (ctx) => ctx.computer_use === true,
    action: () => ({ provider: "openai", model: "gpt-5.4" }),
  },
]
```

### Layer 2: Policy Table (Configurable Rules)

Stored in KV, hot-updatable. Open-source default in `routing-rules.default.json`.

```typescript
const DEFAULT_POLICY: PolicyTable = {
  role_preference: {
    planner: {
      primary:   { provider: "anthropic", model: "claude-sonnet-4.6" },
      economy:   { provider: "gemini",    model: "gemini-3.1-flash" },
      reason: "Claude excels at long-context planning and structured analysis",
    },
    worker: {
      primary:   { provider: "openai",    model: "gpt-5.4" },
      economy:   { provider: "openai",    model: "gpt-5.4-mini" },
      reason: "GPT structured output and tool calling most stable",
    },
    reviewer: {
      primary:   { provider: "anthropic", model: "claude-sonnet-4.6" },
      economy:   { provider: "gemini",    model: "gemini-3.1-pro" },
      reason: "Cross-model review eliminates blind spots; Claude strong at critical analysis",
    },
    playtest_analyst: {
      primary:   { provider: "gemini",    model: "gemini-3.1-flash" },
      economy:   { provider: "gemini",    model: "gemini-3.1-flash" },
      reason: "Structured judgment task, speed and cost efficiency sufficient",
    },
  },

  // Per-skill overrides
  skill_override: {
    ui_layout: {
      worker: { provider: "anthropic", model: "claude-sonnet-4.6" },
      reason: "Claude more nuanced at UI structure reasoning than GPT",
    },
  },

  // Round-based downgrade
  round_downgrade: {
    threshold: 4,
    downgrade_to: "economy",
    reason: "Late-round fixes are small edits, don't need top-tier models",
  },

  // Changeset-based upgrade
  changeset_upgrade: {
    threshold: 10,
    upgrade_to: "primary",
    reason: "Large changesets need stronger context understanding",
  },
}
```

### Layer 3: Intelligence (Data-Driven Adjustment)

Consumes quality scores from D1. Adapts routing based on observed model performance.

**Key behaviors:**
- **Quality trend decline** — If recent 3 scores average < 3.0, switch to the highest-rated alternative model.
- **A/B experiment injection** — 5% of traffic randomly assigned to challenger models for continuous data collection.
- **Insufficient samples** — Fall through to Layer 2 policy when sample count < 20 for a model+role combination.

```typescript
async function applyIntelligence(
  ctx: RouteContext,
  policyChoice: RouteDecision,
  scores: ModelScore[],
): Promise<RouteDecision> {
  const relevant = scores.filter(s =>
    s.agent_role === ctx.agent_role && s.sample_count >= 20
  )
  if (relevant.length < 2) return policyChoice

  // Quality trend declining → switch model
  if (ctx.quality_trend.length >= 3) {
    const recent_avg = avg(ctx.quality_trend.slice(-3))
    if (recent_avg < 3.0) {
      const best = relevant
        .filter(s => s.provider !== policyChoice.provider)
        .sort((a, b) => b.avg_quality - a.avg_quality)[0]
      if (best && best.avg_quality > recent_avg + 0.5) {
        return {
          ...policyChoice,
          provider: best.provider,
          model: best.model,
          reason: `Quality declining (${recent_avg.toFixed(1)}), switching to ${best.model} (avg ${best.avg_quality.toFixed(1)})`,
        }
      }
    }
  }

  // A/B experiment (5% traffic)
  if (Math.random() < 0.05 && relevant.length >= 2) {
    const challenger = relevant
      .filter(s => s.provider !== policyChoice.provider)
      .sort(() => Math.random() - 0.5)[0]
    return {
      provider: challenger.provider,
      model: challenger.model,
      reason: `A/B experiment: testing ${challenger.model} against ${policyChoice.model}`,
      experiment_id: crypto.randomUUID(),
      fallback_chain: [policyChoice.model],
    }
  }

  return policyChoice
}
```

### Fallback Chain

When primary model API fails (429/500/timeout), automatic failover:

- Reviewer fallback also respects `cross_model_review` constraint.
- Up to 2 fallback attempts before returning error to god-code.

---

## Quality Scorer Pipeline

### Why Automated Scoring

The routing engine's Layer 3 needs quality data to optimize. Manual scoring at 20+ rounds per session is infeasible. Solution: **use a cheap model to grade expensive models' output**.

```
Worker (GPT-5.4) produces code
        │
        ▼  waitUntil() async
Quality Scorer (Gemini Flash)
        │
        ▼
    Quality scores → D1
        │
        ▼
    Route weights auto-adjust
```

### Scoring Dimensions (1-5 each)

```typescript
interface QualityAssessment {
  request_id: string
  session_id: string
  agent_role: string
  skill: string | null
  provider: string
  model: string

  scores: {
    correctness: number       // Code/response correctness for Godot 4.4
    completeness: number      // Task fully addressed, no TODOs
    tool_usage: number        // Right tools used, no waste
    godot_conventions: number // Signal naming, node structure, script ordering
    efficiency: number        // Token usage efficiency
  }

  overall: number             // Weighted composite
  flags: string[]             // "hallucination", "incomplete_tool_call", "wrong_api"
  latency_ms: number
  prompt_tokens: number
  completion_tokens: number
  cost_estimate: number
  scored_by: string           // Scoring model ID
}
```

### Scoring Prompt

Short, structured, reliable. Evaluator receives:
- Agent role context
- Compressed request summary (~500 tokens)
- Response content (truncated to ~1500 tokens, head + tail preserved)
- Tool call summary (name + success/fail only, no full arguments)

Output: JSON with 5 dimension scores + flags array.

### Sampling Rate Control

Not every response needs scoring — intelligent sampling:

| Condition | Rate |
|-----------|------|
| Base rate | 30% |
| A/B experiment active | 100% |
| New model first 50 calls | 100% |
| Quality drop detected | 100% |
| Reviewer responses | 80% |
| High-confidence model (>200 samples, stable) | 10% |
| Explain mode | 10% |

### Context Compression

Scoring model doesn't need full conversation. Compress to ~2000 tokens:
1. **Request**: Last user message only, truncated to 500 tokens
2. **Response**: Smart truncate to 1500 tokens (keep head + tail)
3. **Tools**: Name + success/fail only, no arguments or full responses

### Quality Alerts

- **Score drop**: New score > 1.5 below 7-day average → alert
- **Hallucination flag**: Immediate alert
- Alerts stored in D1, surfaced in `/v1/session/:id/quality`

### Cost

~$0.00007 per scoring call. At 100 sessions/day × 6 scored rounds/session = **$1.26/month**. Negligible.

---

## Session State Management (Durable Objects)

### Why Session State

| Need | Why stateless proxy can't do it |
|------|--------------------------------|
| Reviewer ≠ worker provider | Must know what worker used |
| Quality trend detection | Must remember recent scores |
| A/B experiment tracking | Must keep user in same cohort |
| Round-based downgrade | Must track cumulative rounds |
| Future consensus mode | Must coordinate parallel calls |

### SessionState Structure

```typescript
interface SessionState {
  session_id: string
  created_at: string
  last_active: string

  route_history: RouteRecord[]     // Last 50 routing decisions
  quality_window: number[]          // Last 10 quality scores (sliding)
  quality_alerts: number

  experiment_assignments: Record<string, string>

  user_config: {
    available_providers: string[]
    cost_preference: string
    custom_overrides: Record<string, string>
  }

  usage: {
    total_requests: number
    total_prompt_tokens: number
    total_completion_tokens: number
    estimated_cost_usd: number
    by_provider: Record<string, { requests: number; tokens: number; cost: number }>
  }
}
```

### DO Endpoints

| Endpoint | Purpose | Timing |
|----------|---------|--------|
| `/route-context` | Provide cross-request context for routing | Sync, before routing |
| `/record-route` | Record routing decision | Sync, after provider response |
| `/record-quality` | Backfill quality score | Async |
| `/usage` | Query session usage stats | On-demand |
| `/configure` | Update user preferences | On-demand |

### Session Lifecycle

```
Create              Active                Sleep              Destroy
│                   │                     │                  │
▼                   ▼                     ▼                  ▼
First request   Continuous requests   10 min idle        30 days unused
→ new instance  → in-memory fast      → CF auto-sleep    → alarm cleanup
→ init state    → single-threaded     → next req wakes   → archive to D1
                                      → ~$0 cost
```

### Consensus Mode Ready (v2)

DO's single-threaded nature naturally supports consensus coordination:
- Fan out to 2-3 providers in parallel
- Use scoring model to select best response
- **Key insight**: Consensus produces high-quality comparative scoring data (same task, different models, direct comparison) — this calibrates the Quality Scorer itself.

### Cost

~$0.09/month at 100 sessions/day. Negligible.

---

## API Contract

### Core Endpoint: `POST /v1/orchestrate`

```typescript
// Request
interface OrchestrateRequest {
  messages: Message[]
  tools?: ToolDefinition[]
  stream?: boolean

  metadata: {
    session_id: string
    agent_role: "planner" | "worker" | "reviewer" | "playtest_analyst"
    skill: string | null
    mode: "apply" | "plan" | "review" | "fix" | "explain"
    round_number: number
    changeset_size: number
    estimated_tokens: number
  }

  provider_keys?: Record<string, string>   // BYOK

  preferences?: {
    cost_preference?: "economy" | "balanced" | "quality"
    force_provider?: string
    force_model?: string
  }
}

// Response (OpenAI chat completions compatible)
interface OrchestrateResponse {
  choices: [{
    message: {
      role: "assistant"
      content: string | null
      tool_calls?: ToolCall[]
    }
  }]
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }

  // Routing transparency
  routing: {
    provider: string
    model: string
    reason: string
    experiment_id: string | null
    latency_ms: number
    quality_estimate: number | null
  }
}
```

### Auxiliary Endpoints

```
GET  /v1/session/:id/usage     → Usage statistics
GET  /v1/session/:id/quality   → Quality report
POST /v1/session/:id/configure → Update preferences
GET  /v1/models                → Available models + quality scores
GET  /v1/health                → Health check + provider status

# OAuth phase additions
POST /v1/auth/token            → OAuth token exchange
GET  /v1/account/usage         → Account usage + billing
```

### Error Format

```typescript
interface OrchestrateError {
  error: {
    code: string           // "provider_unavailable" | "key_invalid" | "rate_limited" | "budget_exceeded"
    message: string
    provider: string
    retryable: boolean
    fallback_attempted: boolean
    fallback_provider: string | null
  }
}
```

### Streaming

SSE format, OpenAI compatible. Routing metadata appended before `[DONE]`:

```
data: {"choices":[{"delta":{"content":"extends "}}]}
data: {"choices":[{"delta":{"content":"CharacterBody2D"}}]}
...
data: {"choices":[{"delta":{"content":""}}],"finish_reason":"stop"}
data: {"routing":{"provider":"openai","model":"gpt-5.4","reason":"worker default","latency_ms":1234}}
data: [DONE]
```

---

## god-code Client Adaptation

### Scope: ~120 lines across 3 files

Zero breaking changes. When `backend_url` is empty (default), all behavior is identical to current version.

### 1. `godot_agent/runtime/config.py` (+15 lines)

New optional fields:

```python
backend_url: str = ""                    # Empty = direct provider (current behavior)
backend_cost_preference: str = "balanced"
backend_force_provider: str = ""
backend_force_model: str = ""
backend_provider_keys: dict[str, str] = field(default_factory=dict)
```

### 2. `godot_agent/llm/client.py` (~80 lines)

Dual-path chat method:

```python
async def chat(self, messages, tools=None, *, route_metadata=None):
    if self._use_backend and route_metadata:
        return await self._chat_via_backend(messages, tools, route_metadata)
    return await self._chat_direct(messages, tools)  # Existing logic, unchanged
```

`_chat_via_backend()` sends `OrchestrateRequest` to Workers, parses `OrchestrateResponse`, logs routing info.

### 3. `godot_agent/runtime/engine.py` (~25 lines)

Inject route metadata on each LLM call:

```python
route_metadata = {
    "session_id": self.session_id,
    "agent_role": self._current_agent_role or "worker",
    "skill": self._active_skill_key(),
    "mode": self.mode,
    "round_number": self._current_round,
    "changeset_size": len(self.changeset.modified_files),
    "estimated_tokens": self._estimate_message_tokens(),
}
response = await self.client.chat(messages, tools, route_metadata=route_metadata)
```

### Backward Compatibility

All existing tests pass without modification. `backend_url=""` means `_use_backend=False`, which means `route_metadata` is ignored and `_chat_direct()` runs the exact current code path.

---

## Workers Project Structure

```
god-code-api/
├── src/
│   ├── index.ts                 # Worker entry, HTTP routing
│   ├── auth/
│   │   ├── guard.ts             # API key validation + future OAuth
│   │   └── key_encrypt.ts       # BYOK key passthrough (never stored)
│   ├── router/
│   │   ├── engine.ts            # 3-layer routing engine
│   │   ├── constraints.ts       # Layer 1: hard rules
│   │   ├── policy.ts            # Layer 2: configurable policy
│   │   ├── intelligence.ts      # Layer 3: data-driven adjustment
│   │   └── fallback.ts          # Fallback chain logic
│   ├── providers/
│   │   ├── dispatch.ts          # Unified provider call + response normalization
│   │   ├── openai.ts            # OpenAI adapter
│   │   ├── anthropic.ts         # Anthropic adapter (messages API conversion)
│   │   ├── gemini.ts            # Gemini adapter
│   │   └── xai.ts               # xAI adapter
│   ├── scoring/
│   │   ├── pipeline.ts          # Quality scoring pipeline
│   │   ├── sampler.ts           # Sampling rate control
│   │   ├── compressor.ts        # Context compression
│   │   └── alerts.ts            # Quality anomaly alerts
│   ├── session/
│   │   └── durable_object.ts    # Session DO implementation
│   ├── experiments/
│   │   ├── ab_framework.ts      # A/B testing framework
│   │   └── analysis.ts          # Experiment result analysis
│   └── types.ts                 # Shared type definitions
├── schema/
│   ├── 001_init.sql             # D1 initial schema
│   └── 002_quality_scores.sql   # Quality scoring tables + views
├── routing-rules.default.json   # Open-source default routing rules
├── wrangler.toml
├── package.json
├── tsconfig.json
├── vitest.config.ts
└── tests/
    ├── router/
    │   ├── constraints.test.ts
    │   ├── policy.test.ts
    │   └── intelligence.test.ts
    ├── scoring/
    │   └── pipeline.test.ts
    ├── session/
    │   └── durable_object.test.ts
    └── integration/
        └── orchestrate.test.ts
```

---

## D1 Database Schema

```sql
-- Route decisions log
CREATE TABLE route_decisions (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  agent_role TEXT NOT NULL,
  skill TEXT,
  mode TEXT NOT NULL,
  round_number INTEGER NOT NULL,
  changeset_size INTEGER NOT NULL,
  estimated_tokens INTEGER,
  chosen_provider TEXT NOT NULL,
  chosen_model TEXT NOT NULL,
  reason TEXT,
  experiment_id TEXT,
  latency_ms INTEGER,
  cost_estimate REAL,
  quality_score REAL,
  quality_scored_by TEXT,
  quality_scored_at TEXT
);

CREATE INDEX idx_decisions_session ON route_decisions(session_id);
CREATE INDEX idx_decisions_role_model ON route_decisions(agent_role, chosen_model);
CREATE INDEX idx_decisions_experiment ON route_decisions(experiment_id)
  WHERE experiment_id IS NOT NULL;

-- Quality scores
CREATE TABLE quality_scores (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  agent_role TEXT NOT NULL,
  skill TEXT,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  correctness REAL NOT NULL,
  completeness REAL NOT NULL,
  tool_usage REAL NOT NULL,
  godot_conventions REAL NOT NULL,
  efficiency REAL NOT NULL,
  overall REAL NOT NULL,
  flags TEXT,
  latency_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_estimate REAL,
  scored_by TEXT NOT NULL,
  scoring_cost REAL,
  experiment_id TEXT
);

CREATE INDEX idx_quality_provider_model ON quality_scores(provider, model, agent_role);

-- Aggregated model performance view
CREATE VIEW model_performance AS
SELECT
  provider,
  model,
  agent_role,
  skill,
  COUNT(*) as sample_count,
  AVG(overall) as avg_quality,
  AVG(correctness) as avg_correctness,
  AVG(completeness) as avg_completeness,
  AVG(tool_usage) as avg_tool_usage,
  AVG(godot_conventions) as avg_godot,
  AVG(efficiency) as avg_efficiency,
  AVG(latency_ms) as avg_latency,
  AVG(cost_estimate) as avg_cost,
  MAX(timestamp) as last_scored
FROM quality_scores
WHERE timestamp > datetime('now', '-30 days')
GROUP BY provider, model, agent_role, skill;

-- Quality alerts
CREATE TABLE quality_alerts (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  type TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  agent_role TEXT,
  current_score REAL,
  baseline_score REAL,
  message TEXT NOT NULL,
  request_id TEXT,
  acknowledged INTEGER DEFAULT 0
);
```

---

## Deployment Plan

### Phase 1: Internal Version

```bash
# 1. Create repo
gh repo create 888wing/god-code-api --private

# 2. Deploy Workers
npx wrangler d1 create god-code-api
npx wrangler d1 execute god-code-api --file=schema/001_init.sql
npx wrangler d1 execute god-code-api --file=schema/002_quality_scores.sql
npx wrangler kv namespace create ROUTING_KV
npx wrangler deploy

# 3. Configure god-code
god-code set backend_url https://god-code-api.<your>.workers.dev
god-code set backend_provider_keys.openai sk-xxx
god-code set backend_provider_keys.anthropic sk-ant-xxx
god-code set backend_provider_keys.gemini AIza-xxx
```

### Phase 2: Open Source BYOK

```bash
# 1. Repo → public, GPL-3.0
# 2. Users fork and deploy to own CF account
# 3. README + one-click deploy button

# User flow:
git clone https://github.com/888wing/god-code-api
cd god-code-api
npx wrangler deploy
```

### Phase 3: OAuth Managed Service

```
# Add OAuth endpoints
# Users no longer need provider keys
# Billing: per-task or per-token
# Routing uses officially accumulated optimal weights
# Premium tier: consensus mode
```

---

## Cost Estimates (100 sessions/day)

| Component | Monthly Cost |
|-----------|-------------|
| Workers requests | ~$0.15 |
| Durable Objects | ~$0.09 |
| D1 storage | ~$0.05 |
| KV reads | ~$0.01 |
| Quality scoring (Gemini Flash) | ~$1.26 |
| **Total** | **~$1.56/month** |

---

## Summary

| Component | Location | Tech | Est. Lines |
|-----------|----------|------|-----------|
| Task Router (3-layer) | god-code-api | CF Workers + KV | ~300 |
| Provider Dispatch | god-code-api | Workers | ~200 |
| Quality Scorer | god-code-api | Workers + Gemini Flash | ~250 |
| Session DO | god-code-api | Durable Objects | ~200 |
| A/B Framework | god-code-api | Workers + D1 | ~150 |
| D1 Schema | god-code-api | SQL | ~60 |
| Auth Guard | god-code-api | Workers | ~100 |
| Tests | god-code-api | Vitest | ~400 |
| **god-code adaptation** | **god-code** | **Python** | **~120** |
| **Total** | | | **~1780** |

### Non-Goals for v1

- OAuth implementation (Phase 3)
- Consensus mode (Phase 2 premium)
- Dashboard UI (CLI + D1 queries sufficient initially)
- Multi-region deployment (single CF region is fine at this scale)

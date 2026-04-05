# God Code API Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `god-code-api` — a CF Workers orchestration backend that routes god-code's LLM calls across providers with quality scoring and A/B testing — plus the minimal client adaptation in `god-code`.

**Architecture:** Two repos. `god-code-api` is a new TypeScript CF Workers project with D1, Durable Objects, and KV. `god-code` gets ~120 lines of Python adaptation (dual-path LLMClient + config fields + engine metadata injection).

**Tech Stack:** TypeScript, Cloudflare Workers, D1 (SQLite), Durable Objects, KV, Vitest. Python (god-code client side), pytest.

**Design Doc:** `docs/plans/2026-04-04-api-backend-design.md`

---

## Phase 1: Project Scaffold + Shared Types

### Task 1: Initialize god-code-api project

**Files:**
- Create: `~/projects/god-code-api/package.json`
- Create: `~/projects/god-code-api/tsconfig.json`
- Create: `~/projects/god-code-api/wrangler.toml`
- Create: `~/projects/god-code-api/vitest.config.ts`
- Create: `~/projects/god-code-api/.gitignore`

**Step 1: Create project directory and init**

```bash
mkdir -p ~/projects/god-code-api
cd ~/projects/god-code-api
git init
```

**Step 2: Create package.json**

```json
{
  "name": "god-code-api",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20250327.0",
    "typescript": "^5.7",
    "vitest": "^3.1",
    "wrangler": "^4.14"
  }
}
```

**Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "outDir": "dist",
    "rootDir": "src",
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

**Step 4: Create wrangler.toml**

```toml
name = "god-code-api"
main = "src/index.ts"
compatibility_date = "2025-12-01"

[durable_objects]
bindings = [
  { name = "SESSION_DO", class_name = "SessionDO" }
]

[[migrations]]
tag = "v1"
new_classes = ["SessionDO"]

[[d1_databases]]
binding = "DB"
database_name = "god-code-api"
database_id = "local"

[[kv_namespaces]]
binding = "ROUTING_KV"
id = "local"

[vars]
SCORING_MODEL = "gemini-3.1-flash"
SCORING_SAMPLE_RATE = "0.3"
AB_TRAFFIC_PERCENTAGE = "0.05"
```

**Step 5: Create vitest.config.ts**

```typescript
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    globals: true,
    environment: "node",
  },
});
```

**Step 6: Create .gitignore, install deps, commit**

```bash
echo "node_modules/\ndist/\n.wrangler/\n.dev.vars" > .gitignore
npm install
git add -A
git commit -m "chore: init god-code-api project scaffold"
```

---

### Task 2: Define shared types

**Files:**
- Create: `~/projects/god-code-api/src/types.ts`
- Test: `~/projects/god-code-api/tests/types.test.ts`

**Step 1: Write the test**

```typescript
// tests/types.test.ts
import { describe, it, expect } from "vitest";
import type {
  OrchestrateRequest,
  OrchestrateResponse,
  RouteContext,
  RouteDecision,
  QualityAssessment,
  SessionState,
  RouteRecord,
  Env,
} from "../src/types";

describe("types", () => {
  it("OrchestrateRequest has required fields", () => {
    const req: OrchestrateRequest = {
      messages: [{ role: "user", content: "hello" }],
      metadata: {
        session_id: "s1",
        agent_role: "worker",
        skill: null,
        mode: "apply",
        round_number: 1,
        changeset_size: 2,
        estimated_tokens: 500,
      },
    };
    expect(req.metadata.agent_role).toBe("worker");
    expect(req.provider_keys).toBeUndefined();
  });

  it("RouteDecision has fallback_chain", () => {
    const decision: RouteDecision = {
      provider: "openai",
      model: "gpt-5.4",
      reason: "worker default",
      experiment_id: null,
      fallback_chain: ["anthropic/claude-sonnet-4.6"],
    };
    expect(decision.fallback_chain).toHaveLength(1);
  });

  it("SessionState initializes with empty collections", () => {
    const state: SessionState = {
      session_id: "s1",
      created_at: "2026-04-04",
      last_active: "2026-04-04",
      route_history: [],
      quality_window: [],
      quality_alerts: 0,
      experiment_assignments: {},
      user_config: {
        available_providers: [],
        cost_preference: "balanced",
        custom_overrides: {},
      },
      usage: {
        total_requests: 0,
        total_prompt_tokens: 0,
        total_completion_tokens: 0,
        estimated_cost_usd: 0,
        by_provider: {},
      },
    };
    expect(state.route_history).toHaveLength(0);
    expect(state.usage.total_requests).toBe(0);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run tests/types.test.ts
```

Expected: FAIL — module `../src/types` not found.

**Step 3: Write types.ts**

```typescript
// src/types.ts

// ─── Message types ───

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface ToolDefinition {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
    strict?: boolean;
  };
}

// ─── API contract ───

export type AgentRole = "planner" | "worker" | "reviewer" | "playtest_analyst";
export type Mode = "apply" | "plan" | "review" | "fix" | "explain";
export type CostPreference = "economy" | "balanced" | "quality";

export interface OrchestrateRequest {
  messages: Message[];
  tools?: ToolDefinition[];
  stream?: boolean;
  metadata: {
    session_id: string;
    agent_role: AgentRole;
    skill: string | null;
    mode: Mode;
    round_number: number;
    changeset_size: number;
    estimated_tokens: number;
  };
  provider_keys?: Record<string, string>;
  preferences?: {
    cost_preference?: CostPreference;
    force_provider?: string;
    force_model?: string;
  };
}

export interface RoutingInfo {
  provider: string;
  model: string;
  reason: string;
  experiment_id: string | null;
  latency_ms: number;
  quality_estimate: number | null;
}

export interface OrchestrateResponse {
  choices: [
    {
      message: {
        role: "assistant";
        content: string | null;
        tool_calls?: ToolCall[];
      };
    },
  ];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  routing: RoutingInfo;
}

export interface OrchestrateError {
  error: {
    code: string;
    message: string;
    provider: string;
    retryable: boolean;
    fallback_attempted: boolean;
    fallback_provider: string | null;
  };
}

// ─── Router types ───

export interface RouteContext {
  agent_role: AgentRole;
  skill: string | null;
  mode: Mode;
  round_number: number;
  changeset_size: number;
  estimated_tokens: number;
  session_id: string;
  previous_models: { role: string; provider: string; model: string }[];
  quality_trend: number[];
  provider_keys: string[];
  cost_preference: CostPreference;
  custom_overrides: Record<string, string>;
  tool_requested?: string;
  computer_use?: boolean;
}

export interface RouteDecision {
  provider: string;
  model: string;
  reason: string;
  experiment_id: string | null;
  fallback_chain: string[];
}

export interface ModelScore {
  provider: string;
  model: string;
  agent_role: string;
  skill: string | null;
  avg_quality: number;
  p95_latency_ms: number;
  cost_per_1k_tokens: number;
  sample_count: number;
  last_updated: string;
}

// ─── Session types ───

export interface RouteRecord {
  request_id: string;
  timestamp: string;
  agent_role: string;
  skill: string | null;
  round_number: number;
  provider: string;
  model: string;
  latency_ms: number;
  tokens: number;
  quality_score: number | null;
}

export interface SessionState {
  session_id: string;
  created_at: string;
  last_active: string;
  route_history: RouteRecord[];
  quality_window: number[];
  quality_alerts: number;
  experiment_assignments: Record<string, string>;
  user_config: {
    available_providers: string[];
    cost_preference: string;
    custom_overrides: Record<string, string>;
  };
  usage: {
    total_requests: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    estimated_cost_usd: number;
    by_provider: Record<
      string,
      { requests: number; tokens: number; cost: number }
    >;
  };
}

// ─── Quality types ───

export interface QualityAssessment {
  request_id: string;
  session_id: string;
  agent_role: string;
  skill: string | null;
  provider: string;
  model: string;
  scores: {
    correctness: number;
    completeness: number;
    tool_usage: number;
    godot_conventions: number;
    efficiency: number;
  };
  overall: number;
  flags: string[];
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate: number;
  scored_by: string;
}

// ─── Worker env ───

export interface Env {
  DB: D1Database;
  ROUTING_KV: KVNamespace;
  SESSION_DO: DurableObjectNamespace;
  SCORING_MODEL: string;
  SCORING_SAMPLE_RATE: string;
  AB_TRAFFIC_PERCENTAGE: string;
}
```

**Step 4: Run test to verify it passes**

```bash
npx vitest run tests/types.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/types.ts tests/types.test.ts
git commit -m "feat: add shared type definitions"
```

---

### Task 3: Create D1 schema

**Files:**
- Create: `~/projects/god-code-api/schema/001_init.sql`
- Create: `~/projects/god-code-api/schema/002_quality_scores.sql`

**Step 1: Write 001_init.sql**

```sql
-- schema/001_init.sql
CREATE TABLE IF NOT EXISTS route_decisions (
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

CREATE INDEX IF NOT EXISTS idx_decisions_session ON route_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_role_model ON route_decisions(agent_role, chosen_model);
CREATE INDEX IF NOT EXISTS idx_decisions_experiment ON route_decisions(experiment_id)
  WHERE experiment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS quality_alerts (
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

**Step 2: Write 002_quality_scores.sql**

```sql
-- schema/002_quality_scores.sql
CREATE TABLE IF NOT EXISTS quality_scores (
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

CREATE INDEX IF NOT EXISTS idx_quality_provider_model ON quality_scores(provider, model, agent_role);

CREATE VIEW IF NOT EXISTS model_performance AS
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
```

**Step 3: Commit**

```bash
git add schema/
git commit -m "feat: add D1 database schema"
```

---

### Task 4: Create default routing rules

**Files:**
- Create: `~/projects/god-code-api/routing-rules.default.json`
- Test: `~/projects/god-code-api/tests/router/policy.test.ts` (partial — load test)

**Step 1: Write the test**

```typescript
// tests/router/policy.test.ts
import { describe, it, expect } from "vitest";
import rules from "../../routing-rules.default.json";

describe("routing-rules.default.json", () => {
  it("has all four agent roles", () => {
    const roles = Object.keys(rules.role_preference);
    expect(roles).toContain("planner");
    expect(roles).toContain("worker");
    expect(roles).toContain("reviewer");
    expect(roles).toContain("playtest_analyst");
  });

  it("each role has primary and economy", () => {
    for (const [role, pref] of Object.entries(rules.role_preference)) {
      expect(pref).toHaveProperty("primary");
      expect(pref).toHaveProperty("economy");
      expect((pref as any).primary).toHaveProperty("provider");
      expect((pref as any).primary).toHaveProperty("model");
    }
  });

  it("reviewer primary differs from worker primary provider", () => {
    const worker = (rules.role_preference as any).worker.primary.provider;
    const reviewer = (rules.role_preference as any).reviewer.primary.provider;
    expect(reviewer).not.toBe(worker);
  });

  it("has round_downgrade and changeset_upgrade", () => {
    expect(rules.round_downgrade.threshold).toBeGreaterThan(0);
    expect(rules.changeset_upgrade.threshold).toBeGreaterThan(0);
  });
});
```

**Step 2: Run test — FAIL**

```bash
npx vitest run tests/router/policy.test.ts
```

**Step 3: Write routing-rules.default.json**

```json
{
  "role_preference": {
    "planner": {
      "primary": { "provider": "anthropic", "model": "claude-sonnet-4.6" },
      "economy": { "provider": "gemini", "model": "gemini-3.1-flash" },
      "reason": "Claude excels at long-context planning and structured analysis"
    },
    "worker": {
      "primary": { "provider": "openai", "model": "gpt-5.4" },
      "economy": { "provider": "openai", "model": "gpt-5.4-mini" },
      "reason": "GPT structured output and tool calling most stable"
    },
    "reviewer": {
      "primary": { "provider": "anthropic", "model": "claude-sonnet-4.6" },
      "economy": { "provider": "gemini", "model": "gemini-3.1-pro" },
      "reason": "Cross-model review eliminates blind spots"
    },
    "playtest_analyst": {
      "primary": { "provider": "gemini", "model": "gemini-3.1-flash" },
      "economy": { "provider": "gemini", "model": "gemini-3.1-flash" },
      "reason": "Structured judgment task, speed and cost efficiency sufficient"
    }
  },
  "skill_override": {
    "ui_layout": {
      "worker": { "provider": "anthropic", "model": "claude-sonnet-4.6" },
      "reason": "Claude more nuanced at UI structure reasoning"
    }
  },
  "round_downgrade": {
    "threshold": 4,
    "downgrade_to": "economy",
    "reason": "Late-round fixes are small edits"
  },
  "changeset_upgrade": {
    "threshold": 10,
    "upgrade_to": "primary",
    "reason": "Large changesets need stronger context understanding"
  }
}
```

**Step 4: Run test — PASS**

```bash
npx vitest run tests/router/policy.test.ts
```

**Step 5: Commit**

```bash
git add routing-rules.default.json tests/router/policy.test.ts
git commit -m "feat: add default routing rules"
```

---

## Phase 2: Router Engine

### Task 5: Layer 1 — Constraints

**Files:**
- Create: `~/projects/god-code-api/src/router/constraints.ts`
- Test: `~/projects/god-code-api/tests/router/constraints.test.ts`

**Step 1: Write the test**

```typescript
// tests/router/constraints.test.ts
import { describe, it, expect } from "vitest";
import { applyConstraints } from "../../src/router/constraints";
import type { RouteContext, RouteDecision } from "../../src/types";

function makeCtx(overrides: Partial<RouteContext> = {}): RouteContext {
  return {
    agent_role: "worker",
    skill: null,
    mode: "apply",
    round_number: 1,
    changeset_size: 2,
    estimated_tokens: 500,
    session_id: "s1",
    previous_models: [],
    quality_trend: [],
    provider_keys: ["openai", "anthropic", "gemini"],
    cost_preference: "balanced",
    custom_overrides: {},
    ...overrides,
  };
}

function makeDecision(overrides: Partial<RouteDecision> = {}): RouteDecision {
  return {
    provider: "openai",
    model: "gpt-5.4",
    reason: "default",
    experiment_id: null,
    fallback_chain: [],
    ...overrides,
  };
}

describe("constraints", () => {
  it("cross_model_review: reviewer rejects same provider as worker", () => {
    const ctx = makeCtx({
      agent_role: "reviewer",
      previous_models: [{ role: "worker", provider: "openai", model: "gpt-5.4" }],
    });
    const result = applyConstraints(ctx, makeDecision({ provider: "openai" }));
    expect(result.blocked).toBe(true);
    expect(result.rule).toBe("cross_model_review");
  });

  it("cross_model_review: reviewer accepts different provider", () => {
    const ctx = makeCtx({
      agent_role: "reviewer",
      previous_models: [{ role: "worker", provider: "openai", model: "gpt-5.4" }],
    });
    const result = applyConstraints(ctx, makeDecision({ provider: "anthropic" }));
    expect(result.blocked).toBe(false);
  });

  it("cross_model_review: does not apply to worker", () => {
    const ctx = makeCtx({ agent_role: "worker" });
    const result = applyConstraints(ctx, makeDecision({ provider: "openai" }));
    expect(result.blocked).toBe(false);
  });

  it("key_availability: blocks provider without key", () => {
    const ctx = makeCtx({ provider_keys: ["openai"] });
    const result = applyConstraints(ctx, makeDecision({ provider: "anthropic" }));
    expect(result.blocked).toBe(true);
    expect(result.rule).toBe("key_availability");
  });

  it("image_gen: forces openai", () => {
    const ctx = makeCtx({ tool_requested: "generate_sprite" });
    const result = applyConstraints(ctx, makeDecision());
    expect(result.forced).toBeDefined();
    expect(result.forced?.provider).toBe("openai");
  });

  it("computer_use: forces gpt-5.4", () => {
    const ctx = makeCtx({ computer_use: true });
    const result = applyConstraints(ctx, makeDecision());
    expect(result.forced).toBeDefined();
    expect(result.forced?.model).toBe("gpt-5.4");
  });
});
```

**Step 2: Run test — FAIL**

```bash
npx vitest run tests/router/constraints.test.ts
```

**Step 3: Implement constraints.ts**

```typescript
// src/router/constraints.ts
import type { RouteContext, RouteDecision } from "../types";

export interface ConstraintResult {
  blocked: boolean;
  rule?: string;
  reason?: string;
  forced?: Partial<RouteDecision>;
}

export function applyConstraints(
  ctx: RouteContext,
  candidate: RouteDecision,
): ConstraintResult {
  // Force rules (override candidate entirely)
  if (ctx.tool_requested === "generate_sprite") {
    return {
      blocked: false,
      forced: { provider: "openai", model: "gpt-image-1", reason: "image_gen_openai_only" },
    };
  }
  if (ctx.computer_use) {
    return {
      blocked: false,
      forced: { provider: "openai", model: "gpt-5.4", reason: "computer_use_gpt54" },
    };
  }

  // Block rules (reject candidate)
  if (!ctx.provider_keys.includes(candidate.provider)) {
    return { blocked: true, rule: "key_availability", reason: `No key for ${candidate.provider}` };
  }

  if (ctx.agent_role === "reviewer") {
    const workerEntry = ctx.previous_models.find((m) => m.role === "worker");
    if (workerEntry && candidate.provider === workerEntry.provider) {
      return {
        blocked: true,
        rule: "cross_model_review",
        reason: `Reviewer must differ from worker provider (${workerEntry.provider})`,
      };
    }
  }

  return { blocked: false };
}
```

**Step 4: Run test — PASS**

```bash
npx vitest run tests/router/constraints.test.ts
```

**Step 5: Commit**

```bash
git add src/router/constraints.ts tests/router/constraints.test.ts
git commit -m "feat: add Layer 1 constraint rules"
```

---

### Task 6: Layer 2 — Policy

**Files:**
- Create: `~/projects/god-code-api/src/router/policy.ts`
- Modify: `~/projects/god-code-api/tests/router/policy.test.ts` (add apply tests)

**Step 1: Add tests to existing policy.test.ts**

```typescript
// Append to tests/router/policy.test.ts
import { applyPolicy } from "../../src/router/policy";
import type { RouteContext } from "../../src/types";

function makeCtx(overrides: Partial<RouteContext> = {}): RouteContext {
  return {
    agent_role: "worker",
    skill: null,
    mode: "apply",
    round_number: 1,
    changeset_size: 2,
    estimated_tokens: 500,
    session_id: "s1",
    previous_models: [],
    quality_trend: [],
    provider_keys: ["openai", "anthropic", "gemini"],
    cost_preference: "balanced",
    custom_overrides: {},
    ...overrides,
  };
}

describe("applyPolicy", () => {
  it("returns primary model for worker balanced", () => {
    const decision = applyPolicy(makeCtx(), rules);
    expect(decision.provider).toBe("openai");
    expect(decision.model).toBe("gpt-5.4");
  });

  it("returns economy model for economy preference", () => {
    const decision = applyPolicy(makeCtx({ cost_preference: "economy" }), rules);
    expect(decision.model).toBe("gpt-5.4-mini");
  });

  it("downgrades to economy after round threshold", () => {
    const decision = applyPolicy(makeCtx({ round_number: 5 }), rules);
    expect(decision.model).toBe("gpt-5.4-mini");
    expect(decision.reason).toContain("round");
  });

  it("upgrades to primary for large changeset", () => {
    const decision = applyPolicy(
      makeCtx({ cost_preference: "economy", changeset_size: 15 }),
      rules,
    );
    expect(decision.model).toBe("gpt-5.4");
    expect(decision.reason).toContain("changeset");
  });

  it("applies skill override for ui_layout worker", () => {
    const decision = applyPolicy(makeCtx({ skill: "ui_layout" }), rules);
    expect(decision.provider).toBe("anthropic");
  });

  it("respects custom_overrides", () => {
    const decision = applyPolicy(
      makeCtx({ custom_overrides: { worker: "gemini/gemini-3.1-pro" } }),
      rules,
    );
    expect(decision.provider).toBe("gemini");
    expect(decision.model).toBe("gemini-3.1-pro");
  });
});
```

**Step 2: Run test — FAIL**

**Step 3: Implement policy.ts**

```typescript
// src/router/policy.ts
import type { RouteContext, RouteDecision } from "../types";

interface ModelRef {
  provider: string;
  model: string;
}

interface PolicyTable {
  role_preference: Record<string, { primary: ModelRef; economy: ModelRef; reason: string }>;
  skill_override: Record<string, Record<string, ModelRef & { reason: string }>>;
  round_downgrade: { threshold: number; downgrade_to: string; reason: string };
  changeset_upgrade: { threshold: number; upgrade_to: string; reason: string };
}

export function applyPolicy(ctx: RouteContext, policy: PolicyTable): RouteDecision {
  // Custom override takes highest priority
  const override = ctx.custom_overrides[ctx.agent_role];
  if (override && override.includes("/")) {
    const [provider, model] = override.split("/", 2);
    return {
      provider: provider!,
      model: model!,
      reason: "custom_override",
      experiment_id: null,
      fallback_chain: [],
    };
  }

  const rolePrefs = policy.role_preference[ctx.agent_role];
  if (!rolePrefs) {
    return {
      provider: "openai",
      model: "gpt-5.4",
      reason: "unknown_role_fallback",
      experiment_id: null,
      fallback_chain: [],
    };
  }

  // Start with cost preference
  let tier: "primary" | "economy" =
    ctx.cost_preference === "economy" ? "economy" : "primary";
  let reason = `${ctx.agent_role} ${tier}`;

  // Round downgrade
  if (ctx.round_number >= policy.round_downgrade.threshold && tier === "primary") {
    tier = "economy";
    reason = `round ${ctx.round_number} >= ${policy.round_downgrade.threshold}, downgraded`;
  }

  // Changeset upgrade
  if (ctx.changeset_size >= policy.changeset_upgrade.threshold && tier === "economy") {
    tier = "primary";
    reason = `changeset ${ctx.changeset_size} >= ${policy.changeset_upgrade.threshold}, upgraded`;
  }

  let chosen = rolePrefs[tier];

  // Skill override
  if (ctx.skill && policy.skill_override[ctx.skill]) {
    const skillOverride = policy.skill_override[ctx.skill]![ctx.agent_role];
    if (skillOverride) {
      chosen = skillOverride;
      reason = `skill_override: ${ctx.skill}`;
    }
  }

  return {
    provider: chosen.provider,
    model: chosen.model,
    reason,
    experiment_id: null,
    fallback_chain: [],
  };
}
```

**Step 4: Run test — PASS**

**Step 5: Commit**

```bash
git add src/router/policy.ts tests/router/policy.test.ts
git commit -m "feat: add Layer 2 policy table routing"
```

---

### Task 7: Layer 3 — Intelligence

**Files:**
- Create: `~/projects/god-code-api/src/router/intelligence.ts`
- Test: `~/projects/god-code-api/tests/router/intelligence.test.ts`

**Step 1: Write the test**

```typescript
// tests/router/intelligence.test.ts
import { describe, it, expect } from "vitest";
import { applyIntelligence } from "../../src/router/intelligence";
import type { RouteContext, RouteDecision, ModelScore } from "../../src/types";

function makeCtx(overrides: Partial<RouteContext> = {}): RouteContext {
  return {
    agent_role: "worker", skill: null, mode: "apply",
    round_number: 1, changeset_size: 2, estimated_tokens: 500,
    session_id: "s1", previous_models: [], quality_trend: [],
    provider_keys: ["openai", "anthropic", "gemini"],
    cost_preference: "balanced", custom_overrides: {},
    ...overrides,
  };
}

const baseDecision: RouteDecision = {
  provider: "openai", model: "gpt-5.4",
  reason: "policy", experiment_id: null, fallback_chain: [],
};

describe("applyIntelligence", () => {
  it("passes through when insufficient samples", () => {
    const scores: ModelScore[] = [{
      provider: "openai", model: "gpt-5.4", agent_role: "worker",
      skill: null, avg_quality: 4.0, p95_latency_ms: 1000,
      cost_per_1k_tokens: 0.01, sample_count: 5, last_updated: "",
    }];
    const result = applyIntelligence(makeCtx(), baseDecision, scores, 0);
    expect(result.provider).toBe("openai");
    expect(result.reason).toBe("policy");
  });

  it("switches model when quality trend declining", () => {
    const ctx = makeCtx({ quality_trend: [2.0, 2.5, 2.0] });
    const scores: ModelScore[] = [
      { provider: "openai", model: "gpt-5.4", agent_role: "worker",
        skill: null, avg_quality: 3.5, p95_latency_ms: 1000,
        cost_per_1k_tokens: 0.01, sample_count: 30, last_updated: "" },
      { provider: "anthropic", model: "claude-sonnet-4.6", agent_role: "worker",
        skill: null, avg_quality: 4.2, p95_latency_ms: 1200,
        cost_per_1k_tokens: 0.015, sample_count: 25, last_updated: "" },
    ];
    const result = applyIntelligence(ctx, baseDecision, scores, 0);
    expect(result.provider).toBe("anthropic");
    expect(result.reason).toContain("Quality declining");
  });

  it("does not switch when quality trend is fine", () => {
    const ctx = makeCtx({ quality_trend: [4.0, 4.5, 4.2] });
    const scores: ModelScore[] = [
      { provider: "openai", model: "gpt-5.4", agent_role: "worker",
        skill: null, avg_quality: 4.0, p95_latency_ms: 1000,
        cost_per_1k_tokens: 0.01, sample_count: 30, last_updated: "" },
      { provider: "anthropic", model: "claude-sonnet-4.6", agent_role: "worker",
        skill: null, avg_quality: 4.2, p95_latency_ms: 1200,
        cost_per_1k_tokens: 0.015, sample_count: 25, last_updated: "" },
    ];
    const result = applyIntelligence(ctx, baseDecision, scores, 0);
    expect(result.provider).toBe("openai");
  });

  it("injects A/B experiment at threshold", () => {
    const scores: ModelScore[] = [
      { provider: "openai", model: "gpt-5.4", agent_role: "worker",
        skill: null, avg_quality: 4.0, p95_latency_ms: 1000,
        cost_per_1k_tokens: 0.01, sample_count: 30, last_updated: "" },
      { provider: "anthropic", model: "claude-sonnet-4.6", agent_role: "worker",
        skill: null, avg_quality: 4.2, p95_latency_ms: 1200,
        cost_per_1k_tokens: 0.015, sample_count: 25, last_updated: "" },
    ];
    // Force A/B by passing abRandom < threshold
    const result = applyIntelligence(makeCtx(), baseDecision, scores, 0.02);
    expect(result.experiment_id).not.toBeNull();
    expect(result.provider).toBe("anthropic");
  });

  it("skips A/B when random above threshold", () => {
    const scores: ModelScore[] = [
      { provider: "openai", model: "gpt-5.4", agent_role: "worker",
        skill: null, avg_quality: 4.0, p95_latency_ms: 1000,
        cost_per_1k_tokens: 0.01, sample_count: 30, last_updated: "" },
      { provider: "anthropic", model: "claude-sonnet-4.6", agent_role: "worker",
        skill: null, avg_quality: 4.2, p95_latency_ms: 1200,
        cost_per_1k_tokens: 0.015, sample_count: 25, last_updated: "" },
    ];
    const result = applyIntelligence(makeCtx(), baseDecision, scores, 0.5);
    expect(result.experiment_id).toBeNull();
  });
});
```

**Step 2: Run test — FAIL**

**Step 3: Implement intelligence.ts**

```typescript
// src/router/intelligence.ts
import type { RouteContext, RouteDecision, ModelScore } from "../types";

function avg(nums: number[]): number {
  if (nums.length === 0) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

export function applyIntelligence(
  ctx: RouteContext,
  policyChoice: RouteDecision,
  scores: ModelScore[],
  abRandom: number,
  abThreshold: number = 0.05,
): RouteDecision {
  const relevant = scores.filter(
    (s) => s.agent_role === ctx.agent_role && s.sample_count >= 20,
  );
  if (relevant.length < 2) return policyChoice;

  // Quality trend declining → switch model
  if (ctx.quality_trend.length >= 3) {
    const recentAvg = avg(ctx.quality_trend.slice(-3));
    if (recentAvg < 3.0) {
      const best = relevant
        .filter((s) => s.provider !== policyChoice.provider)
        .sort((a, b) => b.avg_quality - a.avg_quality)[0];
      if (best && best.avg_quality > recentAvg + 0.5) {
        return {
          ...policyChoice,
          provider: best.provider,
          model: best.model,
          reason: `Quality declining (${recentAvg.toFixed(1)}), switching to ${best.model} (avg ${best.avg_quality.toFixed(1)})`,
        };
      }
    }
  }

  // A/B experiment injection
  if (abRandom < abThreshold && relevant.length >= 2) {
    const challenger = relevant.find(
      (s) => s.provider !== policyChoice.provider,
    );
    if (challenger) {
      return {
        provider: challenger.provider,
        model: challenger.model,
        reason: `A/B experiment: testing ${challenger.model} against ${policyChoice.model}`,
        experiment_id: crypto.randomUUID(),
        fallback_chain: [policyChoice.model],
      };
    }
  }

  return policyChoice;
}
```

**Step 4: Run test — PASS**

**Step 5: Commit**

```bash
git add src/router/intelligence.ts tests/router/intelligence.test.ts
git commit -m "feat: add Layer 3 intelligence routing"
```

---

### Task 8: Router engine (combines 3 layers)

**Files:**
- Create: `~/projects/god-code-api/src/router/engine.ts`
- Create: `~/projects/god-code-api/src/router/fallback.ts`
- Test: `~/projects/god-code-api/tests/router/engine.test.ts`

**Step 1: Write the test**

```typescript
// tests/router/engine.test.ts
import { describe, it, expect } from "vitest";
import { route } from "../../src/router/engine";
import type { RouteContext, ModelScore } from "../../src/types";
import rules from "../../routing-rules.default.json";

function makeCtx(overrides: Partial<RouteContext> = {}): RouteContext {
  return {
    agent_role: "worker", skill: null, mode: "apply",
    round_number: 1, changeset_size: 2, estimated_tokens: 500,
    session_id: "s1", previous_models: [], quality_trend: [],
    provider_keys: ["openai", "anthropic", "gemini"],
    cost_preference: "balanced", custom_overrides: {},
    ...overrides,
  };
}

describe("route", () => {
  it("routes worker to openai by default", () => {
    const decision = route(makeCtx(), rules, []);
    expect(decision.provider).toBe("openai");
    expect(decision.model).toBe("gpt-5.4");
  });

  it("routes reviewer to anthropic (not openai like worker)", () => {
    const ctx = makeCtx({
      agent_role: "reviewer",
      previous_models: [{ role: "worker", provider: "openai", model: "gpt-5.4" }],
    });
    const decision = route(ctx, rules, []);
    expect(decision.provider).toBe("anthropic");
  });

  it("forces openai for sprite generation even if reviewer", () => {
    const ctx = makeCtx({
      agent_role: "reviewer",
      tool_requested: "generate_sprite",
      previous_models: [{ role: "worker", provider: "openai", model: "gpt-5.4" }],
    });
    const decision = route(ctx, rules, []);
    expect(decision.provider).toBe("openai");
  });

  it("falls back when primary provider has no key", () => {
    const ctx = makeCtx({ provider_keys: ["gemini"] });
    const decision = route(ctx, rules, []);
    // Worker default is openai, but no key → should find alternative
    expect(decision.provider).toBe("gemini");
  });

  it("includes fallback chain", () => {
    const decision = route(makeCtx(), rules, []);
    expect(decision.fallback_chain.length).toBeGreaterThan(0);
  });
});
```

**Step 2: Run test — FAIL**

**Step 3: Implement fallback.ts**

```typescript
// src/router/fallback.ts
import type { RouteContext, RouteDecision } from "../types";

const PROVIDER_MODELS: Record<string, Record<string, string>> = {
  openai: { default: "gpt-5.4", planner: "gpt-5.4", worker: "gpt-5.4", reviewer: "gpt-5.4" },
  anthropic: { default: "claude-sonnet-4.6", planner: "claude-sonnet-4.6", worker: "claude-sonnet-4.6", reviewer: "claude-sonnet-4.6" },
  gemini: { default: "gemini-3.1-flash", planner: "gemini-3.1-flash", worker: "gemini-3.1-pro", reviewer: "gemini-3.1-pro" },
  xai: { default: "grok-4", planner: "grok-4", worker: "grok-4", reviewer: "grok-4" },
};

export function buildFallbackChain(
  ctx: RouteContext,
  primary: RouteDecision,
): string[] {
  const workerProvider = ctx.previous_models.find((m) => m.role === "worker")?.provider;

  return Object.entries(PROVIDER_MODELS)
    .filter(([provider]) => {
      if (provider === primary.provider) return false;
      if (!ctx.provider_keys.includes(provider)) return false;
      if (ctx.agent_role === "reviewer" && provider === workerProvider) return false;
      return true;
    })
    .map(([provider, models]) => {
      const model = models[ctx.agent_role] ?? models["default"]!;
      return `${provider}/${model}`;
    });
}

export function findFirstAvailable(
  ctx: RouteContext,
  policy: any,
): RouteDecision | null {
  const role = ctx.agent_role;
  const prefs = policy.role_preference[role];
  if (!prefs) return null;

  for (const tier of ["primary", "economy"] as const) {
    const ref = prefs[tier];
    if (ref && ctx.provider_keys.includes(ref.provider)) {
      return {
        provider: ref.provider,
        model: ref.model,
        reason: `${role} ${tier} (available)`,
        experiment_id: null,
        fallback_chain: [],
      };
    }
  }

  // Last resort: any provider with a key
  for (const [provider, models] of Object.entries(PROVIDER_MODELS)) {
    if (ctx.provider_keys.includes(provider)) {
      const model = (models as Record<string, string>)[role] ?? (models as Record<string, string>)["default"]!;
      return {
        provider,
        model,
        reason: `last_resort: ${provider}`,
        experiment_id: null,
        fallback_chain: [],
      };
    }
  }

  return null;
}
```

**Step 4: Implement engine.ts**

```typescript
// src/router/engine.ts
import type { RouteContext, RouteDecision, ModelScore } from "../types";
import { applyConstraints } from "./constraints";
import { applyPolicy } from "./policy";
import { applyIntelligence } from "./intelligence";
import { buildFallbackChain, findFirstAvailable } from "./fallback";

export function route(
  ctx: RouteContext,
  policy: any,
  scores: ModelScore[],
  abRandom: number = Math.random(),
  abThreshold: number = 0.05,
): RouteDecision {
  // Layer 2: Policy baseline
  let decision = applyPolicy(ctx, policy);

  // Layer 1: Constraints check
  const constraint = applyConstraints(ctx, decision);

  if (constraint.forced) {
    return {
      ...decision,
      ...constraint.forced,
      reason: constraint.forced.reason ?? decision.reason,
      fallback_chain: buildFallbackChain(ctx, { ...decision, ...constraint.forced } as RouteDecision),
    };
  }

  if (constraint.blocked) {
    // Policy choice blocked → find alternative
    const alt = findFirstAvailable(ctx, policy);
    if (!alt) {
      return {
        provider: "none",
        model: "none",
        reason: `All providers blocked: ${constraint.reason}`,
        experiment_id: null,
        fallback_chain: [],
      };
    }
    decision = alt;

    // Re-check constraints on alternative
    const recheck = applyConstraints(ctx, decision);
    if (recheck.blocked) {
      return {
        provider: "none",
        model: "none",
        reason: `No valid provider after constraint recheck`,
        experiment_id: null,
        fallback_chain: [],
      };
    }
  }

  // Layer 3: Intelligence adjustment
  decision = applyIntelligence(ctx, decision, scores, abRandom, abThreshold);

  // Build fallback chain
  decision.fallback_chain = buildFallbackChain(ctx, decision);

  return decision;
}
```

**Step 5: Run test — PASS**

```bash
npx vitest run tests/router/
```

**Step 6: Commit**

```bash
git add src/router/ tests/router/
git commit -m "feat: add router engine with 3-layer routing"
```

---

## Phase 3: Provider Dispatch

### Task 9: Provider adapters + dispatch

**Files:**
- Create: `~/projects/god-code-api/src/providers/dispatch.ts`
- Create: `~/projects/god-code-api/src/providers/openai.ts`
- Create: `~/projects/god-code-api/src/providers/anthropic.ts`
- Create: `~/projects/god-code-api/src/providers/gemini.ts`
- Create: `~/projects/god-code-api/src/providers/xai.ts`
- Test: `~/projects/god-code-api/tests/providers/dispatch.test.ts`

This task covers the format conversion layer. Each adapter transforms OrchestrateRequest into the provider's native format, calls the API, and normalizes the response back.

**Step 1: Write test for dispatch routing logic (no real API calls)**

```typescript
// tests/providers/dispatch.test.ts
import { describe, it, expect } from "vitest";
import { buildProviderRequest, normalizeResponse, providerEndpoint } from "../../src/providers/dispatch";

describe("providerEndpoint", () => {
  it("returns openai chat completions url", () => {
    expect(providerEndpoint("openai")).toBe("https://api.openai.com/v1/chat/completions");
  });
  it("returns anthropic messages url", () => {
    expect(providerEndpoint("anthropic")).toBe("https://api.anthropic.com/v1/messages");
  });
  it("returns gemini openai-compat url", () => {
    expect(providerEndpoint("gemini")).toBe(
      "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    );
  });
  it("returns xai url", () => {
    expect(providerEndpoint("xai")).toBe("https://api.x.ai/v1/chat/completions");
  });
});

describe("buildProviderRequest", () => {
  const messages = [{ role: "user" as const, content: "hello" }];

  it("builds openai request body", () => {
    const body = buildProviderRequest("openai", "gpt-5.4", messages);
    expect(body.model).toBe("gpt-5.4");
    expect(body.messages).toEqual(messages);
  });

  it("builds anthropic request with role conversion", () => {
    const body = buildProviderRequest("anthropic", "claude-sonnet-4.6", messages);
    expect(body.model).toBe("claude-sonnet-4.6");
    expect(body.max_tokens).toBeDefined();
  });
});

describe("normalizeResponse", () => {
  it("normalizes openai response", () => {
    const raw = {
      choices: [{ message: { role: "assistant", content: "hi" } }],
      usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
    };
    const result = normalizeResponse("openai", raw);
    expect(result.choices[0].message.content).toBe("hi");
    expect(result.usage.total_tokens).toBe(15);
  });

  it("normalizes anthropic response", () => {
    const raw = {
      content: [{ type: "text", text: "hi" }],
      usage: { input_tokens: 10, output_tokens: 5 },
    };
    const result = normalizeResponse("anthropic", raw);
    expect(result.choices[0].message.content).toBe("hi");
    expect(result.usage.prompt_tokens).toBe(10);
    expect(result.usage.completion_tokens).toBe(5);
  });
});
```

**Step 2: Run test — FAIL**

**Step 3: Implement provider files**

Each adapter file exports `endpoint`, `buildRequest`, `buildHeaders`, `normalizeResponse`. Dispatch.ts delegates based on provider name. Full implementation in the execution phase — the structure follows the test expectations above.

**Step 4: Run test — PASS**

**Step 5: Commit**

```bash
git add src/providers/ tests/providers/
git commit -m "feat: add provider adapters and dispatch layer"
```

---

## Phase 4: Session Durable Object

### Task 10: Session DO implementation

**Files:**
- Create: `~/projects/god-code-api/src/session/durable_object.ts`
- Test: `~/projects/god-code-api/tests/session/durable_object.test.ts`

**Step 1: Write the test**

```typescript
// tests/session/durable_object.test.ts
import { describe, it, expect } from "vitest";
import {
  newSessionState,
  recordRoute,
  recordQuality,
  getRouteContext,
  updateUsage,
} from "../../src/session/durable_object";
import type { RouteRecord, SessionState } from "../../src/types";

describe("session state", () => {
  it("newSessionState creates empty state", () => {
    const state = newSessionState("s1");
    expect(state.session_id).toBe("s1");
    expect(state.route_history).toHaveLength(0);
    expect(state.quality_window).toHaveLength(0);
    expect(state.usage.total_requests).toBe(0);
  });

  it("recordRoute appends to history and caps at 50", () => {
    let state = newSessionState("s1");
    for (let i = 0; i < 55; i++) {
      state = recordRoute(state, {
        request_id: `r${i}`, timestamp: "2026-04-04", agent_role: "worker",
        skill: null, round_number: 1, provider: "openai", model: "gpt-5.4",
        latency_ms: 100, tokens: 500, quality_score: null,
      });
    }
    expect(state.route_history).toHaveLength(50);
    expect(state.route_history[0]!.request_id).toBe("r5");
  });

  it("recordQuality updates window and backfills route", () => {
    let state = newSessionState("s1");
    state = recordRoute(state, {
      request_id: "r1", timestamp: "2026-04-04", agent_role: "worker",
      skill: null, round_number: 1, provider: "openai", model: "gpt-5.4",
      latency_ms: 100, tokens: 500, quality_score: null,
    });
    state = recordQuality(state, "r1", 4.2);
    expect(state.quality_window).toEqual([4.2]);
    expect(state.route_history[0]!.quality_score).toBe(4.2);
  });

  it("quality_window caps at 10", () => {
    let state = newSessionState("s1");
    for (let i = 0; i < 12; i++) {
      state = recordQuality(state, `r${i}`, 3.0 + i * 0.1);
    }
    expect(state.quality_window).toHaveLength(10);
  });

  it("getRouteContext returns last worker provider", () => {
    let state = newSessionState("s1");
    state = recordRoute(state, {
      request_id: "r1", timestamp: "2026-04-04", agent_role: "worker",
      skill: null, round_number: 1, provider: "openai", model: "gpt-5.4",
      latency_ms: 100, tokens: 500, quality_score: null,
    });
    const ctx = getRouteContext(state, "reviewer");
    expect(ctx.last_worker_provider).toBe("openai");
    expect(ctx.previous_models).toHaveLength(1);
  });

  it("updateUsage tracks per-provider costs", () => {
    let state = newSessionState("s1");
    state = updateUsage(state, "openai", "gpt-5.4", 1000);
    state = updateUsage(state, "anthropic", "claude-sonnet-4.6", 500);
    state = updateUsage(state, "openai", "gpt-5.4", 200);
    expect(state.usage.total_requests).toBe(3);
    expect(state.usage.by_provider["openai"]!.requests).toBe(2);
    expect(state.usage.by_provider["anthropic"]!.requests).toBe(1);
  });
});
```

**Step 2: Run test — FAIL**

**Step 3: Implement pure functions (testable without DO runtime)**

The DO class itself wraps these pure functions with storage read/write. The pure functions are unit-testable without Cloudflare runtime.

```typescript
// src/session/durable_object.ts
import type { SessionState, RouteRecord } from "../types";

export function newSessionState(session_id: string): SessionState {
  return {
    session_id,
    created_at: new Date().toISOString(),
    last_active: new Date().toISOString(),
    route_history: [],
    quality_window: [],
    quality_alerts: 0,
    experiment_assignments: {},
    user_config: {
      available_providers: [],
      cost_preference: "balanced",
      custom_overrides: {},
    },
    usage: {
      total_requests: 0,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      estimated_cost_usd: 0,
      by_provider: {},
    },
  };
}

export function recordRoute(state: SessionState, record: RouteRecord): SessionState {
  const history = [...state.route_history, record];
  return {
    ...state,
    route_history: history.length > 50 ? history.slice(-50) : history,
    last_active: new Date().toISOString(),
  };
}

export function recordQuality(
  state: SessionState,
  request_id: string,
  overall: number,
): SessionState {
  const route_history = state.route_history.map((r) =>
    r.request_id === request_id ? { ...r, quality_score: overall } : r,
  );
  const quality_window = [...state.quality_window, overall];
  return {
    ...state,
    route_history,
    quality_window: quality_window.length > 10 ? quality_window.slice(-10) : quality_window,
    last_active: new Date().toISOString(),
  };
}

export interface RouteContextResponse {
  previous_models: { role: string; provider: string; model: string }[];
  last_worker_provider: string | null;
  quality_trend: number[];
  inferred_round: number;
  available_providers: string[];
  cost_preference: string;
  custom_overrides: Record<string, string>;
  total_cost: number;
}

export function getRouteContext(
  state: SessionState,
  agent_role: string,
): RouteContextResponse {
  const worker_providers = state.route_history
    .filter((r) => r.agent_role === "worker")
    .map((r) => r.provider);

  let round_count = 0;
  for (let i = state.route_history.length - 1; i >= 0; i--) {
    if (state.route_history[i]!.agent_role === agent_role) {
      round_count++;
    } else {
      break;
    }
  }

  return {
    previous_models: state.route_history.slice(-10).map((r) => ({
      role: r.agent_role,
      provider: r.provider,
      model: r.model,
    })),
    last_worker_provider: worker_providers.at(-1) ?? null,
    quality_trend: state.quality_window.slice(-5),
    inferred_round: round_count + 1,
    available_providers: state.user_config.available_providers,
    cost_preference: state.user_config.cost_preference,
    custom_overrides: state.user_config.custom_overrides,
    total_cost: state.usage.estimated_cost_usd,
  };
}

const COST_PER_1K: Record<string, number> = {
  "gpt-5.4": 0.01,
  "gpt-5.4-mini": 0.003,
  "claude-sonnet-4.6": 0.015,
  "gemini-3.1-flash": 0.001,
  "gemini-3.1-pro": 0.005,
  "grok-4": 0.01,
};

export function updateUsage(
  state: SessionState,
  provider: string,
  model: string,
  tokens: number,
): SessionState {
  const cost = (tokens / 1000) * (COST_PER_1K[model] ?? 0.01);
  const provEntry = state.usage.by_provider[provider] ?? { requests: 0, tokens: 0, cost: 0 };

  return {
    ...state,
    usage: {
      ...state.usage,
      total_requests: state.usage.total_requests + 1,
      total_prompt_tokens: state.usage.total_prompt_tokens + tokens,
      estimated_cost_usd: state.usage.estimated_cost_usd + cost,
      by_provider: {
        ...state.usage.by_provider,
        [provider]: {
          requests: provEntry.requests + 1,
          tokens: provEntry.tokens + tokens,
          cost: provEntry.cost + cost,
        },
      },
    },
    last_active: new Date().toISOString(),
  };
}

// DO class wrapper — uses the pure functions above with DurableObject storage.
// Implemented when deployed, tested via integration tests with miniflare.
```

**Step 4: Run test — PASS**

**Step 5: Commit**

```bash
git add src/session/ tests/session/
git commit -m "feat: add session state management (pure functions)"
```

---

## Phase 5: Quality Scorer

### Task 11: Sampler + Compressor

**Files:**
- Create: `~/projects/god-code-api/src/scoring/sampler.ts`
- Create: `~/projects/god-code-api/src/scoring/compressor.ts`
- Test: `~/projects/god-code-api/tests/scoring/sampler.test.ts`
- Test: `~/projects/god-code-api/tests/scoring/compressor.test.ts`

Tests cover: shouldScore() returns correct sampling decision based on conditions; compressForScoring() truncates messages correctly and preserves tool call names.

**Commit:** `feat: add quality scoring sampler and compressor`

---

### Task 12: Scoring pipeline + alerts

**Files:**
- Create: `~/projects/god-code-api/src/scoring/pipeline.ts`
- Create: `~/projects/god-code-api/src/scoring/alerts.ts`
- Test: `~/projects/god-code-api/tests/scoring/pipeline.test.ts`

Tests cover: buildScoringPrompt() produces valid prompt; parseScoreResponse() handles valid/invalid JSON; checkQualityAlerts() fires on drop > 1.5 and on hallucination flag.

**Commit:** `feat: add quality scoring pipeline and alerts`

---

## Phase 6: Worker Entry + Integration

### Task 13: Worker index.ts — HTTP routing + orchestrate endpoint

**Files:**
- Create: `~/projects/god-code-api/src/index.ts`
- Create: `~/projects/god-code-api/src/auth/guard.ts`
- Test: `~/projects/god-code-api/tests/integration/orchestrate.test.ts`

This task wires everything together:
- `POST /v1/orchestrate` → parse request → auth guard → session DO route-context → router engine → provider dispatch → record route → async quality score → return response
- `GET /v1/health` → return provider status
- `GET /v1/models` → return available models + quality scores from D1

Integration test uses mocked provider responses (no real API calls).

**Commit:** `feat: add worker entry point and orchestrate endpoint`

---

### Task 14: Streaming support

**Files:**
- Modify: `~/projects/god-code-api/src/index.ts`
- Modify: `~/projects/god-code-api/src/providers/dispatch.ts`
- Test: `~/projects/god-code-api/tests/integration/streaming.test.ts`

Add SSE streaming path: when `stream: true`, proxy the provider's SSE stream and append routing metadata chunk before `[DONE]`.

**Commit:** `feat: add SSE streaming support`

---

## Phase 7: god-code Client Adaptation

### Task 15: Add backend config fields

**Files:**
- Modify: `~/projects/god-code/godot_agent/runtime/config.py`
- Test: `~/projects/god-code/tests/runtime/test_config.py`

**Step 1: Write the test**

```python
# Append to tests/runtime/test_config.py
def test_backend_config_defaults():
    cfg = AgentConfig()
    assert cfg.backend_url == ""
    assert cfg.backend_cost_preference == "balanced"
    assert cfg.backend_force_provider == ""
    assert cfg.backend_force_model == ""
    assert cfg.backend_provider_keys == {}

def test_backend_config_from_dict():
    cfg = AgentConfig(
        backend_url="https://api.god-code.dev",
        backend_cost_preference="quality",
        backend_provider_keys={"openai": "sk-xxx"},
    )
    assert cfg.backend_url == "https://api.god-code.dev"
    assert cfg.backend_provider_keys["openai"] == "sk-xxx"
```

**Step 2: Run test — FAIL**

```bash
cd ~/projects/god-code && pytest tests/runtime/test_config.py -v -k "backend"
```

**Step 3: Add fields to config.py**

Add to the `AgentConfig` dataclass:

```python
backend_url: str = ""
backend_cost_preference: str = "balanced"
backend_force_provider: str = ""
backend_force_model: str = ""
backend_provider_keys: dict[str, str] = field(default_factory=dict)
```

**Step 4: Run test — PASS**

**Step 5: Run full test suite to verify no regressions**

```bash
pytest tests/ -v
```

**Step 6: Commit**

```bash
git add godot_agent/runtime/config.py tests/runtime/test_config.py
git commit -m "feat: add backend orchestration config fields"
```

---

### Task 16: Dual-path LLMClient

**Files:**
- Modify: `~/projects/god-code/godot_agent/llm/client.py`
- Test: `~/projects/god-code/tests/llm/test_client.py`

**Step 1: Write the test**

```python
# Append to tests/llm/test_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_chat_direct_when_no_backend():
    """When backend_url is empty, chat() uses direct path."""
    config = LLMConfig(
        provider="openai", model="gpt-5.4",
        api_key="sk-test", base_url="https://api.openai.com/v1",
    )
    client = LLMClient(config)
    assert client._use_backend is False

@pytest.mark.asyncio
async def test_chat_backend_when_url_set():
    """When backend_url is set, chat() with metadata uses backend path."""
    config = LLMConfig(
        provider="openai", model="gpt-5.4",
        api_key="sk-test", base_url="https://api.openai.com/v1",
        backend_url="https://api.god-code.dev",
    )
    client = LLMClient(config)
    assert client._use_backend is True

@pytest.mark.asyncio
async def test_chat_ignores_metadata_without_backend():
    """route_metadata is ignored when no backend configured."""
    config = LLMConfig(
        provider="openai", model="gpt-5.4",
        api_key="sk-test", base_url="https://api.openai.com/v1",
    )
    client = LLMClient(config)
    # Should not raise even with metadata
    # (actual API call mocked in existing tests)
```

**Step 2: Run test — FAIL (backend_url not in LLMConfig)**

**Step 3: Add backend_url to LLMConfig, add dual-path to LLMClient**

Add `backend_url: str = ""` to `LLMConfig` in `types.py`.

Modify `LLMClient.__init__` and `chat()` to support dual path as specified in the design doc.

**Step 4: Run test — PASS**

**Step 5: Run full test suite**

```bash
pytest tests/ -v
```

**Step 6: Commit**

```bash
git add godot_agent/llm/client.py godot_agent/llm/types.py tests/llm/test_client.py
git commit -m "feat: add dual-path LLMClient (direct + backend)"
```

---

### Task 17: Engine metadata injection

**Files:**
- Modify: `~/projects/god-code/godot_agent/runtime/engine.py`
- Test: `~/projects/god-code/tests/runtime/test_engine.py`

**Step 1: Write the test**

```python
# Append to tests/runtime/test_engine.py
def test_build_route_metadata():
    """Engine builds route metadata dict with correct fields."""
    # Use existing engine fixture/mock
    metadata = {
        "session_id": "test-session",
        "agent_role": "worker",
        "skill": "collision",
        "mode": "apply",
        "round_number": 1,
        "changeset_size": 3,
        "estimated_tokens": 1000,
    }
    assert "session_id" in metadata
    assert "agent_role" in metadata
    assert metadata["agent_role"] in ("planner", "worker", "reviewer", "playtest_analyst")
```

**Step 2: Add metadata building to engine's _call_model method**

Pass `route_metadata=` kwarg to `self.client.chat()`.

**Step 3: Run full test suite — PASS**

**Step 4: Commit**

```bash
git add godot_agent/runtime/engine.py tests/runtime/test_engine.py
git commit -m "feat: inject route metadata from engine to LLMClient"
```

---

## Phase 8: Deploy + Smoke Test

### Task 18: Deploy god-code-api to Cloudflare

**Step 1: Create D1 database**

```bash
cd ~/projects/god-code-api
npx wrangler d1 create god-code-api
# Update wrangler.toml with real database_id
```

**Step 2: Run migrations**

```bash
npx wrangler d1 execute god-code-api --file=schema/001_init.sql
npx wrangler d1 execute god-code-api --file=schema/002_quality_scores.sql
```

**Step 3: Create KV namespace**

```bash
npx wrangler kv namespace create ROUTING_KV
# Update wrangler.toml with real KV id
```

**Step 4: Deploy**

```bash
npx wrangler deploy
```

**Step 5: Smoke test health endpoint**

```bash
curl https://god-code-api.<your>.workers.dev/v1/health
# Expected: {"status":"ok","providers":["openai","anthropic","gemini","xai"]}
```

**Step 6: Commit wrangler.toml with real IDs**

```bash
git add wrangler.toml
git commit -m "chore: add production D1 and KV bindings"
```

---

### Task 19: Configure god-code and end-to-end test

**Step 1: Set backend config**

```bash
cd ~/projects/god-code
god-code set backend_url https://god-code-api.<your>.workers.dev
god-code set backend_provider_keys.openai sk-xxx
god-code set backend_provider_keys.anthropic sk-ant-xxx
```

**Step 2: Run a simple ask command**

```bash
god-code ask "list the files in this project" --project .
```

**Step 3: Verify routing in TUI output**

Expected: TUI shows `routing: gpt-5.4 (worker primary) XXXms`

**Step 4: Verify D1 has route_decisions entry**

```bash
cd ~/projects/god-code-api
npx wrangler d1 execute god-code-api --command "SELECT * FROM route_decisions LIMIT 5"
```

**Step 5: Commit any config adjustments**

---

## Summary

| Phase | Tasks | Est. Lines | Key Deliverable |
|-------|-------|-----------|----------------|
| 1. Scaffold + Types | 1-4 | ~350 | Project init, types, schema, routing rules |
| 2. Router Engine | 5-8 | ~300 | 3-layer routing (constraints → policy → intelligence) |
| 3. Provider Dispatch | 9 | ~200 | OpenAI/Anthropic/Gemini/xAI adapters |
| 4. Session DO | 10 | ~200 | Session state pure functions |
| 5. Quality Scorer | 11-12 | ~250 | Sampler, compressor, pipeline, alerts |
| 6. Integration | 13-14 | ~250 | Worker entry, orchestrate endpoint, streaming |
| 7. god-code Adaptation | 15-17 | ~120 | Config fields, dual-path client, engine metadata |
| 8. Deploy | 18-19 | ~0 | D1/KV setup, deploy, smoke test |
| **Total** | **19 tasks** | **~1670** | |

### Dependencies

```
Phase 1 (scaffold) → Phase 2 (router) → Phase 6 (integration)
Phase 1 (scaffold) → Phase 3 (providers) → Phase 6 (integration)
Phase 1 (scaffold) → Phase 4 (session) → Phase 6 (integration)
Phase 1 (scaffold) → Phase 5 (scoring) → Phase 6 (integration)
Phase 6 (integration) → Phase 8 (deploy)
Phase 7 (god-code) can run in parallel with Phases 2-6
```

Phases 2, 3, 4, 5 are all independent of each other and can be developed in parallel after Phase 1.

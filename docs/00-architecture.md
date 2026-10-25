# 00 — Architecture

Author: founding CTO. Status: v0.1 (pre-MVP). Units: **millimetres, integers** everywhere in the domain. Angles in degrees. Never floats for dimensions in the domain layer.

---

## 1. Architectural principles (non-negotiable)

These exist because each one prevents a specific failure mode I have seen in "AI → CAD" products.

1. **The PartGraph is the source of truth — not SketchUp, not the LLM.**
   SketchUp geometry is a *projection* of the PartGraph. Cut list, BOM, drawings and CNC data are computed from the PartGraph, never reverse-engineered from SketchUp faces. Reading manufacturing data back out of a mesh is lossy (no edge-banding, no grain, no hole semantics) and slow.

2. **AI proposes, rules dispose, code builds.**
   LLMs output only a `FurnitureSpec` (design *intent*: type, overall size, layout, materials, hardware families). A deterministic **Rule Engine** validates and normalises it. A deterministic **Parametric Generator** (pure Python, no network, no randomness) turns it into parts. Same `spec + rulepack_version + generator_version` ⇒ byte-identical PartGraph. This makes the system testable, cacheable and explainable to a workshop.

3. **Human-in-the-loop at the cheapest point.**
   A single image cannot determine absolute scale. Dimensions come with confidence scores; the user confirms/edits the Spec in a review UI *before* any expensive geometry or drawings are produced. Editing a number in a form is 1000× cheaper than editing a SketchUp model.

4. **Immutable versions.** `DesignVersion` = frozen spec + frozen PartGraph + artifacts. Any edit creates a new version. Workshops need "what exactly did we cut on 12 March".

5. **SketchUp is a scarce, slow, stateful resource — isolate it behind a queue.**
   SketchUp is a desktop GUI app (Windows/macOS), not a server. It lives in a separate *Geometry Farm*, consumed only through the `GeometryEngine` port. The rest of the platform must keep working (cut list, drawings, 3D web preview) when every SketchUp node is down.

6. **Pluggable engines behind ports.** `VisionModel`, `GeometryEngine`, `DrawingRenderer`, `CncPostProcessor`, `Nester` are interfaces (hexagonal architecture). This is what lets us swap GPT ↔ Claude, SketchUp MCP ↔ SketchUp C SDK, DXF ↔ Homag MPR without touching the domain.

7. **Boring infrastructure.** One Postgres (Supabase), one Redis, one Python codebase for all backend logic, one Next.js app. A solo founder cannot operate Kubernetes, Kafka and five languages.

---

## 2. High-level architecture

```
                                   ┌───────────────────────────────┐
                                   │            Clerk              │
                                   │  users · orgs · JWT (RS256)   │
                                   └──────────────┬────────────────┘
                                                  │ JWT (also accepted by Supabase as 3rd-party auth)
┌────────────────────────────┐   HTTPS/JSON      ▼
│  apps/web  (Next.js 15)    │──────────────►┌──────────────────────────────┐
│  App Router · shadcn/ui    │               │ apps/api  (FastAPI)          │
│  three.js viewer (glTF)    │◄── SSE ───────│  REST /v1 · SSE /events      │
│  Spec Review form          │               │  authz · validation · orchestration entry
└──────────┬─────────────────┘               └───┬──────────────┬───────────┘
           │ signed upload URL                    │ SQL          │ enqueue (Celery)
           ▼                                      ▼              ▼
┌────────────────────────────┐   ┌────────────────────────┐  ┌─────────────────────┐
│ Supabase Storage           │   │ Supabase Postgres      │  │ Redis               │
│  images/ skp/ pdf/ dxf/    │   │  domain tables · RLS   │  │  Celery broker      │
│  gltf/ zip/                │   │  outbox · realtime     │  │  results · pub/sub  │
└────────────▲───────────────┘   └───────────▲────────────┘  └──┬──────┬──────┬───┘
             │                               │                  │      │      │
             │          ┌────────────────────┴──────────┐       │      │      │
             │          │                               │       │      │      │
   ┌─────────┴──────────┴──┐   ┌────────────────────────┴──┐    │      │      │
   │ worker-ai  (Celery)   │◄──┤ queue: ai                 │◄───┘      │      │
   │ Stage 1 Perception    │   └───────────────────────────┘           │      │
   │ Stage 2 Spec drafting │──► OpenAI Responses API (GPT-5 vision)    │      │
   └───────────────────────┘──► Anthropic Messages API (Claude vision) │      │
   ┌───────────────────────┐   ┌───────────────────────────┐           │      │
   │ worker-core (Celery)  │◄──┤ queue: core               │◄──────────┘
   │ Stage 3 Parametric    │   └───────────────────────────┘
   │ Stage 5 Cutlist/BOM   │──► inserts geometry_jobs row (status=queued)
   │ Nesting · Drawings    │
   │ CNC post · glTF       │
   └───────────────────────┘

   ═══════════════════════════ GEOMETRY FARM (Windows VMs) ═══════════════════════
   ┌──────────────────────────────────────────────────────────────────────┐
   │ apps/sketchup-agent (Python service, 1 job at a time)                │
   │   ├─ HTTPS long-poll  POST api/internal/geometry/claim  (node token) │──► api
   │   ├─ MCP client (stdio) ──► SketchUp MCP server (Python, FastMCP)    │
   │   │                            └─ TCP 127.0.0.1:9876 ──► SketchUp    │
   │   │                                 + designforge_bridge.rbz         │
   │   └─ PUT artifacts to signed Storage URLs from the claim ticket      │
   └──────────────────────────────────────────────────────────────────────┘
   N nodes, 1 SketchUp process each, auto-restart on crash.
```

Why the Geometry Farm is pull-based over HTTPS: nodes sit behind NAT on Windows VMs and hold **no database or Redis credentials** — only a scoped node token. The geometry queue is the `geometry_jobs` table claimed with `FOR UPDATE SKIP LOCKED` (see 02-api, internal API). No inbound ports, no public MCP endpoint (an exposed `eval_ruby` tool is remote code execution).

---

## 3. Service boundaries (bounded contexts → deployables)

| Bounded context | Responsibility | Owns tables | Deployable | Talks to |
|---|---|---|---|---|
| **Identity & Tenancy** | Clerk webhooks → orgs/members, plan, seat limits | `organizations`, `members` | api | Clerk |
| **Catalog** | Materials, sheet stock, edge bands, hardware, rule packs, price lists (per org overrides) | `materials`, `sheet_stock`, `edge_bands`, `hardware_catalog`, `rule_packs` | api + core lib | — |
| **Ingestion** | Signed uploads, EXIF strip, normalise to sRGB/≤2048px, perceptual hash dedupe, NSFW/irrelevance check | `source_images` | api + worker-ai | Storage |
| **Perception** (Stage 1) | Image → `ImageObservation` (category, visible features, proportion ratios, materials, style) | `analysis_runs`, `image_observations` | worker-ai | LLM providers |
| **Design Knowledge** (Stage 2) | Observations + priors + user anchors → `FurnitureSpec`; Rule Engine validation | `designs`, `design_versions`, `spec_issues` | worker-ai (draft) + core (rules) | — |
| **Parametric** (Stage 3) | `FurnitureSpec` → `PartGraph` (deterministic) | `part_graphs`, `parts`, `hardware_placements` | worker-core | — |
| **Geometry** (Stage 4) | `PartGraph` → SketchUp model, scenes, exports | `geometry_jobs`, `geometry_nodes` | sketchup-agent | SketchUp MCP |
| **Manufacturing** (Stage 5a) | Cut list, edge-band list, BOM, costing, nesting, CNC programs | `cutlist_items`, `bom_lines`, `nest_layouts` | worker-core | — |
| **Documentation** (Stage 5b) | Production drawings (PDF/DXF/SVG), assembly sheets, labels | `drawing_sets`, `drawing_sheets` | worker-core | — |
| **Delivery** | Artifacts registry, production package zip, share links | `artifacts`, `share_links` | api | Storage |
| **Orchestration** | Pipeline runs, step state, retries, events (outbox) | `pipeline_runs`, `pipeline_steps`, `domain_events` | api + all workers | Redis |
| **Billing & Usage** | Credits per stage, Stripe, quotas | `usage_events`, `credit_ledger` | api | Stripe |

Rule of thumb: **contexts share a database but never another context's tables.** They share *contracts* (`df_domain` Pydantic models). Cross-context calls go through a Python service interface in-process (same deployable) or a Celery task (different deployable). This is a modular monolith — splitting a context into its own service later is a mechanical change.

---

## 4. Deployment topology

| Unit | Runtime | Hosting (MVP) | Scale lever |
|---|---|---|---|
| web | Next.js 15, Node 22 | Vercel | edge/CDN |
| api | FastAPI + Uvicorn, Python 3.12 | Fly.io / Render (2× small) | horizontal |
| worker-ai | Celery, `-Q ai`, concurrency 8 (I/O bound, use `--pool=threads` or gevent) | same host family as api | horizontal; bounded by LLM rate limits |
| worker-core | Celery, `-Q core`, prefork, concurrency = vCPU | Fly/Render | horizontal (CPU) |
| sketchup-agent | Windows Server 2022 VM, SketchUp Pro 2025/2026, auto-logon interactive session | AWS EC2 `g4dn.xlarge` Windows (or Paperspace / Shadow-style desktops); 1 node in MVP | add nodes; 1 job/node |
| Postgres + Storage + Realtime | Supabase Pro | Supabase | compute add-on |
| Redis | Managed Redis with persistence (Redis Cloud / Fly Redis / ElastiCache) | — | **not** Upstash serverless: Celery's polling/ack traffic is a poor fit for per-command billing |
| Observability | Sentry (web/api/workers), Logfire or OpenTelemetry → Grafana Cloud, Langfuse for LLM traces | SaaS | — |

Environments: `local` (docker-compose: postgres via `supabase start`, redis, api, workers; SketchUp agent runs on your own Windows/Mac machine pointing at local Redis via tunnel), `staging`, `prod`.

---

## 5. Event flow — "Generate design from images"

### 5.1 State machine of a `pipeline_run`

```
created
  └─► ingesting ──► perceiving ──► drafting_spec ──► awaiting_review ──(user approves)──►
      generating_parts ──► ┬─► building_geometry ──┐
                           ├─► computing_mfg ──────┼─► packaging ──► completed
                           └─► rendering_drawings ─┘
  any step ──► failed (retryable | terminal)      user ──► cancelled
```

Stage 4 (SketchUp) runs **in parallel** with Stage 5 because both consume the PartGraph. The package is ready as soon as all three complete; if SketchUp fails, the user still gets drawings + cut list + glTF, and the `.skp` is retried (degraded mode).

### 5.2 Sequence

```
User        web             api                 Postgres          Redis/Celery          workers
 │ upload    │                │                     │                  │                    │
 │──images──►│ POST /designs  │                     │                  │                    │
 │           │───────────────►│ insert design,run   │                  │                    │
 │           │◄─ upload URLs ─│────────────────────►│                  │                    │
 │           │ PUT to Storage (direct, signed)       │                  │                    │
 │           │ POST /runs/{id}/start ──────────────►│ step=ingesting   │                    │
 │           │                │── chain(ingest→perceive→draft_spec) ──►│                    │
 │           │ GET /runs/{id}/events (SSE) ◄────────── outbox relay ◄──│◄── step updates ───│ worker-ai
 │           │                │                     │                  │                    │
 │  ◄── "Review spec" (awaiting_review, spec v1 + issues + confidence) │                    │
 │ edits     │ PATCH /versions/{v}/spec  (new draft version, re-validated synchronously)    │
 │ approve   │ POST /versions/{v}/approve ─────────►│                  │                    │
 │           │                │── chain(generate_parts) then group(build_geometry,         │
 │           │                │        compute_mfg, render_drawings) | chord(package) ──►  │ worker-core
 │           │                │                     │◄─ geometry_jobs claim (HTTPS long-poll) ─│ sketchup-agent
 │  ◄── progress events, then package.ready with artifact URLs ───────────────────────────│
```

### 5.3 Event catalogue (outbox → SSE + Supabase Realtime)

| Event | Payload (besides `run_id`, `design_id`, `version_id`, `ts`) |
|---|---|
| `run.step_started` / `run.step_completed` / `run.step_failed` | `step`, `attempt`, `error_code?` |
| `images.ingested` | `image_ids[]`, `rejected[]` |
| `perception.completed` | `observation_ids[]`, `category`, `confidence` |
| `spec.drafted` | `spec_hash`, `issues[]`, `low_confidence_fields[]` |
| `spec.approved` | `approved_by` |
| `partgraph.generated` | `part_count`, `hardware_count`, `graph_hash` |
| `geometry.completed` / `geometry.failed` | `artifact_ids[]`, `node_id`, `duration_ms` |
| `manufacturing.completed` | `sheet_count`, `yield_pct`, `cost_estimate` |
| `drawings.completed` | `sheet_count`, `artifact_ids[]` |
| `package.ready` | `zip_artifact_id` |

Implementation: every worker writes step state + an `domain_events` row **in the same transaction** (transactional outbox). A tiny relay (inside api, `LISTEN/NOTIFY` on insert) fans out to Redis pub/sub; the SSE endpoint subscribes per run. For the MVP you may skip the relay and let the web app subscribe to `pipeline_steps` via **Supabase Realtime** directly — fewer moving parts. The outbox is still written so V1 can add webhooks (ERP integrations) without changing workers.

### 5.4 Idempotency & retries

- Every Celery task takes `(run_id, step, attempt)` and is idempotent: it checks `pipeline_steps.status` and the content hash of its input before doing work.
- Outputs are content-addressed: `artifacts.sha256`, `part_graphs.graph_hash`. If an identical PartGraph has already been built into an `.skp` for this rulepack/bridge version, **reuse it** (cache hit = free, instant).
- Retry policy: LLM calls `autoretry_for=(RateLimit, Timeout)`, exponential backoff, max 4; geometry jobs max 2 then mark node unhealthy; deterministic steps (parametric, mfg) **never retry** on `ValidationError` — that's a bug, alert.

---

## 6. Monorepo structure

Tooling: **pnpm + Turborepo** for TypeScript, **uv workspaces** for Python, one root `Makefile` / `justfile` that wraps both. Contracts are generated from a single JSON Schema source so TS and Python can't drift.

```
designforge/
├── apps/
│   ├── web/                          # Next.js 15 (App Router), TS, Tailwind, shadcn/ui
│   │   ├── app/
│   │   │   ├── (marketing)/          # landing, pricing
│   │   │   ├── (app)/
│   │   │   │   ├── projects/[projectId]/
│   │   │   │   ├── designs/[designId]/
│   │   │   │   │   ├── page.tsx              # overview + run status
│   │   │   │   │   ├── review/page.tsx       # Spec Review (the money screen)
│   │   │   │   │   ├── model/page.tsx        # 3D viewer (glTF) + part inspector
│   │   │   │   │   ├── drawings/page.tsx     # PDF sheets viewer
│   │   │   │   │   └── production/page.tsx   # cut list, BOM, nesting, downloads
│   │   │   │   ├── catalog/                   # org materials, hardware, sheet stock
│   │   │   │   └── settings/
│   │   │   └── api/webhooks/clerk/route.ts    # (or handled in FastAPI — pick one: FastAPI)
│   │   ├── components/
│   │   │   ├── ui/                   # shadcn generated
│   │   │   ├── spec-review/          # DimensionField w/ confidence, LayoutEditor (sections/rows)
│   │   │   ├── viewer/               # three.js / @react-three/fiber, explode view, part picking
│   │   │   └── production/           # CutlistTable (TanStack Table), NestingPreview (SVG)
│   │   ├── lib/api-client.ts         # generated from OpenAPI (openapi-typescript + openapi-fetch)
│   │   └── lib/realtime.ts           # SSE hook
│   ├── api/                          # FastAPI
│   │   ├── src/df_api/
│   │   │   ├── main.py
│   │   │   ├── deps.py               # auth (Clerk JWKS), db session, tenancy
│   │   │   ├── routers/              # projects, designs, versions, runs, artifacts, catalog, webhooks
│   │   │   ├── services/             # application services (use cases) — thin, call domain
│   │   │   └── sse.py
│   │   └── tests/
│   ├── worker/                       # Celery app: queues ai, core (same image, different -Q)
│   │   └── src/df_worker/
│   │       ├── celery_app.py
│   │       ├── tasks/ingest.py perceive.py draft_spec.py parametric.py
│   │       │        manufacturing.py drawings.py package.py
│   │       └── orchestration.py      # build_chain(run) → canvas
│   └── sketchup-agent/               # runs on Windows geometry nodes
│       └── src/df_agent/
│           ├── main.py               # claim loop: long-poll api /internal/geometry/claim, 1 job at a time
│           ├── supervisor.py         # start/watch/restart SketchUp.exe, health heartbeat
│           └── uploader.py
├── python/                           # shared Python libraries (uv workspace members)
│   ├── df_domain/                    # Pydantic models, value objects, ports (Protocols). NO I/O.
│   ├── df_rules/                     # Rule Engine + rule packs (YAML) + validators
│   ├── df_parametric/                # generators per furniture family (pure functions)
│   ├── df_ai/                        # VisionModel adapters, prompts, schemas, ensembling, evals
│   ├── df_geometry/                  # GeometryEngine port + SketchUp MCP adapter + glTF engine
│   ├── df_manufacturing/             # cutlist, edge banding, BOM, costing, nesting, CNC posts
│   ├── df_drawings/                  # 2D projection, dimensioning, sheet layout, PDF/DXF/SVG
│   └── df_infra/                     # DB repositories (SQLAlchemy/asyncpg), storage, outbox, settings
├── packages/                         # shared TypeScript
│   ├── contracts/                    # generated + hand-written TS types (FurnitureSpec, DTOs, events)
│   ├── ui/                           # shared React components if a 2nd app appears (admin)
│   └── config/                       # eslint, tsconfig, tailwind preset
├── schemas/                          # ★ SOURCE OF TRUTH: JSON Schema 2020-12
│   ├── furniture-spec.schema.json    #   → TS via json-schema-to-typescript
│   ├── part-graph.schema.json        #   → Python via datamodel-code-generator (or hand-written Pydantic
│   └── events.schema.json            #     that exports schema, with a CI diff check — see 01-domain)
├── extensions/
│   └── sketchup-bridge/              # Ruby extension (.rbz): high-level build ops inside SketchUp
├── supabase/
│   ├── migrations/                   # SQL migrations (supabase db diff / push)
│   └── seed.sql                      # default materials, hardware, rule pack
├── evals/                            # golden image set + expected specs + scoring scripts
│   ├── datasets/wardrobes/…          # image + ground_truth.json (measured real furniture)
│   └── run_evals.py
├── infra/
│   ├── docker/                       # api.Dockerfile, worker.Dockerfile
│   ├── docker-compose.yml
│   ├── windows-node/                 # Packer template / PowerShell bootstrap for geometry nodes
│   └── fly/                          # fly.toml per app
├── docs/
├── .cursor/rules/                    # Cursor project rules (*.mdc)
├── turbo.json  pnpm-workspace.yaml  pyproject.toml (uv workspace)  justfile
└── .github/workflows/                # ci.yml (lint, typecheck, tests, schema drift), deploy-*.yml
```

### Dependency rules (enforced with `import-linter` in CI)

```
df_domain        ← depends on nothing (pydantic only)
df_rules         ← df_domain
df_parametric    ← df_domain, df_rules
df_manufacturing ← df_domain
df_drawings      ← df_domain
df_geometry      ← df_domain           (+ mcp SDK in adapter module only)
df_ai            ← df_domain           (+ openai, anthropic SDKs in adapter modules only)
df_infra         ← df_domain
apps/*           ← anything above
```

The domain never imports an SDK, a database driver or Celery.

# 06 — Roadmap, risks, and the solo-founder plan

## 1. Strategy in three sentences

1. **Wedge = custom furniture workshops**, not designers: they get a Pinterest photo from a client every day and lose hours turning it into a quote and a cut list. "Photo → quote + cut list in 10 minutes" is a measurable win they pay for.
2. **The deterministic core is the product; AI is the on-ramp.** Ship a *manual spec mode* first (type the dimensions, get drawings + cut list + SKP). That is useful on day 1 and becomes the ground truth AI is measured against.
3. **Go narrow and deep:** carcass furniture (wardrobes, cabinets, bookcases, sideboards) covers most of the volume for panel-based workshops. Chairs, sofas, curved or solid-wood joinery come much later or never.

## 2. Roadmap

### MVP — "Paid beta" (≈ 16 weeks, 3–5 design-partner workshops)

| Area | In | Out (explicitly) |
|---|---|---|
| Categories | wardrobe, base/wall/tall cabinet, bookcase, sideboard (carcass family) | desks, beds, chairs, kitchens as runs |
| Construction | gables-over-top, minifix+dowel, inset-groove back, plinth or legs, overlay doors, drawers on 1 slide family, hanging rail, adjustable shelves | inset fronts, sliding doors, lift-ups, mitred/solid-wood joinery |
| AI | single-model perception, dimension solver with anchors, layout mapper, rules + one-click fixes, Spec Review | ensembles, SAM rectification, chat editing |
| 3D | glTF preview (web), SketchUp `.skp` + scenes via MCP on **1** Windows node | OBJ/STL/DXF from SketchUp (glTF engine provides STL/OBJ) |
| Manufacturing | cut list (CSV/XLSX), edge banding, BOM + cost, guillotine nesting, generic layered DXF, part labels | native CNC dialects, offcut inventory |
| Drawings | GA, elevations (doors on/off), side sections, part drawings, hardware schedule, title block | LayOut, custom templates |
| Platform | Clerk orgs, Supabase, credits + Stripe, one global catalog + per-org overrides (CSV import) | SSO, API keys, webhooks |

**Exit criteria:** ≥ 3 workshops use it on real paid jobs; median *edits-to-approve* < 10; zero wrong-dimension parts cut because of a software bug; time from upload to package < 5 min p50.

### V1 — "Workshop OS" (months 5–9)

- Categories: kitchen runs (multiple units + worktop + fillers), desks, TV units, sliding-door wardrobes, inset fronts.
- AI: `accurate` mode (GPT ‖ Claude ensemble), SAM 2 + vanishing-point rectification, OCR dims from product pages, chat-to-edit ("make it 200 mm wider and add a drawer under the shelf" → JSON Patch on the spec, reviewed like any edit).
- Manufacturing: first native CNC dialect with a partner's machine (likely Homag MPR or Biesse BPP), per-org DXF layer mapping UI, offcut reuse, quote PDF.
- Shop floor: QR labels → part status tracking (cut/banded/drilled/assembled).
- Geometry: autoscaling farm; start `SkpSdkEngine` (headless `.skp` writer) to cut farm cost and licensing risk.
- Platform: outbound webhooks, API keys, rule-pack editor UI, hardware catalogs (Blum/Hettich/Häfele) imported as data.

### V2 — "Design-to-manufacture network" (months 10–18)

- Room context: site photos + floor plan → fitted furniture that respects walls, skirting, sockets, ceilings (scribe allowances automatic).
- Multi-piece projects (entire kitchen / bedroom) with shared materials and consolidated nesting.
- SketchUp **plugin** (reverse direction): designers model in SketchUp, push to DesignForge for production data — reuses the bridge + PartGraph contract.
- Marketplace: designers send approved designs to partner workshops for quotes (two-sided network effect).
- ERP/MES integrations (e.g. via webhooks), LayOut presentation sets, AR preview, generative variants ("show me 3 handle-less versions").

## 3. Risks and bottlenecks

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| 1 | **Scale ambiguity** — a single photo cannot give absolute size | H | H | Ask for one measured anchor; category priors; OCR; confidence chips; mandatory Spec Review. Never claim "measured". |
| 2 | **LLM invents construction** (impossible joints, hardware not stocked) | H | H | LLM writes only the Spec; catalog codes as schema enums; Rule Engine; deterministic generator. |
| 3 | **SketchUp licensing** for unattended SaaS use | M | **Critical** | Ask Trimble in writing *before* launch; `GeometryEngine` port; SketchUp C SDK writer as plan B; glTF engine ensures no feature depends only on SketchUp. |
| 4 | **SketchUp automation fragility** (modal dialogs, crashes, memory growth, updates) | H | M | Golden VM image, pinned version, watchdog + restart, reset instead of File>New, job timeout, verification of bbox/part count, cache by graph_hash. |
| 5 | **Wrong part gets cut** (liability, material waste, tool damage on CNC) | M | **Critical** | Verification gates, mandatory "Release to shop", operation simulation PDF, per-dialect test cuts, ToS limitation of liability, versioned audit trail. |
| 6 | **Every shop builds differently** (back style, connectors, CNC layers, setbacks) | H | M | Rule packs per org from day 1; layer-mapping config; onboarding session to set the rule pack. |
| 7 | **Long tail of furniture types** | H | M | Narrow category list; "other" → manual spec with generic box parts; add generators by demand data. |
| 8 | Provider model changes / price / outages | M | M | `VisionModel` port, two providers wired, eval gate, caching, fallbacks. |
| 9 | Windows farm cost and cold starts | M | M | Geometry only after approval; caching; one warm node; SDK engine in V1. |
| 10 | Multi-tenant data leak | L | H | RLS + repository-level org scoping + tests that try cross-org access; service-role key only on backend. |
| 11 | IP: users copying protected designs from images | M | M | ToS (user warrants rights); no public gallery of generated copies; respond to takedowns. |
| 12 | **Solo founder bandwidth** | H | H | This plan: narrow scope, boring stack, managed services, AI-assisted coding with guardrails, design partners as QA. |

**Throughput bottlenecks to watch**

| Bottleneck | MVP capacity | Lever |
|---|---|---|
| SketchUp node | ~1 job / 30–90 s / node | cache, more nodes, SDK engine |
| LLM rate limits / latency | provider tier | batch images per request, cache perception, tier upgrades |
| Celery long tasks | Redis `visibility_timeout` must exceed longest task (set 2 h), `acks_late=True`, `prefetch_multiplier=1` | separate queues per stage |
| Storage egress (zips with SKP + PNGs) | Supabase plan | lazy zip build, CDN, compress PNGs |
| Drawings CPU | seconds per design | worker-core horizontal scale |

## 4. Solo-founder development plan (Cursor-first)

### 4.1 Before writing code (week 0)

- 10 interviews with workshops and designers; get **50 real past jobs** (reference photos + the drawings/cut lists they actually produced). These are your eval set, your demo data, and your first rule packs.
- Sign 3–5 design partners (free during beta, weekly 30-min call).
- Email Trimble about SketchUp licensing for server-side automation.

### 4.2 Week-by-week (16 weeks)

| Wk | Goal | Done when |
|---|---|---|
| 1 | Monorepo, CI, Supabase (migrations from this repo), Clerk orgs, FastAPI + Next.js deployed to staging | Sign in → create project on staging |
| 2 | `df_domain` models, JSON Schema export, TS generation; **carcass generator** + tests (already started here) | `pytest` green, schema drift check in CI |
| 3 | glTF engine + 3D viewer; **Manual Spec mode** (form → preview) | Partner can type a wardrobe and see it |
| 4 | Cut list, edge banding, BOM, generic DXF, package zip | Partner cuts a real cabinet from our cut list |
| 5 | Ingest + Perception (one provider) + eval harness on the 50 jobs | Baseline metrics recorded |
| 6 | Dimension solver + layout mapper + anchors UX | Photo → reviewable spec < 60 s |
| 7 | Rule Engine + issues + one-click fixes | Error rules block approval |
| 8 | SketchUp bridge + forked MCP server running on your own machine; compiler | `.skp` matches glTF bbox for all eval specs |
| 9 | Windows node image + agent + claim API + heartbeats | Staging builds `.skp` end-to-end unattended |
| 10–11 | Drawings: elevations, sections, part drawings, title block, PDF | Partner says "I could hand this to my CNC operator" |
| 12 | Drawers + hanging + hinge/slide drilling; nesting + labels | Full wardrobe with drawers produced |
| 13 | Stripe credits, quotas, onboarding, catalog CSV import | First invoice |
| 14 | Observability (Sentry, Langfuse, uptime), backups, cross-tenant tests, security pass | Runbook written |
| 15 | Polish Spec Review UX from partner feedback; performance | edits-to-approve trending down |
| 16 | Paid beta launch | 3 paying workshops |

Rhythm: Mon–Thu build, Fri = partner calls + eval run + write next week's plan. Ship to staging daily, to prod weekly.

### 4.3 How to use Cursor without losing control of the architecture

1. **Context is the architecture.** Keep `docs/` and `.cursor/rules/*.mdc` in the repo (included here). Reference `@docs/01-domain-model.md` in prompts that touch the domain.
2. **Contracts first, then implementation.** Write/approve the Pydantic model or Protocol by hand; let the agent implement against it. Agents are great at filling interfaces and bad at inventing good ones.
3. **Tests are the spec for geometry.** For every generator change: ask Cursor to write the failing test first (sizes, part counts, no-collision check like `test_world_geometry_fills_overall_box_without_collisions`), then the code. Add **golden snapshot tests** — PartGraph JSON for 30 reference specs committed to the repo; any diff must be reviewed by you.
4. **Small, reviewable diffs.** One concern per Agent run; ask for a plan first on anything touching > 3 files. Read every diff in `df_parametric`, `df_manufacturing`, `df_rules` line by line — those decide what gets cut.
5. **Let agents do the boilerplate:** CRUD routers, shadcn forms, TanStack tables, Celery task wiring, SQL migrations (you review), Dockerfiles, CI YAML.
6. **Connect the SketchUp MCP server to Cursor itself during development** (MCP settings in Cursor) so you can experiment with geometry interactively, then freeze what works into bridge ops.
7. **Never let the agent "fix" a failing deterministic test by changing expected numbers** without a written reason in the commit message (rule included in `.cursor/rules`).
8. Use background agents for parallel chores (docs, tests for existing code, type cleanup) — never two agents on the same package.

### 4.4 Indicative monthly run-rate at MVP (verify current prices)

| Item | Rough cost |
|---|---|
| Vercel Pro | ~$20 |
| Supabase Pro (+ compute) | ~$25–60 |
| API + workers (Fly/Render) | ~$40–100 |
| Managed Redis | ~$10–30 |
| Windows GPU VM, 1 node always-on | ~$300–550 (on-demand); less with savings plans or a Mac mini/PC in your office early on |
| SketchUp Pro subscription per node | ~$30/month equivalent |
| Sentry / Langfuse / Clerk | free tiers early |
| LLM usage | variable — track `cost_micro_usd` per run from day 1 |

Early trick: during weeks 8–12 run the geometry node on your own machine with the agent pointed at staging. Rent the VM only when partners need unattended builds.

## 5. North-star and health metrics

- **Edits-to-approve** (AI quality), **time-to-package**, **parts produced per week through DesignForge** (real usage), **zero-defect cut rate**, gross margin per design (AI + geometry cost vs credit price), partner NPS.

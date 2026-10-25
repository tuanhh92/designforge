# DesignForge

> Furniture reference image → manufacturable design (SKP, drawings, cut list, BOM, CNC).

This repository is the founding architecture package. Read in order:

| # | Document | What it decides |
|---|----------|-----------------|
| 0 | [docs/00-architecture.md](docs/00-architecture.md) | Principles, high-level architecture, service boundaries, deployment, event flow, monorepo layout |
| 1 | [docs/01-domain-model.md](docs/01-domain-model.md) | DDD bounded contexts, aggregates, ubiquitous language, ERD |
| 2 | [docs/02-api.md](docs/02-api.md) | REST + realtime API contracts |
| 3 | [docs/03-ai-pipeline.md](docs/03-ai-pipeline.md) | 5-stage pipeline, model routing, dimension estimation, evals |
| 4 | [docs/04-mcp-layer.md](docs/04-mcp-layer.md) | SketchUp MCP adapter, geometry farm, bridge extension |
| 5 | [docs/05-manufacturing.md](docs/05-manufacturing.md) | Drawings, cut list, BOM, nesting, CNC export |
| 6 | [docs/06-roadmap-risks-plan.md](docs/06-roadmap-risks-plan.md) | MVP → V1 → V2, risks, solo-founder plan with Cursor |
| 7 | [docs/07-prd.md](docs/07-prd.md) | Product Requirements Document (export of the [live PRD](https://claude.ai/artifact/PEdpP2AJZP9ExWaynorr8z)) |

Code contracts (compilable skeletons, not full implementations):

| Path | Contents |
|------|----------|
| [supabase/migrations/0001_init.sql](supabase/migrations/0001_init.sql) | Full Postgres schema with RLS |
| [packages/contracts/src/](packages/contracts/src/) | TypeScript: FurnitureSpec, PartGraph, API DTOs, events |
| [python/df_domain/](python/df_domain/) | Pydantic domain models + ports (Protocols) |
| [python/df_ai/](python/df_ai/) | VisionModel port, OpenAI + Anthropic adapters, ensemble, dimension solver |
| [python/df_parametric/](python/df_parametric/) | Deterministic generator — worked example: sectioned carcass (wardrobe/bookcase/cabinet) |
| [python/df_geometry/](python/df_geometry/) | GeometryEngine port, PartGraph → command compiler, MCP client, SketchUp MCP engine |
| [python/tests/](python/tests/) | Determinism, sizes, hinge rule, no-collision geometry, compiler tests (5 passing) |
| [extensions/sketchup-bridge/](extensions/sketchup-bridge/) | Ruby extension that builds a PartGraph inside SketchUp in one undo operation |
| [extensions/sketchup-mcp-server/](extensions/sketchup-mcp-server/) | Forked FastMCP server exposing the `df_*` tools over stdio |

Run the tests (Python 3.12, `pip install pydantic numpy pytest`):

```bash
cd python && PYTHONPATH=. pytest -q tests
```
| [.cursor/rules/](.cursor/rules/) | Cursor rules that keep the AI coding agent inside the architecture |

## Run the MVP

Upload a furniture photo → AI analysis → FurnitureSpec → parts → 3D model → SketchUp model via MCP.

Needs Python 3.12+ (3.13 tested), Node 20+, and Postgres 13+.

```bash
make setup
```

Postgres — either Docker (`make db-up`) or, on macOS without Docker, Homebrew Postgres 16 with the
user and databases `.env` expects:

```bash
make db-brew
```

Shared config for the SketchUp extension and the worker (port, token, job folder):

```bash
make bridge-setup
```

Start everything in the background (API :8000, worker, web :3000, and the fake SketchUp bridge when
`GEOMETRY_ENGINE=sketchup_mcp` and SketchUp is not running). Logs go to `var/log/`:

```bash
make dev
```

```bash
make status
```

```bash
make stop
```

Open http://localhost:3000, upload a photo, and add one measured dimension if you have it.

| Setting in `.env` | What it does |
|---|---|
| `AI_PROVIDER=mock` (default) | No key needed: a deterministic analysis from the image's proportions and colour, so the pipeline runs end to end. |
| `AI_PROVIDER=openai` + `OPENAI_API_KEY` | GPT vision via the Responses API with a strict JSON schema. |
| `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` | Claude vision via a forced tool call. |
| `GEOMETRY_ENGINE=gltf` (default) | Web 3D preview, parts list and parts model only. |
| `GEOMETRY_ENGINE=sketchup_mcp` | Also builds the model in SketchUp through the MCP server: `.skp`, scene PNGs, OBJ, STL. |

**Language.** The web app defaults to Vietnamese; the VI | EN toggle in the header switches it (saved in the `df_locale` cookie). Strings live in `apps/web/lib/i18n/messages.ts`. Server messages (progress log, status, rule checks, spec notes, upload errors) carry a `code` + `params` that the UI translates; their English text is only the fallback.

**Real SketchUp.** Install `extensions/sketchup-bridge` into SketchUp (zip `designforge_bridge.rb` + `designforge_bridge/` as `designforge_bridge.rbz`, then Extension Manager → Install). Start SketchUp with the same `DF_BRIDGE_TOKEN`, `DF_BRIDGE_PORT` and an absolute `DF_JOB_ROOT` as the worker, and don't run `make bridge-fake`. The fake bridge speaks the same protocol so the whole MCP path can be developed and tested without SketchUp; its `.skp` is a labelled placeholder (OBJ, STL and PNG are real).

**Tests**

```bash
make test
```

The end-to-end test (`apps/api/tests/test_pipeline_e2e.py`) needs `DATABASE_URL` pointing at a **dedicated** test database (`make db-brew` creates `designforge_test`): it truncates tables, and a running `make worker` on the same database would race it for jobs.

### MVP flow

```
web (Next.js) ──multipart──► api (FastAPI) ──insert design + job──► Postgres
                                                                       │ jobs: FOR UPDATE SKIP LOCKED
worker ◄───────────────────────────────────────────────────────────────┘
  analyze:      images → vision model (mock | GPT | Claude) → ImageObservation
                → spec_generator (dimension fusion + rules) → FurnitureSpec v1 → enqueue build_model
  build_model:  FurnitureSpec → df_parametric → PartGraph → model.glb, parts.csv, part_graph.json
                → (sketchup_mcp) MCP client ─stdio─► MCP server ─TCP─► bridge in SketchUp → .skp, PNG, OBJ, STL
web polls GET /v1/designs/{id} → progress log, 3D viewer, spec editor (save → rebuild), parts table, downloads
```

## The one-sentence architecture

**AI proposes a `FurnitureSpec`, deterministic code builds a `PartGraph`, and every output — SketchUp model, drawings, cut list, BOM, CNC — is a projection of that `PartGraph`.**

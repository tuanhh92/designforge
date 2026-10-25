# 02 — API contracts

Base: `https://api.designforge.app/v1`. JSON, `snake_case` on the wire (FastAPI/Pydantic default; the generated TS client maps types as-is — don't fight it). TS types: [packages/contracts/src/api.ts](../packages/contracts/src/api.ts).

## Conventions

| Concern | Decision |
|---|---|
| Auth | `Authorization: Bearer <Clerk session JWT>`. Verified against Clerk JWKS (cached). Active org from the `org_id` claim; requests without an active org → `403 org_required`. |
| Roles | `owner/admin` manage catalog + billing; `designer` creates/edits designs; `shop` reads production data, can mark versions "released to shop"; `viewer` read-only. |
| Idempotency | `Idempotency-Key` header required on every POST that creates work (runs, approvals, exports). Stored 24 h in Redis keyed by `(org, key)`; replay returns the original response. |
| Concurrency | Spec edits use optimistic locking: `If-Match: "<spec_hash>"` → `412` on mismatch. |
| Errors | RFC 9457 `application/problem+json`: `{type, title, status, detail, code, errors?: [{path, message}]}`. Stable `code`s, e.g. `spec_invalid`, `version_frozen`, `quota_exceeded`, `run_active`. |
| Pagination | Cursor: `?limit=50&cursor=…` → `{items, next_cursor}`. |
| Units | Integers in mm. Display conversion is a client concern. |
| Versioning | URL major (`/v1`). Additive changes only within a major. `FurnitureSpec.schema_version` versioned separately with upgrade functions. |
| Long work | Never block a request > 2 s. Return `202` + `run` resource; progress via SSE. |
| Rate limits | Per org per plan, token bucket in Redis; `429` + `Retry-After`. |

## Endpoints

### Projects & designs

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/projects` | → `Page<Project>` |
| `POST` | `/projects` | `{name, client_name?, site_address?}` → `201 Project` |
| `POST` | `/projects/{project_id}/designs` | `CreateDesignRequest {name, images: [{filename, content_type, bytes, sha256, role?, user_notes?}]}` → `201 CreateDesignResponse {design, upload_targets: [{image_id, signed_url, headers}]}` |
| `POST` | `/designs/{design_id}/images` | add more images, same shape as above |
| `POST` | `/designs/{design_id}/images:confirm` | `{image_ids}` → `200` — client calls after direct-to-Storage uploads finish |
| `GET` | `/designs/{design_id}` | → `DesignDetail {design, current_version, versions_summary, latest_run, images}` |
| `DELETE` | `/designs/{design_id}` | soft delete |

### Runs (pipeline)

| Method | Path | Body → Response |
|---|---|---|
| `POST` | `/designs/{design_id}/runs` | `StartRunRequest {kind:'from_images', hints?: {category?, anchors?: DimensionAnchor[], materials_hint?, notes?}, options?: RunOptions}` → `202 PipelineRun` |
| `GET` | `/runs/{run_id}` | → `PipelineRun {id, status, steps: PipelineStep[], version_id, error?}` |
| `GET` | `/runs/{run_id}/events` | **SSE** stream of `DomainEvent` (see 00 §5.3). Supports `Last-Event-ID` for resume (event ids = outbox ids). |
| `POST` | `/runs/{run_id}:cancel` | → `202` |
| `POST` | `/runs/{run_id}/steps/{step}:retry` | → `202` (only failed retryable steps) |

`DimensionAnchor` = the cure for scale ambiguity: `{image_id?, dimension: 'width'|'height'|'depth'|'section_width'|'door_height', value_mm, source: 'user_measured'|'catalog'|'site_plan'}`. If the user provides even one anchor, dimension error drops from ±15–25 % to ±3–6 % (estimate; validate with evals).

### Versions & spec

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/designs/{design_id}/versions` | → `Page<DesignVersionSummary>` |
| `GET` | `/versions/{version_id}` | → `DesignVersion {id, version_no, status, spec, spec_hash, field_confidence, issues, rule_pack, graph_hash?, artifacts_summary}` |
| `PUT` | `/versions/{version_id}/spec` | full `FurnitureSpec`, `If-Match` → `200 SpecValidationResult {spec (normalised), spec_hash, issues}` — only for `draft` |
| `PATCH` | `/versions/{version_id}/spec` | RFC 6902 JSON Patch (what the Review UI sends; also how one-click "apply suggestion" works) → same as PUT |
| `POST` | `/versions/{version_id}:validate` | `{spec}` → `SpecValidationResult` (dry run, no write; used while typing, debounced 300 ms) |
| `POST` | `/versions/{version_id}:approve` | `{options?: RunOptions}` → `202 PipelineRun` (kind `regenerate`) — 409 if any `error` issue |
| `POST` | `/versions/{version_id}:fork` | → `201 DesignVersion` (new draft copied from this one) |
| `GET` | `/versions/{version_id}/preview.glb` | quick glTF built from PartGraph without SketchUp (≤ 1 s) — powers the live 3D preview in Review |

### Production data

| Method | Path | Response |
|---|---|---|
| `GET` | `/versions/{id}/part-graph` | `PartGraph` (JSON, ETag = graph_hash) |
| `GET` | `/versions/{id}/cutlist?format=json\|csv\|xlsx` | `CutList` or file |
| `GET` | `/versions/{id}/bom?format=json\|csv\|xlsx` | `Bom` (with cost roll-up) |
| `GET` | `/versions/{id}/nesting` | `NestResult {sheets: NestSheet[], yield_pct, sheet_count_by_material}` |
| `GET` | `/versions/{id}/drawings` | `DrawingSet {sheets: [{sheet_no, kind, title, pdf_url, svg_url, dxf_url}]}` |
| `GET` | `/versions/{id}/artifacts` | `Artifact[]` |
| `GET` | `/artifacts/{id}/download` | `302` → signed Storage URL (5 min TTL) |
| `POST` | `/versions/{id}/exports` | `ExportRequest {formats: ExportFormat[], cnc_dialect?: 'dxf_generic'\|'homag_mpr'\|'biesse_bpp'\|'scm_xxl', include_labels?: bool}` → `202 PipelineRun` (kind `exports_only`) |
| `POST` | `/versions/{id}:release` | mark "released to shop" (role `admin`/`shop`), freezes further exports for audit |

### Catalog

`GET/POST/PATCH /catalog/materials`, `/catalog/edge-bands`, `/catalog/sheet-stock`, `/catalog/hardware`, `/catalog/rule-packs` (POST creates a new version; GET `?include_global=true`). `POST /catalog/materials:import` accepts CSV.

### Webhooks (inbound)

- `POST /webhooks/clerk` — Svix-signed. `organization.created/updated/deleted`, `organizationMembership.*`, `user.deleted`.
- `POST /webhooks/stripe` — subscription + credit purchases.

### Outbound webhooks (V1)

`POST {customer_url}` with `X-DesignForge-Signature: t=…,v1=HMAC_SHA256`. Events: `package.ready`, `version.released`. Payload = `DomainEvent`. Source: outbox.

### Internal — geometry node API

Geometry nodes run on Windows boxes outside our trust boundary as much as possible, so they **never hold database or Redis credentials.** They speak to the API with a per-node token (`Authorization: Node <token>`, rotated, scoped to `/internal/geometry/*`).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/internal/geometry/claim` | Long-poll (≤ 25 s). Server does `SELECT … FROM geometry_jobs WHERE status='queued' AND engine=$1 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`. Returns `GeometryJobTicket {job_id, part_graph, exports, upload_targets: {kind → signed_url}, deadline}` or `204`. |
| `POST` | `/internal/geometry/jobs/{id}/heartbeat` | `{progress, phase}` every 5 s; missing 3 → job re-queued, node marked unhealthy |
| `POST` | `/internal/geometry/jobs/{id}/complete` | `{artifacts: [{kind, sha256, bytes, storage_path}], stats: {entities, components, duration_ms}, bbox_mm}` |
| `POST` | `/internal/geometry/jobs/{id}/fail` | `{code, message, retryable, sketchup_log_tail}` |
| `POST` | `/internal/geometry/nodes/{id}/heartbeat` | `{status, sketchup_version, bridge_version, free_disk_mb}` |

Using Postgres `SKIP LOCKED` as the geometry queue is deliberate: volume is low (tens–thousands of jobs/day), it is transactional with job state, it is visible in SQL, and Windows nodes only need HTTPS egress. Celery handles everything else.

## Example: Spec Review round-trip

```http
PATCH /v1/versions/7b1e…/spec
If-Match: "c0ffee…"
Content-Type: application/json-patch+json

[{"op":"replace","path":"/overall/width","value":2400},
 {"op":"replace","path":"/sections/1/compartments/2/count","value":3}]
```

```json
200 OK
{
  "spec_hash": "a91f…",
  "spec": { "...normalised FurnitureSpec..." },
  "issues": [
    { "rule_code": "DRAWER_HEIGHT_TOO_SMALL", "severity": "error",
      "path": "/sections/1/compartments/2",
      "message": "3 drawers in 360 mm gives 112 mm fronts; minimum for Blum Tandembox M is 120 mm.",
      "suggestion": [{"op":"replace","path":"/sections/1/compartments/2/count","value":2}] }
  ]
}
```

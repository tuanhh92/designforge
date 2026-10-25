# 03 — AI pipeline

```
 images ─► [0 Ingest] ─► [1 Perception] ─► [2 Knowledge Engine] ─► Spec Review (human) ─►
           CV + cheap      vision LLM(s)      dimension solver        approve
           model           structured out     + LLM layout mapper
                                              + Rule Engine
       ─► [3 Parametric] ─► PartGraph ─┬─► [4 Geometry: SketchUp MCP] ─► .skp .obj .stl scenes
          deterministic                ├─► [5a Manufacturing] ─► cut list, BOM, nesting, CNC
                                       └─► [5b Documentation] ─► drawings PDF/DXF
```

**Where AI is allowed:** stages 0–2 only. Stages 3–5 are deterministic code with unit tests. This is how we get manufacturing-grade outputs out of probabilistic models.

---

## Stage 0 — Ingest (worker-ai, ~1 s/image)

1. Download from Storage, verify sha256, strip EXIF (privacy) but keep orientation + focal length if present (useful for perspective).
2. Normalise: sRGB, longest side 2048 px (vision models downsample anyway; this caps token cost), JPEG q90.
3. Perceptual hash → dedupe within design.
4. **Relevance gate** with a cheap/fast model call: "Is there a piece of furniture? Which one is the subject? Is it a photo, render, sketch, or product page screenshot?" Reject memes/rooms with no clear subject; when several furniture items are present, ask the user to tap the one they mean (we store the click as a normalised point and pass it to Stage 1 as a crop hint).
5. Optional (V1): SAM 2 segmentation of the subject → crop + mask; line-segment detection (OpenCV LSD) + vanishing-point estimation → **rectified front elevation**. This turns proportion estimates from "LLM guess" into "measured pixel ratios" and is the single biggest accuracy jump after user anchors.

## Stage 1 — Image Understanding / Perception (worker-ai)

Output per image: `ImageObservation` ([python/df_domain/observation.py](../python/df_domain/observation.py)). Key design choices:

- **Ask for things vision models are good at:** category, counts (doors, drawers, sections, shelves), layout topology ("left section: 2 doors over 3 drawers"), handle type, base type, materials/finish, style, reading text (product pages often print `W 240 × H 236 × D 60 cm` — OCR'd dims are gold).
- **Don't ask for absolute millimetres.** Ask for *ratios* (width:height, section width shares, drawer front height shares) and *scale cues* (worktop, socket outlet ≈ 80 mm, door frame ≈ 2000–2100 mm, ceiling, a person, floor tiles). Absolute dimensions are computed in Stage 2.
- **Every field has a confidence** and an `evidence` string. Low confidence is useful information, not failure.
- **Strict structured output.** OpenAI Responses API with `text.format = {type: "json_schema", strict: true, schema}`; Claude via a single forced tool call whose `input_schema` is the same JSON Schema. Validate with Pydantic anyway; on validation failure, one repair round-trip with the error message, then fail the step.
- Multiple images of the same object are sent **in one request** (front + side + detail) so the model can cross-reference; the output is one fused observation plus per-image notes.

### Model routing

| Mode | Perception | Spec layout mapper | When |
|---|---|---|---|
| `fast` (default MVP) | 1 model (configurable; start with whichever wins the eval) | same | Free tier, drafts |
| `accurate` | **GPT-5 vision ‖ Claude vision in parallel** | stronger model | Paid tiers, or auto-escalate when `fast` confidence < 0.6 |

Ensembling rule for `accurate`: for discrete fields (category, counts, topology) — agree ⇒ confidence = max; disagree ⇒ take the higher-confidence answer, cap confidence at 0.5, add a `review_hint` so the UI highlights it. For ratios — weighted mean, variance from disagreement feeds the dimension solver.

All providers sit behind `VisionModel` ([python/df_ai/vision.py](../python/df_ai/vision.py); dimension solver in [dimension_solver.py](../python/df_ai/dimension_solver.py)); model IDs live in config, never in code. Record `provider, model, prompt_version, tokens, cost, latency, trace_id` in `analysis_runs` for every call.

## Stage 2 — Furniture Knowledge Engine (worker-ai + df_rules)

Turns observations into a valid `FurnitureSpec`. Three sub-steps, only one of which uses an LLM:

### 2a. Dimension solver (deterministic)

Unknowns: `W, H, D`, section widths `s_i`, compartment heights `c_ij`. Evidence, by weight:

1. **User anchors** — hard constraints.
2. **OCR'd dimensions** — near-hard (σ ≈ 1 %).
3. **Measured ratios** from rectified elevation (σ ≈ 3–5 %) or LLM ratios (σ ≈ 10–20 %).
4. **Scale cues** from Stage 1 (σ per cue type).
5. **Category priors** from the rule pack, e.g.

| Category | H | D | Notes |
|---|---|---|---|
| base_cabinet (EU) | carcass 720 + plinth 100–150 + top 38 → ~900 floor-to-top | carcass 560–580, worktop 600–650 | module widths 300/400/450/500/600/800/900 |
| wall_cabinet | 360–960 (720 common) | 300–350 | |
| wardrobe | 2000–2600 (often to ceiling − scribe) | 560–650 | hanging needs ≥ 530 clear depth |
| chest_of_drawers | 700–1200 | 400–550 | |
| desk | 720–760 | 500–800 | |

Solve a small weighted least-squares problem **in log space** (ratios become linear) with `scipy.optimize.lsq_linear` bounds from rule limits → posterior mean + variance per dimension → `field_confidence`. Then **snap**: overall to 1 mm (or 10 mm if no anchor), modules to catalog widths when within 3 %, drawer stacks to slide-length/front-height tables, shelf positions to the 32 mm grid.

### 2b. Layout mapper (LLM)

Input: fused observation, solved dimensions, org catalog *subset* (materials, hinge/slide/handle families actually stocked), rule-pack defaults. Output: the `FurnitureSpec` topology — sections, compartments, doors, materials, hardware choices, notes.

The structured-output schema is **built per request**: `material.code` and `hardware.code` become `enum`s of the org's catalog codes. The model physically cannot invent a hinge the workshop doesn't stock. Numbers it may emit are only `"auto"` or values copied from 2a; the server overwrites any number that disagrees with the solver (and logs it — that's eval signal).

### 2c. Rule Engine (deterministic, `df_rules`)

Rule packs are YAML (versioned in DB), each rule a Python predicate + message + optional auto-fix producing a JSON Patch:

| Code | Example rule |
|---|---|
| `PANEL_MAX_SIZE` | any part > sheet size − trim ⇒ error, suggest divider |
| `SHELF_SPAN_EXCEEDED` | 18 mm MFC shelf span > 800 mm (load class) ⇒ warning, suggest divider or 25 mm shelf |
| `HANGING_DEPTH` | hanging compartment clear depth < 530 ⇒ error |
| `HANGING_HEIGHT` | long hanging < 1500 / short < 900 ⇒ warning |
| `DRAWER_HEIGHT_TOO_SMALL` | front height < slide minimum ⇒ error |
| `DOOR_LEAF_TOO_WIDE` | hinged leaf > 600 mm ⇒ warning (sag), > 650 ⇒ error |
| `HINGE_COUNT` | door height → hinge count (≤ 900:2, ≤ 1600:3, ≤ 2000:4, else 5) — auto, not an issue |
| `DOOR_OVER_DRAWER_CLEARANCE` | internal drawers behind doors need front setback for hinge clearance |
| `WALL_SCRIBE` | fitted unit with no scribe allowance ⇒ info |
| `GRAIN_CONTINUITY` | veneered fronts in a stack should share grain direction ⇒ info |
| `TIPPING_RISK` | H/D > 3.5 and not fitted ⇒ warning, add anti-tip hardware to BOM |

Loop: `auto-fix safe issues → re-validate`. If structural errors remain, **one** LLM repair round with the issue list; then hand to the human with issues visible. The draft lands in `awaiting_review` either way.

### Spec Review (human) — the product's most important screen

- Left: source images with overlay of detected fronts. Right: form grouped *Overall → Construction → Sections → Fronts → Hardware*, each dimension field with a confidence chip (green ≥ 0.85, amber, red < 0.5) and its `source`.
- Centre: live 3D preview from `GET /versions/{id}/preview.glb` (Stage 3 + glTF engine, no SketchUp, < 1 s) re-rendered on each valid edit.
- Issue list with one-click fixes (apply the JSON Patch).
- **Metric that matters:** *edits-to-approve* (JSON Patch ops between AI draft and approved spec). Track per category and model; this is the north-star for AI quality.

## Evals (from week 2, not "later")

- `evals/datasets/` — start with ~150 items where ground truth is exact: **IKEA / retailer product pages** (published dimensions, many angles, assembly PDFs reveal construction), plus your own workshop's past jobs (photo + approved drawing). Grow to 1 000.
- Scored by `evals/run_evals.py` against `ground_truth.json` (a hand-checked FurnitureSpec):
  - category accuracy; exact-match on door / drawer / section counts; topology similarity (tree edit distance)
  - dimension MAPE without anchors / with one anchor
  - schema-valid rate, rule-error rate after auto-fix
  - cost and p95 latency per run
- CI gate: a prompt or model change that worsens any headline metric > 2 % fails the PR. Results logged to Langfuse datasets.

## Prompt management

- Prompts are files: `python/df_ai/prompts/perception.v7.md`, `layout_mapper.v4.md`, with Jinja variables. `prompt_version` recorded per call.
- System prompt contains the ubiquitous-language glossary (01-domain-model §1) and 3–5 few-shot examples (image → observation) chosen by category.
- Never include other tenants' data in few-shots.

## Cost & latency envelope (targets, verify with real token counts)

| Step | p50 latency | Notes |
|---|---|---|
| Ingest | 1–3 s | parallel per image |
| Perception (fast / accurate) | 10–25 s / 15–35 s | images dominate input tokens; cap at 6 images |
| Spec draft (solver + mapper + rules) | 5–15 s | |
| **Time to Spec Review** | **< 60 s** | product requirement |
| Parametric + mfg + drawings | 2–10 s | CPU |
| SketchUp build + exports | 15–90 s | farm-bound; cached by graph_hash |

Budget per design: keep AI cost under ~5 % of plan price per design. Cache perception by `(image sha256 set, prompt_version, model)`.

## Data & privacy

- Customer images are their IP. Use provider settings that exclude API data from training (default for both OpenAI and Anthropic API traffic) and request zero-data-retention where available for enterprise tiers.
- Store `raw_response` for evals only with org opt-in; otherwise keep 30 days.

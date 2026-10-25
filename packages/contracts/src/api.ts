/**
 * API DTOs. In the real repo these are generated from FastAPI's OpenAPI (openapi-typescript);
 * this hand-written version pins the intended shape.
 */
import type { FieldConfidence, FurnitureCategory, FurnitureSpec, JsonPatchOp, Mm, SpecIssue, Uuid } from "./furniture-spec";
import type { Grain, EdgeName } from "./part-graph";

export interface Page<T> { items: T[]; next_cursor: string | null }

export interface Problem {
  type: string; title: string; status: number; detail?: string;
  code: "spec_invalid" | "version_frozen" | "quota_exceeded" | "run_active" | "not_found"
      | "forbidden" | "org_required" | "precondition_failed" | "rate_limited" | string;
  errors?: { path: string; message: string }[];
}

// ── Projects & designs ────────────────────────────────────────────────────────
export interface Project { id: Uuid; name: string; client_name?: string; site_address?: string; created_at: string }

export interface ImageUploadRequest {
  filename: string; content_type: "image/jpeg" | "image/png" | "image/webp" | "image/heic";
  bytes: number; sha256: string;
  role?: "reference" | "detail" | "site_photo" | "sketch";
  user_notes?: string;
}
export interface CreateDesignRequest { name: string; images: ImageUploadRequest[] }
export interface UploadTarget { image_id: Uuid; signed_url: string; headers: Record<string, string> }
export interface Design { id: Uuid; project_id: Uuid; name: string; category: FurnitureCategory | null; current_version_id: Uuid | null; created_at: string }
export interface CreateDesignResponse { design: Design; upload_targets: UploadTarget[] }

export interface SourceImage {
  id: Uuid; url: string; role: ImageUploadRequest["role"]; accepted: boolean | null;
  rejected_reason?: string; width_px: number; height_px: number;
}

// ── Runs ──────────────────────────────────────────────────────────────────────
export type StepName = "ingest" | "perceive" | "draft_spec" | "validate_spec" | "generate_parts"
  | "build_geometry" | "compute_mfg" | "render_drawings" | "package";
export type RunStatus = "created" | "running" | "awaiting_review" | "completed" | "failed" | "cancelled";

export interface DimensionAnchor {
  image_id?: Uuid;
  dimension: "width" | "height" | "depth" | "section_width" | "door_height";
  value_mm: Mm;
  source: "user_measured" | "catalog" | "site_plan";
}

export interface RunOptions {
  skip_geometry?: boolean;
  exports?: ExportFormat[];
  cnc_dialect?: CncDialect;
  ai_mode?: "fast" | "accurate";   // accurate = dual-model ensemble
}

export interface StartRunRequest {
  kind: "from_images";
  hints?: { category?: FurnitureCategory; anchors?: DimensionAnchor[]; materials_hint?: string; notes?: string };
  options?: RunOptions;
}

export interface PipelineStep {
  name: StepName; status: "pending" | "running" | "succeeded" | "failed" | "skipped";
  attempt: number; progress: number | null; error?: { code: string; message: string; retryable: boolean };
  started_at?: string; finished_at?: string;
}
export interface PipelineRun {
  id: Uuid; design_id: Uuid; version_id: Uuid | null;
  kind: "from_images" | "regenerate" | "exports_only";
  status: RunStatus; steps: PipelineStep[]; created_at: string;
}

// ── Versions ──────────────────────────────────────────────────────────────────
export interface DesignVersion {
  id: Uuid; design_id: Uuid; version_no: number;
  status: "draft" | "in_review" | "approved" | "superseded" | "archived";
  spec: FurnitureSpec; spec_hash: string; field_confidence: FieldConfidence;
  issues: SpecIssue[]; graph_hash: string | null;
  approved_by?: string; approved_at?: string; created_at: string;
}
export interface SpecValidationResult { spec: FurnitureSpec; spec_hash: string; issues: SpecIssue[] }
export type SpecPatchRequest = JsonPatchOp[];

// ── Production data ───────────────────────────────────────────────────────────
export interface CutListLine {
  line_no: number; label_code: string; part_keys: string[]; description: string;
  material_code: string; thickness: Mm; cut_length: Mm; cut_width: Mm; qty: number;
  grain: Grain; edge_band: Partial<Record<EdgeName, string | null>>; has_machining: boolean;
}
export interface CutList { lines: CutListLine[]; totals: { parts: number; area_m2_by_material: Record<string, number>; edge_band_m_by_code: Record<string, number> } }

export interface BomLine {
  category: "sheet" | "edge_band" | "hardware" | "consumable" | "labour";
  code: string; description: string; qty: number; unit: "sheet" | "m2" | "m" | "pcs" | "h";
  unit_price_minor?: number; total_minor?: number; currency?: string;
}
export interface Bom { lines: BomLine[]; total_minor: number; currency: string; waste_factor: number }

export interface NestPlacement { part_key: string; label_code: string; x: Mm; y: Mm; rotated: boolean }
export interface NestSheet { material_code: string; sheet_index: number; length: Mm; width: Mm; placements: NestPlacement[]; yield_pct: number }
export interface NestResult { sheets: NestSheet[]; yield_pct: number; sheet_count_by_material: Record<string, number> }

export interface DrawingSheet { sheet_no: number; kind: "general_arrangement" | "elevation" | "section" | "part" | "assembly" | "hardware" | "nesting"; title: string; pdf_url: string; svg_url?: string; dxf_url?: string }
export interface DrawingSet { sheets: DrawingSheet[]; combined_pdf_url: string }

export type ExportFormat = "skp" | "obj" | "stl" | "dxf_3d" | "gltf" | "scene_png" | "drawing_pdf" | "drawing_dxf"
  | "cutlist_csv" | "cutlist_xlsx" | "bom_xlsx" | "cnc" | "labels_pdf" | "package_zip";
export type CncDialect = "dxf_generic" | "homag_mpr" | "biesse_bpp" | "scm_xxl";
export interface ExportRequest { formats: ExportFormat[]; cnc_dialect?: CncDialect; include_labels?: boolean }

export interface Artifact { id: Uuid; kind: string; bytes: number; mime: string; sha256: string; producer: string; created_at: string; download_url: string }

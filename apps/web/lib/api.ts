/** Typed client for the DesignForge API (mirrors apps/api/src/df_api/schemas.py). */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type DesignStatus = "uploaded" | "analyzing" | "spec_ready" | "building" | "model_ready" | "failed" | "unsupported";

export interface DesignSummary {
  id: string;
  name: string;
  status: DesignStatus;
  category: string | null;
  created_at: string;
  updated_at: string;
  cover_url: string | null;
}

export type MessageParams = Record<string, string | number | null>;

export interface SpecIssue {
  rule_code: string;
  severity: "info" | "warning" | "error";
  path: string;
  message: string;
  params?: MessageParams;
  suggestion?: { op: string; path: string; value?: unknown }[] | null;
}

export type Confidence = Record<string, { value: number; source: string; sources?: string[] }>;

/** Subset of df_domain.FurnitureSpec the UI reads and edits; the rest round-trips untouched. */
export interface FurnitureSpec {
  schema_version: "1.0";
  category: string;
  name: string;
  overall: { width: number; height: number; depth: number };
  construction: {
    carcass_material: { code: string };
    carcass_thickness: number;
    back: { style: string; material: { code: string }; thickness: number };
    base: { kind: "plinth" | "legs" | "none"; height?: number; [k: string]: unknown };
    [k: string]: unknown;
  };
  fronts: {
    style: "overlay_full" | "overlay_half" | "inset" | "sliding" | "none";
    material: { code: string }; thickness: number; reveal: number;
    handle: { kind: string; [k: string]: unknown };
    sliding?: { leaves: 2 | 3; track: { code: string }; overlap: number } | null;
    [k: string]: unknown;
  };
  sections: {
    width: number | "auto";
    compartments: { kind: string; height: number | "auto"; adjustable_shelves?: number; [k: string]: unknown }[];
    doors: { kind: string; leaves?: 1 | 2; hinge_side?: "left" | "right" | null; spans?: [number, number]; [k: string]: unknown }[];
  }[];
  style: { tags: string[]; finish: string; colour_hex?: string | null };
  rule_pack: { id: string; version: number };
  notes: string[];
}

export interface SpecOut {
  id: string;
  version: number;
  origin: "ai" | "user_edit";
  spec: FurnitureSpec;
  spec_hash: string;
  field_confidence: Confidence;
  issues: SpecIssue[];
  observation: Record<string, unknown> | null;
  notes_detail: { code: string; params: MessageParams; text: string }[];
  provider: string | null;
  model: string | null;
  created_at: string;
}

export interface JobOut {
  id: string;
  kind: "analyze" | "build_model";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  step: string | null;
  progress: number;
  attempts: number;
  max_attempts: number;
  error: { type: string; message: string; retryable: boolean } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobEvent {
  id: number; ts: string; level: "info" | "warning" | "error"; step: string | null;
  message: string; code: string | null; params: MessageParams;
}

export interface Artifact { id: string; kind: string; name: string; bytes: number; mime: string; producer: string; url: string; created_at: string }

export interface DesignDetail {
  id: string;
  name: string;
  status: DesignStatus;
  status_message: string | null;
  status_code: string | null;
  status_params: MessageParams;
  category: string | null;
  hints: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  images: { id: string; url: string; width_px: number; height_px: number }[];
  spec: SpecOut | null;
  versions: { id: string; version: number; origin: string; created_at: string }[];
  jobs: JobOut[];
  events: JobEvent[];
  artifacts: Artifact[];
  busy: boolean;
}

export interface Catalog {
  materials: { code: string; name: string; colour_hex: string; thickness: number }[];
  categories: string[];
}

export interface Part {
  key: string;
  role: string;
  label: string;
  material_code: string;
  length: number;
  width: number;
  thickness: number;
  cut_length: number;
  cut_width: number;
  grain: string;
  edge_band: Record<string, string | null>;
  operations: unknown[];
}

/** `code` + `params` (when the API sends them) let the UI show the error in the user's language. */
export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public params?: MessageParams, public body?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = await res.text(); }
    const b = (typeof body === "object" && body ? body : {}) as { detail?: unknown; code?: string; params?: MessageParams };
    const detail = b.detail as string | { code?: string; message?: string } | undefined;
    const code = b.code ?? (typeof detail === "object" ? detail?.code : undefined);
    const message = typeof detail === "string" ? detail : typeof detail === "object" && detail?.message ? detail.message
      : `Request failed (${res.status})`;
    throw new ApiError(res.status, message, code, b.params, body);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDesigns: () => request<DesignSummary[]>("/v1/designs"),
  getDesign: (id: string) => request<DesignDetail>(`/v1/designs/${id}`),
  catalog: () => request<Catalog>("/v1/catalog"),
  createDesign: (form: FormData) => request<{ id: string }>("/v1/designs", { method: "POST", body: form }),
  validateSpec: (id: string, spec: FurnitureSpec) =>
    request<{ issues: SpecIssue[]; spec_hash: string }>(`/v1/designs/${id}/spec:validate`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec),
    }),
  saveSpec: (id: string, spec: FurnitureSpec) =>
    request<{ spec_id: string | null; issues: SpecIssue[]; job_id: string | null }>(`/v1/designs/${id}/spec`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec),
    }),
  rebuild: (id: string) => request<{ job_id: string }>(`/v1/designs/${id}/rebuild`, { method: "POST" }),
  reanalyze: (id: string) => request<{ job_id: string }>(`/v1/designs/${id}/reanalyze`, { method: "POST" }),
  parts: async (artifactUrl: string) => (await request<{ parts: Part[] }>(artifactUrl.replace(API_URL, ""))).parts,
};

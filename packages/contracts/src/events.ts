/** Domain events (outbox → SSE / Supabase Realtime / outbound webhooks). */
import type { Uuid } from "./furniture-spec";
import type { StepName } from "./api";

interface Base<T extends string, P> {
  id: number;                    // outbox id, used as SSE Last-Event-ID
  type: T;
  run_id: Uuid; design_id: Uuid; version_id: Uuid | null;
  ts: string;
  payload: P;
}

export type DomainEvent =
  | Base<"run.step_started", { step: StepName; attempt: number }>
  | Base<"run.step_completed", { step: StepName; duration_ms: number }>
  | Base<"run.step_failed", { step: StepName; error_code: string; retryable: boolean }>
  | Base<"run.progress", { step: StepName; progress: number; phase?: string }>
  | Base<"images.ingested", { image_ids: Uuid[]; rejected: { image_id: Uuid; reason: string }[] }>
  | Base<"perception.completed", { observation_ids: Uuid[]; category: string; confidence: number }>
  | Base<"spec.drafted", { spec_hash: string; issue_count: number; low_confidence_fields: string[] }>
  | Base<"spec.approved", { approved_by: string }>
  | Base<"partgraph.generated", { part_count: number; hardware_count: number; graph_hash: string }>
  | Base<"geometry.completed", { artifact_ids: Uuid[]; node_id: string; duration_ms: number; cache_hit: boolean }>
  | Base<"geometry.failed", { code: string; retryable: boolean }>
  | Base<"manufacturing.completed", { sheet_count: number; yield_pct: number; cost_total_minor: number; currency: string }>
  | Base<"drawings.completed", { sheet_count: number; artifact_ids: Uuid[] }>
  | Base<"package.ready", { zip_artifact_id: Uuid }>;

export type DomainEventType = DomainEvent["type"];

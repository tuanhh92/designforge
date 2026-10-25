"""Job handlers.

analyze      images → ImageObservation (AI) → FurnitureSpec (deterministic) → saved spec version
             → enqueues build_model when the spec has no errors and auto_build is on
build_model  FurnitureSpec → PartGraph (deterministic) → glTF + parts CSV (always) → SketchUp via MCP (optional)
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import text

from df_domain.spec import FurnitureSpec
from df_geometry.mcp_client import SketchUpMcpError
from df_parametric.carcass import generate

from . import queue
from .analysis import SourceImage, analyze
from .catalog import DefaultCatalog, DefaultRules
from .config import get_settings
from .db import tx
from .designs import add_artifact, get_spec, save_spec, set_status
from .geometry import sketchup_outputs, web_outputs
from .queue import Job, RetryableError
from .spec_generator import UnsupportedCategory, build_spec

log = logging.getLogger(__name__)


def handle(job: Job) -> dict:
    if job.kind == "analyze":
        return run_analyze(job)
    if job.kind == "build_model":
        return run_build(job)
    raise ValueError(f"unknown job kind {job.kind}")


def mark_failed(job: Job, message: str) -> None:
    with tx() as conn:
        set_status(conn, job.design_id, "failed", message, code="status.failed", params={"error": message})


# ── analyze ─────────────────────────────────────────────────────────────────

def run_analyze(job: Job) -> dict:
    settings = get_settings()
    with tx() as conn:
        design = conn.execute(text("select hints from designs where id = :id"), {"id": job.design_id}).one()
        rows = conn.execute(text("select id, storage_key from source_images where design_id = :id order by position"),
                            {"id": job.design_id}).all()
        set_status(conn, job.design_id, "analyzing", "Analysing images", code="status.analyzing")
    hints = design.hints or {}
    images = [SourceImage(r.id, r.storage_key) for r in rows]

    queue.progress(job.id, "perceive", 0.1, f"Analysing {len(images)} image(s) with provider '{settings.ai_provider}'",
                   code="analyze.start", params={"count": len(images), "provider": settings.ai_provider})
    try:
        result = asyncio.run(analyze(images, hints.get("category"), hints.get("notes"), settings))
    except Exception as e:  # provider errors: rate limits and timeouts are worth retrying
        name = type(e).__name__
        if any(k in name for k in ("RateLimit", "Timeout", "APIConnection", "InternalServer", "Overloaded")):
            raise RetryableError(f"{name}: {e}") from e
        raise
    obs = result.observation
    queue.progress(job.id, "perceive", 0.6,
                   f"Detected {obs.category.value} ({obs.category.confidence:.0%}), {obs.section_count.value} section(s), "
                   f"{obs.door_count.value} door(s), {obs.drawer_count.value} drawer(s)",
                   data={"latency_ms": result.meta.latency_ms, "model": result.meta.model},
                   code="analyze.detected",
                   params={"category": obs.category.value, "confidence": round(obs.category.confidence * 100),
                           "sections": obs.section_count.value, "doors": obs.door_count.value,
                           "drawers": obs.drawer_count.value})

    queue.progress(job.id, "draft_spec", 0.7, "Generating FurnitureSpec", code="spec.generating")
    try:
        draft = build_spec(obs, hints)
    except UnsupportedCategory as e:
        category = hints.get("category") or obs.category.value
        with tx() as conn:
            set_status(conn, job.design_id, "unsupported", str(e), code="status.unsupported",
                       params={"category": category}, category=obs.category.value)
            queue.succeed(conn, job.id, {"unsupported": True, "category": obs.category.value})
        return {"unsupported": True}

    spec, issues = draft.spec, draft.issues
    errors = [i for i in issues if i.severity == "error"]
    auto_build = job.payload.get("auto_build", True) and not errors
    with tx() as conn:
        spec_id = save_spec(conn, job.design_id, spec, origin="ai", observation=obs.model_dump(mode="json"),
                            field_confidence=draft.confidence, issues=[i.model_dump(mode="json") for i in issues],
                            provider=result.meta.provider, model=result.meta.model,
                            notes_detail=[n.as_dict() for n in draft.notes])
        add_artifact(conn, job.design_id, spec_id, job.id, kind="spec_json", name="furniture_spec.json",
                     data=spec.model_dump_json(indent=2).encode(), mime="application/json", producer="spec_generator@1")
        if auto_build:
            queue.enqueue(conn, job.design_id, "build_model", {"spec_id": str(spec_id)})
            set_status(conn, job.design_id, "building", "Spec ready — building model", code="status.spec_building")
        elif errors:
            set_status(conn, job.design_id, "spec_ready", f"Spec has {len(errors)} error(s) to fix before building",
                       code="status.spec_errors", params={"count": len(errors)})
        else:
            set_status(conn, job.design_id, "spec_ready", "Spec ready for review", code="status.spec_review")
        queue.succeed(conn, job.id, {"spec_id": str(spec_id), "issues": len(issues), "auto_build": auto_build})
    return {"spec_id": str(spec_id)}


# ── build_model ─────────────────────────────────────────────────────────────

def run_build(job: Job) -> dict:
    settings = get_settings()
    spec_id = UUID(job.payload["spec_id"])
    with tx() as conn:
        row = get_spec(conn, spec_id)
        set_status(conn, job.design_id, "building", "Generating parts", code="status.generating_parts")
        # A retried attempt replaces the files of the earlier attempt.
        conn.execute(text("delete from artifacts where job_id = :j"), {"j": job.id})
    if row is None:
        raise ValueError(f"spec {spec_id} not found")
    spec = FurnitureSpec.model_validate(row["spec"])

    queue.progress(job.id, "generate_parts", 0.15, "Generating parts (parametric)", code="parts.generating")
    graph = generate(spec, DefaultRules(), DefaultCatalog())
    queue.progress(job.id, "generate_parts", 0.3,
                   f"{len(graph.parts)} parts, {sum(h.qty for h in graph.hardware)} hardware items",
                   data={"graph_hash": graph.graph_hash}, code="parts.generated",
                   params={"parts": len(graph.parts), "hardware": sum(h.qty for h in graph.hardware)})

    files = web_outputs(graph)
    queue.progress(job.id, "web_preview", 0.45, "3D preview (glTF) ready", code="preview.ready")
    with tx() as conn:
        for f in files:
            add_artifact(conn, job.design_id, spec_id, job.id, kind=f.kind, name=f.name, data=f.data, mime=f.mime,
                         producer=f.producer)

    sketchup = "skipped"
    parts_n = {"parts": len(graph.parts)}
    message, status_code, status_params = (
        f"Model ready — {len(graph.parts)} parts (web preview; SketchUp engine disabled)", "status.model_ready_web", parts_n)
    if settings.geometry_engine == "sketchup_mcp":
        queue.progress(job.id, "sketchup", 0.55, "Building SketchUp model via MCP", code="sketchup.building")
        try:
            su_files = asyncio.run(sketchup_outputs(
                graph, settings, str(job.id),
                lambda m, c, p: queue.progress(job.id, "sketchup", 0.75, m, code=c, params=p)))
        except Exception as e:  # noqa: BLE001 — SketchUp trouble degrades to the web preview, never loses it
            if isinstance(e, SketchUpMcpError) and e.retryable and job.attempts < job.max_attempts:
                raise RetryableError(str(e)) from e
            log.warning("SketchUp build failed for job %s", job.id, exc_info=True)
            sketchup = "failed"
            message, status_code, status_params = (
                f"Web preview ready; SketchUp model failed: {e}", "status.sketchup_failed", {"error": str(e)})
            queue.progress(job.id, "sketchup", 0.9, message, code="sketchup.failed", params={"error": str(e)})
        else:
            with tx() as conn:
                for f in su_files:
                    add_artifact(conn, job.design_id, spec_id, job.id, kind=f.kind, name=f.name, data=f.data,
                                 mime=f.mime, producer=f.producer)
            sketchup = "built"
            message, status_code, status_params = (
                f"Model ready — {len(graph.parts)} parts, SketchUp model built", "status.model_ready_sketchup", parts_n)

    with tx() as conn:
        set_status(conn, job.design_id, "model_ready", message, code=status_code, params=status_params)
        queue.succeed(conn, job.id, {"spec_id": str(spec_id), "parts": len(graph.parts),
                                     "graph_hash": graph.graph_hash, "sketchup": sketchup})
    return {"parts": len(graph.parts), "sketchup": sketchup}

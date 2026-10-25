"""DesignForge MVP API.

POST /v1/designs                  multipart upload → design + queued analysis job
GET  /v1/designs                  list
GET  /v1/designs/{id}             detail: images, current spec, jobs, events, artifacts (poll while busy)
POST /v1/designs/{id}/spec:validate   dry-run validation of an edited spec
PUT  /v1/designs/{id}/spec        save an edited spec as a new version and rebuild
POST /v1/designs/{id}/rebuild     rebuild the current spec
POST /v1/designs/{id}/reanalyze   run the AI analysis again
GET  /v1/images/{id}              source image
GET  /v1/artifacts/{id}           generated file (glb, skp, csv, …)
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from df_domain.spec import FurnitureSpec
from df_services import designs as repo
from df_services import queue
from df_services.catalog import DefaultCatalog
from df_services.config import get_settings
from df_services.db import migrate, tx
from df_services.designs import InvalidUpload, UploadedImage
from df_services.spec_generator import validate_spec
from df_services.storage import get_storage

from .schemas import CreatedDesign, DesignDetail, DesignSummary, JobQueued, SpecSaved, SpecValidation

log = logging.getLogger("df_api")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate()  # idempotent; the worker runs it too
    yield


app = FastAPI(title="DesignForge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"])

ANCHOR_DIMENSIONS = {"width", "height", "depth"}
CATEGORIES = {"wardrobe", "tall_cabinet", "bookcase", "base_cabinet", "wall_cabinet", "sideboard", "shoe_cabinet",
              "tv_unit", "chest_of_drawers", "vanity"}


@app.exception_handler(InvalidUpload)
async def _invalid_upload(_, exc: InvalidUpload):
    return JSONResponse(status_code=422, content={"detail": str(exc), "code": f"upload.{exc.code}", "params": exc.params})


def _url(path: str) -> str:
    return f"{settings.api_public_url.rstrip('/')}{path}"


@app.get("/health")
def health() -> dict:
    with tx() as conn:
        conn.execute(text("select 1"))
    return {"ok": True, "ai_provider": settings.ai_provider, "geometry_engine": settings.geometry_engine}


@app.get("/v1/catalog")
def catalog() -> dict:
    cat = DefaultCatalog()
    return {
        "materials": [{"code": c, "name": cat.material(c).sketchup_material_name, "colour_hex": cat.material(c).colour_hex,
                       "thickness": cat.material(c).thickness} for c in cat.material_codes("sheet")],
        "categories": sorted(CATEGORIES),
    }


@app.get("/v1/designs", response_model=list[DesignSummary])
def list_designs() -> list[dict]:
    with tx() as conn:
        rows = repo.list_designs(conn)
    return [{**r, "cover_url": _url(f"/v1/images/{r['cover_image_id']}") if r["cover_image_id"] else None} for r in rows]


@app.post("/v1/designs", response_model=CreatedDesign, status_code=201)
async def create_design(
    images: Annotated[list[UploadFile], File(description="1–6 images of one piece of furniture")],
    name: Annotated[str, Form()] = "",
    category: Annotated[str | None, Form()] = None,
    anchor_dimension: Annotated[str | None, Form()] = None,
    anchor_value_mm: Annotated[int | None, Form(ge=100, le=6000)] = None,
    notes: Annotated[str | None, Form(max_length=1000)] = None,
) -> dict:
    hints: dict[str, Any] = {"anchors": []}
    if category:
        if category not in CATEGORIES:
            raise HTTPException(422, f"unknown category {category!r}")
        hints["category"] = category
    if anchor_dimension and anchor_value_mm:
        if anchor_dimension not in ANCHOR_DIMENSIONS:
            raise HTTPException(422, f"anchor_dimension must be one of {sorted(ANCHOR_DIMENSIONS)}")
        hints["anchors"].append({"dimension": anchor_dimension, "value_mm": anchor_value_mm, "source": "user_measured"})
    if notes:
        hints["notes"] = notes
    uploads = [UploadedImage(f.filename or "image", f.content_type or "", await f.read()) for f in images]
    with tx() as conn:
        design_id = repo.create_design(conn, name or (images[0].filename or "Design").rsplit(".", 1)[0], uploads, hints)
    return {"id": design_id}


@app.get("/v1/designs/{design_id}", response_model=DesignDetail)
def get_design(design_id: UUID) -> dict:
    with tx() as conn:
        d = repo.get_design(conn, design_id)
    if d is None:
        raise HTTPException(404, "design not found")
    design = d["design"]
    return {
        **{k: design[k] for k in ("id", "name", "status", "status_message", "status_code", "status_params", "category",
                                  "hints", "created_at", "updated_at")},
        "images": [{**i, "url": _url(f"/v1/images/{i['id']}")} for i in d["images"]],
        "spec": d["spec"],
        "versions": d["versions"],
        "jobs": d["jobs"],
        "events": d["events"],
        "artifacts": [{**a, "url": _url(f"/v1/artifacts/{a['id']}")} for a in d["artifacts"]],
        "busy": any(j["status"] in ("queued", "running") for j in d["jobs"]),
    }


def _parse_spec(body: dict) -> FurnitureSpec:
    try:
        return FurnitureSpec.model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, detail=json.loads(e.json(include_url=False))) from e


@app.post("/v1/designs/{design_id}/spec:validate", response_model=SpecValidation)
def validate(design_id: UUID, body: Annotated[dict, Body()]) -> dict:
    spec = _parse_spec(body)
    return {"issues": [i.model_dump(mode="json") for i in validate_spec(spec)], "spec_hash": spec.spec_hash()}


def _ensure_idle(conn, design_id: UUID) -> None:
    exists = conn.execute(text("select 1 from designs where id = :id for update"), {"id": design_id}).scalar_one_or_none()
    if exists is None:
        raise HTTPException(404, "design not found")
    busy = conn.execute(text("select 1 from jobs where design_id = :id and status in ('queued','running') limit 1"),
                        {"id": design_id}).scalar_one_or_none()
    if busy:
        raise HTTPException(409, detail={"code": "error.busy", "message": "a job is already running for this design"})


@app.put("/v1/designs/{design_id}/spec", response_model=SpecSaved)
def save_spec(design_id: UUID, body: Annotated[dict, Body()]) -> dict:
    spec = _parse_spec(body)
    issues = [i.model_dump(mode="json") for i in validate_spec(spec)]
    if any(i["severity"] == "error" for i in issues):
        return {"spec_id": None, "issues": issues, "job_id": None}  # nothing saved: fix errors first
    with tx() as conn:
        _ensure_idle(conn, design_id)
        current = conn.execute(text("""select s.field_confidence from designs d join design_specs s on s.id = d.current_spec_id
                                       where d.id = :id"""), {"id": design_id}).scalar_one_or_none() or {}
        confidence = {k: ({**v, "value": 1.0, "source": "user_edit"} if k.startswith("/overall") else v)
                      for k, v in current.items()}
        spec_id = repo.save_spec(conn, design_id, spec, origin="user_edit", field_confidence=confidence, issues=issues)
        job_id = queue.enqueue(conn, design_id, "build_model", {"spec_id": str(spec_id)})
        repo.set_status(conn, design_id, "building", "Edited spec saved — rebuilding model", code="status.edited_rebuilding")
    return {"spec_id": spec_id, "issues": issues, "job_id": job_id}


@app.post("/v1/designs/{design_id}/rebuild", response_model=JobQueued, status_code=202)
def rebuild(design_id: UUID) -> dict:
    with tx() as conn:
        _ensure_idle(conn, design_id)
        spec_id = conn.execute(text("select current_spec_id from designs where id = :id"), {"id": design_id}).scalar_one()
        if spec_id is None:
            raise HTTPException(409, detail={"code": "error.no_spec", "message": "design has no spec yet"})
        job_id = queue.enqueue(conn, design_id, "build_model", {"spec_id": str(spec_id)})
        repo.set_status(conn, design_id, "building", "Rebuilding model", code="status.rebuilding")
    return {"job_id": job_id}


@app.post("/v1/designs/{design_id}/reanalyze", response_model=JobQueued, status_code=202)
def reanalyze(design_id: UUID) -> dict:
    with tx() as conn:
        _ensure_idle(conn, design_id)
        job_id = queue.enqueue(conn, design_id, "analyze", {"auto_build": True})
        repo.set_status(conn, design_id, "analyzing", "Re-analysing images", code="status.reanalyzing")
    return {"job_id": job_id}


@app.get("/v1/images/{image_id}")
def get_image(image_id: UUID) -> FileResponse:
    with tx() as conn:
        key = repo.image_key(conn, image_id)
    if key is None:
        raise HTTPException(404, "image not found")
    return FileResponse(get_storage().path(key), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: UUID, download: bool = False) -> FileResponse:
    with tx() as conn:
        a = repo.artifact_row(conn, artifact_id)
    if a is None:
        raise HTTPException(404, "artifact not found")
    return FileResponse(get_storage().path(a["storage_key"]), media_type=a["mime"],
                        filename=a["name"] if download else None,
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


def run() -> None:
    import uvicorn
    uvicorn.run("df_api.main:app", host="0.0.0.0", port=8000)

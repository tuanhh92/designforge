"""Design repository + use cases shared by the API and the worker."""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Connection, text

from df_domain.spec import FurnitureSpec

from . import queue
from .config import get_settings
from .storage import get_storage

ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_EDGE_PX = 2048


class InvalidUpload(ValueError):
    """`code` + `params` let the UI show the reason in the user's language."""

    def __init__(self, message: str, code: str, **params: Any):
        super().__init__(message)
        self.code, self.params = code, params


@dataclass(frozen=True)
class UploadedImage:
    filename: str
    content_type: str
    data: bytes


def normalise_image(img: UploadedImage) -> tuple[bytes, int, int]:
    """Validate, apply EXIF orientation, strip metadata, cap the long edge, re-encode as JPEG."""
    settings = get_settings()
    if len(img.data) > settings.max_upload_mb * 1024 * 1024:
        raise InvalidUpload(f"{img.filename}: larger than {settings.max_upload_mb} MB", "too_large",
                            name=img.filename, max_mb=settings.max_upload_mb)
    if img.content_type not in ALLOWED_TYPES:
        raise InvalidUpload(f"{img.filename}: unsupported type {img.content_type} (use JPEG, PNG or WEBP)", "bad_type",
                            name=img.filename)
    try:
        im = Image.open(io.BytesIO(img.data))
        im.load()
    except (UnidentifiedImageError, OSError) as e:
        raise InvalidUpload(f"{img.filename}: not a readable image", "unreadable", name=img.filename) from e
    im = ImageOps.exif_transpose(im).convert("RGB")
    if min(im.size) < 200:
        raise InvalidUpload(f"{img.filename}: too small ({im.width}×{im.height}); need at least 200 px", "too_small",
                            name=img.filename, width=im.width, height=im.height)
    im.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90, optimize=True)  # re-encoding drops EXIF (GPS etc.)
    return out.getvalue(), im.width, im.height


def create_design(conn: Connection, name: str, images: list[UploadedImage], hints: dict[str, Any]) -> UUID:
    settings = get_settings()
    if not images:
        raise InvalidUpload("upload at least one image", "no_images")
    if len(images) > settings.max_images:
        raise InvalidUpload(f"upload at most {settings.max_images} images", "too_many", max=settings.max_images)
    prepared = [normalise_image(i) for i in images]  # validate everything before writing anything

    design_id = conn.execute(
        text("insert into designs (name, hints) values (:n, cast(:h as jsonb)) returning id"),
        {"n": name.strip() or "Untitled design", "h": json.dumps(hints)},
    ).scalar_one()
    storage = get_storage()
    seen: set[str] = set()
    for pos, (data, w, h) in enumerate(prepared):
        sha = hashlib.sha256(data).hexdigest()
        if sha in seen:
            continue  # duplicate upload
        seen.add(sha)
        blob = storage.put(f"designs/{design_id}/images/{sha}.jpg", data)
        conn.execute(
            text("""insert into source_images (design_id, storage_key, sha256, content_type, bytes, width_px, height_px, position)
                    values (:d, :k, :s, 'image/jpeg', :b, :w, :h, :p)"""),
            {"d": design_id, "k": blob.key, "s": sha, "b": blob.bytes, "w": w, "h": h, "p": pos},
        )
    queue.enqueue(conn, design_id, "analyze", {"auto_build": True})
    set_status(conn, design_id, "analyzing", "Queued for analysis", code="status.queued_analysis")
    return design_id


def set_status(conn: Connection, design_id: UUID, status: str, message: str | None = None, *,
               code: str | None = None, params: dict | None = None, **fields: Any) -> None:
    """`message` is the English fallback; `code` + `params` are what the UI translates."""
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    conn.execute(
        text(f"""update designs set status = :s, status_message = :m, status_code = :c, status_params = cast(:p as jsonb),
                 updated_at = now(){', ' + sets if sets else ''} where id = :id"""),
        {"s": status, "m": message, "c": code, "p": json.dumps(params or {}), "id": design_id, **fields},
    )


def save_spec(conn: Connection, design_id: UUID, spec: FurnitureSpec, *, origin: str, observation: dict | None = None,
              field_confidence: dict | None = None, issues: list | None = None,
              provider: str | None = None, model: str | None = None, notes_detail: list | None = None) -> UUID:
    # Lock the design row so two concurrent saves cannot pick the same version number.
    conn.execute(text("select 1 from designs where id = :d for update"), {"d": design_id})
    version = conn.execute(
        text("select coalesce(max(version), 0) + 1 from design_specs where design_id = :d"), {"d": design_id}
    ).scalar_one()
    spec_id = conn.execute(
        text("""insert into design_specs (design_id, version, origin, spec, spec_hash, observation, field_confidence, issues,
                                          provider, model, notes_detail)
                values (:d, :v, :o, cast(:s as jsonb), :h, cast(:obs as jsonb), cast(:fc as jsonb), cast(:i as jsonb), :p, :m,
                        cast(:nd as jsonb))
                returning id"""),
        {"d": design_id, "v": version, "o": origin, "s": spec.model_dump_json(), "h": spec.spec_hash(),
         "obs": json.dumps(observation) if observation is not None else None,
         "fc": json.dumps(field_confidence or {}), "i": json.dumps(issues or []), "p": provider, "m": model,
         "nd": json.dumps(notes_detail or [])},
    ).scalar_one()
    conn.execute(text("update designs set current_spec_id = :s, category = :c, updated_at = now() where id = :d"),
                 {"s": spec_id, "c": spec.category, "d": design_id})
    return spec_id


def add_artifact(conn: Connection, design_id: UUID, spec_id: UUID | None, job_id: UUID | None, *, kind: str, name: str,
                 data: bytes, mime: str, producer: str) -> UUID:
    # The job id keeps every build's files apart: artifact URLs are cached as immutable.
    folder = f"specs/{spec_id}/{job_id or 'manual'}" if spec_id else "misc"
    blob = get_storage().put(f"designs/{design_id}/{folder}/{name}", data)
    return conn.execute(
        text("""insert into artifacts (design_id, spec_id, job_id, kind, name, storage_key, bytes, sha256, mime, producer)
                values (:d, :s, :j, :k, :n, :key, :b, :sha, :mime, :p) returning id"""),
        {"d": design_id, "s": spec_id, "j": job_id, "k": kind, "n": name, "key": blob.key, "b": blob.bytes,
         "sha": blob.sha256, "mime": mime, "p": producer},
    ).scalar_one()


# ── reads ───────────────────────────────────────────────────────────────────

def get_design(conn: Connection, design_id: UUID) -> dict | None:
    d = conn.execute(text("select * from designs where id = :id"), {"id": design_id}).mappings().one_or_none()
    if d is None:
        return None
    images = conn.execute(
        text("select id, width_px, height_px, bytes from source_images where design_id = :id order by position"),
        {"id": design_id}).mappings().all()
    spec = None
    if d["current_spec_id"]:
        spec = conn.execute(
            text("""select id, version, origin, spec, spec_hash, field_confidence, issues, observation, provider, model,
                           notes_detail, created_at
                    from design_specs where id = :s"""), {"s": d["current_spec_id"]}).mappings().one()
    versions = conn.execute(
        text("select id, version, origin, created_at from design_specs where design_id = :id order by version desc"),
        {"id": design_id}).mappings().all()
    jobs = conn.execute(
        text("""select id, kind, status, step, progress, attempts, max_attempts, error, created_at, started_at, finished_at
                from jobs where design_id = :id order by created_at desc limit 10"""), {"id": design_id}).mappings().all()
    latest_job_id = jobs[0]["id"] if jobs else None
    events = conn.execute(
        text("select id, ts, level, step, message, code, params from job_events where job_id = :j order by id"),
        {"j": latest_job_id}).mappings().all() if latest_job_id else []
    # Latest build wins: one row per file name for the current spec (rebuilds add new rows).
    artifacts = conn.execute(
        text("""select * from (
                  select distinct on (name) id, kind, name, bytes, mime, producer, created_at from artifacts
                  where design_id = :id and spec_id is not distinct from :s order by name, created_at desc
                ) latest order by created_at, name"""),
        {"id": design_id, "s": d["current_spec_id"]}).mappings().all()
    return {"design": dict(d), "images": [dict(i) for i in images], "spec": dict(spec) if spec else None,
            "versions": [dict(v) for v in versions], "jobs": [dict(j) for j in jobs],
            "events": [dict(e) for e in events], "artifacts": [dict(a) for a in artifacts]}


def list_designs(conn: Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(text("""
        select d.id, d.name, d.status, d.category, d.created_at, d.updated_at,
               (select id from source_images i where i.design_id = d.id order by position limit 1) as cover_image_id
        from designs d order by d.created_at desc limit :l"""), {"l": limit}).mappings().all()
    return [dict(r) for r in rows]


def get_spec(conn: Connection, spec_id: UUID) -> dict | None:
    row = conn.execute(text("select * from design_specs where id = :id"), {"id": spec_id}).mappings().one_or_none()
    return dict(row) if row else None


def image_key(conn: Connection, image_id: UUID) -> str | None:
    return conn.execute(text("select storage_key from source_images where id = :id"), {"id": image_id}).scalar_one_or_none()


def artifact_row(conn: Connection, artifact_id: UUID) -> dict | None:
    row = conn.execute(text("select * from artifacts where id = :id"), {"id": artifact_id}).mappings().one_or_none()
    return dict(row) if row else None

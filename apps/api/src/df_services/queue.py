"""Postgres job queue.

- enqueue(): insert a row (inside the caller's transaction, so a design and its job commit together)
- claim():   atomically take the oldest ready job with FOR UPDATE SKIP LOCKED (many workers, no double work)
- heartbeat()/progress(): liveness + UI progress
- succeed()/fail(): terminal state, or re-queue with exponential backoff when retryable
- requeue_stale(): rescue jobs whose worker died (no heartbeat for job_stale_after_seconds)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from .db import tx


@dataclass(frozen=True)
class Job:
    id: UUID
    design_id: UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


class RetryableError(Exception):
    """Transient failure (rate limit, timeout, SketchUp restart): the job is retried with backoff."""


def enqueue(conn: Connection, design_id: UUID, kind: str, payload: dict | None = None, max_attempts: int = 3) -> UUID:
    row = conn.execute(
        text("""insert into jobs (design_id, kind, payload, max_attempts)
                values (:d, :k, cast(:p as jsonb), :m) returning id"""),
        {"d": design_id, "k": kind, "p": json.dumps(payload or {}), "m": max_attempts},
    ).one()
    log_event(conn, row.id, f"queued {kind}", code="job.queued", params={"kind": kind})
    return row.id


def claim(worker_id: str, kinds: list[str] | None = None) -> Job | None:
    with tx() as conn:
        row = conn.execute(
            text("""
            update jobs set status = 'running', locked_by = :w, heartbeat_at = now(),
                            attempts = attempts + 1, started_at = coalesce(started_at, now()), error = null
            where id = (
              select id from jobs
              where status = 'queued' and run_after <= now()
                and (cast(:kinds as text[]) is null or kind = any(cast(:kinds as text[])))
              order by created_at
              for update skip locked
              limit 1)
            returning id, design_id, kind, payload, attempts, max_attempts"""),
            {"w": worker_id, "kinds": kinds},
        ).one_or_none()
        if row is None:
            return None
        log_event(conn, row.id, f"started by {worker_id} (attempt {row.attempts}/{row.max_attempts})",
                  code="job.started", params={"worker": worker_id, "attempt": row.attempts, "max": row.max_attempts})
        return Job(row.id, row.design_id, row.kind, row.payload, row.attempts, row.max_attempts)


def progress(job_id: UUID, step: str, value: float, message: str | None = None, data: dict | None = None,
             *, code: str | None = None, params: dict | None = None) -> None:
    with tx() as conn:
        conn.execute(
            text("update jobs set step = :s, progress = :v, heartbeat_at = now() where id = :id"),
            {"s": step, "v": max(0.0, min(1.0, value)), "id": job_id},
        )
        if message:
            log_event(conn, job_id, message, step=step, data=data, code=code, params=params)


def touch(job_id: UUID) -> None:
    with tx() as conn:
        conn.execute(text("update jobs set heartbeat_at = now() where id = :id and status = 'running'"), {"id": job_id})


def succeed(conn: Connection, job_id: UUID, result: dict) -> None:
    conn.execute(
        text("""update jobs set status = 'succeeded', progress = 1, result = cast(:r as jsonb),
                finished_at = now(), locked_by = null where id = :id"""),
        {"r": json.dumps(result), "id": job_id},
    )
    log_event(conn, job_id, "succeeded", code="job.succeeded")


def fail(job: Job, error: Exception, retryable: bool) -> bool:
    """Returns True when the job was re-queued for another attempt."""
    err = {"type": type(error).__name__, "message": str(error)[:2000], "retryable": retryable}
    retry = retryable and job.attempts < job.max_attempts
    with tx() as conn:
        if retry:
            delay = 2 ** job.attempts * 5  # 10 s, 20 s, 40 s …
            conn.execute(
                text("""update jobs set status = 'queued', error = cast(:e as jsonb), locked_by = null,
                        run_after = now() + make_interval(secs => :d) where id = :id"""),
                {"e": json.dumps(err), "d": delay, "id": job.id},
            )
            log_event(conn, job.id, f"failed, retrying in {delay}s: {err['message']}", level="warning",
                      code="job.retrying", params={"delay": delay, "error": err["message"]})
        else:
            conn.execute(
                text("""update jobs set status = 'failed', error = cast(:e as jsonb), finished_at = now(),
                        locked_by = null where id = :id"""),
                {"e": json.dumps(err), "id": job.id},
            )
            log_event(conn, job.id, f"failed: {err['message']}", level="error",
                      code="job.failed", params={"error": err["message"]})
    return retry


def requeue_stale(stale_after_seconds: int) -> int:
    with tx() as conn:
        rows = conn.execute(
            text("""update jobs set status = 'queued', locked_by = null
                    where status = 'running' and heartbeat_at < now() - make_interval(secs => :s)
                    returning id"""),
            {"s": stale_after_seconds},
        ).all()
        for r in rows:
            log_event(conn, r.id, "worker stopped responding; job re-queued", level="warning", code="job.requeued_stale")
        return len(rows)


def log_event(conn: Connection, job_id: UUID, message: str, *, level: str = "info", step: str | None = None,
              data: dict | None = None, code: str | None = None, params: dict | None = None) -> None:
    """`message` is the English fallback; `code` + `params` let the UI render it in the user's language."""
    conn.execute(
        text("""insert into job_events (job_id, level, step, message, data, code, params)
                values (:j, :l, :s, :m, cast(:d as jsonb), :c, cast(:p as jsonb))"""),
        {"j": job_id, "l": level, "s": step, "m": message, "d": json.dumps(data) if data else None,
         "c": code, "p": json.dumps(params or {})},
    )

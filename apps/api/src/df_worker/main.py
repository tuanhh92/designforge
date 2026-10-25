"""Worker: claims jobs from the Postgres queue and runs them one at a time.

Run several workers for throughput; SKIP LOCKED guarantees each job is taken once. SketchUp is
single-threaded, so when GEOMETRY_ENGINE=sketchup_mcp run exactly one worker per SketchUp instance
(or restrict it with --kinds build_model and run AI workers separately with --kinds analyze).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import time

from df_services import queue
from df_services.config import get_settings
from df_services.db import migrate
from df_services.pipeline import handle, mark_failed
from df_services.queue import RetryableError

log = logging.getLogger("df_worker")
_stop = threading.Event()


def _heartbeat(job_id, done: threading.Event) -> None:
    """Keep the job's heartbeat fresh during long steps so the stale-job reaper leaves it alone."""
    while not done.wait(15):
        try:
            queue.touch(job_id)
        except Exception:  # noqa: BLE001 — a missed heartbeat is not worth killing the job
            log.warning("heartbeat failed for job %s", job_id, exc_info=True)


def run_once(worker_id: str, kinds: list[str] | None) -> bool:
    job = queue.claim(worker_id, kinds)
    if job is None:
        return False
    log.info("job %s %s (attempt %s)", job.id, job.kind, job.attempts)
    done = threading.Event()
    threading.Thread(target=_heartbeat, args=(job.id, done), daemon=True).start()
    try:
        handle(job)
    except RetryableError as e:
        if not queue.fail(job, e, retryable=True):
            mark_failed(job, str(e))
    except Exception as e:  # noqa: BLE001 — every failure must land on the job, never kill the worker
        log.exception("job %s failed", job.id)
        queue.fail(job, e, retryable=False)
        mark_failed(job, f"{type(e).__name__}: {e}")
    finally:
        done.set()
    return True


def run() -> None:
    parser = argparse.ArgumentParser(description="DesignForge worker")
    parser.add_argument("--kinds", nargs="*", help="job kinds to take (default: all)")
    parser.add_argument("--once", action="store_true", help="drain the queue and exit (tests, CI)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    migrate()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    log.info("worker %s started (ai=%s, geometry=%s)", worker_id, settings.ai_provider, settings.geometry_engine)
    last_reap = 0.0
    while not _stop.is_set():
        if time.monotonic() - last_reap > 30:
            if n := queue.requeue_stale(settings.job_stale_after_seconds):
                log.warning("re-queued %s stale job(s)", n)
            last_reap = time.monotonic()
        worked = run_once(worker_id, args.kinds)
        if args.once and not worked:
            break
        if not worked:
            _stop.wait(settings.worker_poll_seconds)
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    run()

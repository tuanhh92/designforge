"""Database engine, sessions and a minimal ordered-SQL migration runner.

SQLAlchemy Core with explicit SQL: the schema is small, and the queue relies on Postgres features
(FOR UPDATE SKIP LOCKED, jsonb) that are clearest written directly.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from importlib import resources
from typing import Iterator

from sqlalchemy import Connection, Engine, create_engine, text

from .config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


@contextmanager
def tx() -> Iterator[Connection]:
    """One transaction: commits on success, rolls back on error."""
    with get_engine().begin() as conn:
        yield conn


def migrate(engine: Engine | None = None) -> list[str]:
    """Apply migrations/*.sql in name order, each once, recorded in schema_migrations."""
    engine = engine or get_engine()
    applied: list[str] = []
    files = sorted(
        (f for f in resources.files("df_services.migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    with engine.begin() as conn:
        conn.execute(text("select pg_advisory_xact_lock(727274)"))  # one migrator at a time
        conn.execute(text(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())"
        ))
        done = {r[0] for r in conn.execute(text("select name from schema_migrations"))}
        for f in files:
            if f.name in done:
                continue
            log.info("applying migration %s", f.name)
            conn.exec_driver_sql(f.read_text())
            conn.execute(text("insert into schema_migrations(name) values (:n)"), {"n": f.name})
            applied.append(f.name)
    return applied


def migrate_cli() -> None:
    logging.basicConfig(level=logging.INFO)
    applied = migrate()
    print("applied:", ", ".join(applied) if applied else "nothing (up to date)")

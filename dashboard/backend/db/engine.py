"""
db/engine.py — SQLAlchemy engine factory.

Reads DATABASE_URL from the environment.  Falls back to the legacy SQLite path
so existing deployments see zero behaviour change (AC1).

Dialect detection:
    from db.engine import dialect
    if dialect.name == "postgresql":   ...
    if dialect.name == "sqlite":       ...

Pool sizing (Postgres only — per ADR PG-Q8):
    EVONEXUS_DB_POOL_SIZE     (default 5)
    EVONEXUS_DB_MAX_OVERFLOW  (default 10)
    EVONEXUS_ALLOW_OVERSIZED_POOL=1  — disable fail-fast boot check
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locate the workspace root (two levels above backend/)
# ---------------------------------------------------------------------------
_WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Build DATABASE_URL
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = _WORKSPACE / "dashboard" / "data" / "evonexus.db"
_DEFAULT_URL = f"sqlite:///{_DEFAULT_DB_PATH}"

DATABASE_URL: str = os.environ.get("DATABASE_URL", "") or _DEFAULT_URL


def _build_engine() -> Engine:
    url = DATABASE_URL
    is_pg = url.startswith("postgresql") or url.startswith("postgres://")

    if is_pg:
        pool_size = int(os.environ.get("EVONEXUS_DB_POOL_SIZE", "5"))
        max_overflow = int(os.environ.get("EVONEXUS_DB_MAX_OVERFLOW", "10"))

        # Normalise postgres:// → postgresql+psycopg2://
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

        engine = create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            connect_args={"client_encoding": "UTF8"},
            # future=True for 2.0-style execution
            future=True,
        )

        # Fail-fast pool sizing check (ADR PG-Q8)
        _check_pool_ceiling(engine, pool_size, max_overflow)
    else:
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            future=True,
        )

        # Enable WAL mode and FK enforcement on every new connection
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _connection_record):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _check_pool_ceiling(engine: Engine, pool_size: int, max_overflow: int) -> None:
    """Refuse to start if connection demand exceeds 70% of PG max_connections.

    Set EVONEXUS_ALLOW_OVERSIZED_POOL=1 to skip.
    """
    if os.environ.get("EVONEXUS_ALLOW_OVERSIZED_POOL", "").strip() == "1":
        return

    try:
        with engine.connect() as conn:
            row = conn.execute(text("SHOW max_connections")).fetchone()
            max_conns = int(row[0]) if row else 100
    except OperationalError as exc:
        logger.warning("db: could not query max_connections: %s", exc)
        return

    # Assume a conservative worst-case process count of 4 (gunicorn workers)
    # when WORKERS env var is not set.
    processes = int(os.environ.get("WORKERS", "4"))
    demand = processes * (pool_size + max_overflow)
    ceiling = int(max_conns * 0.7)

    if demand > ceiling:
        msg = (
            f"db: pool sizing exceeds 70% of PG max_connections ({max_conns}). "
            f"Demand={demand} (processes={processes} × (pool_size={pool_size} + "
            f"max_overflow={max_overflow})), ceiling={ceiling}. "
            "Reduce EVONEXUS_DB_POOL_SIZE / EVONEXUS_DB_MAX_OVERFLOW / WORKERS, "
            "or set EVONEXUS_ALLOW_OVERSIZED_POOL=1 to override."
        )
        logger.error(msg)
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Module-level singleton — created once, reused across the process lifetime
# ---------------------------------------------------------------------------
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Return the shared SQLAlchemy engine (singleton per process)."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


# Convenience shortcut: dialect object (read-only)
@property  # type: ignore[misc]
def _dialect_prop():
    return get_engine().dialect


# Expose dialect as a module-level attribute so callers can do:
#   from db.engine import dialect
#   if dialect.name == "sqlite": ...
class _DialectProxy:
    """Lazy proxy to engine.dialect — resolves at first access."""

    def __getattr__(self, name: str):  # noqa: ANN001
        return getattr(get_engine().dialect, name)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DialectProxy dialect={get_engine().dialect.name!r}>"


dialect = _DialectProxy()

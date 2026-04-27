"""AC-F3 — Atomic ticket checkout: exactly one winner under concurrent requests.

The checkout SQL:
    UPDATE tickets
    SET locked_at = now(), locked_by = ?, lock_timeout_seconds = ?
    WHERE id = ? AND locked_at IS NULL

must guarantee exactly 1 row updated (winner) when 10 threads race simultaneously.

Postgres: tested under READ COMMITTED and REPEATABLE READ isolation levels.
  - Under REPEATABLE READ, psycopg2 may raise SerializationFailure (40001) —
    treated as a loser (rowcount=0), not a hard error.

SQLite: tested under default isolation (BEGIN DEFERRED). SQLite's file-level
  locking serialises concurrent writes natively; one thread acquires the write
  lock, others block then observe locked_at IS NOT NULL and return rowcount=0.

Run:
    # SQLite only
    pytest tests/db/test_atomic_checkout.py -m 'not postgres' -v

    # Postgres
    DATABASE_URL=postgresql://postgres:test@localhost:55443/postgres \
        pytest tests/db/test_atomic_checkout.py -m postgres -v
"""

from __future__ import annotations

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_DIR = REPO_ROOT / "dashboard" / "alembic"
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

_NOW = "2026-01-01T00:00:00.000Z"
_WORKERS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _create_ticket(engine: sa.Engine) -> str:
    """Insert an unlocked ticket, return its id."""
    tid = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO tickets "
            "(id, title, status, priority, priority_rank, created_at, updated_at, created_by) "
            "VALUES (:id, 'checkout-test', 'open', 'medium', 2, :now, :now, 'test')"
        ), {"id": tid, "now": _NOW})
        conn.commit()
    return tid


def _cleanup_ticket(engine: sa.Engine, ticket_id: str) -> None:
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM ticket_activity WHERE ticket_id = :tid"), {"tid": ticket_id})
        conn.execute(text("DELETE FROM tickets WHERE id = :tid"), {"tid": ticket_id})
        conn.commit()


# ---------------------------------------------------------------------------
# Checkout worker — used by both SQLite and PG tests
# ---------------------------------------------------------------------------

def _try_checkout_sqlite(engine: sa.Engine, ticket_id: str, actor_id: int) -> int:
    """Attempt checkout on SQLite. Returns rowcount (1=winner, 0=loser)."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "UPDATE tickets "
                "SET locked_at = :now, locked_by = :actor, lock_timeout_seconds = 1800 "
                "WHERE id = :tid AND locked_at IS NULL"
            ), {"now": _utcnow_str(), "actor": f"agent-{actor_id}", "tid": ticket_id})
            conn.commit()
            return result.rowcount
    except Exception:
        return 0


def _try_checkout_pg(raw_db_url: str, ticket_id: str, actor_id: int, isolation: str) -> int:
    """Attempt checkout on Postgres under the given isolation level.
    Returns rowcount (1=winner, 0=loser). SerializationFailure → 0.

    Accepts the plain DATABASE_URL (with password) directly — avoids the
    SQLAlchemy engine.url password-masking issue (str(engine.url) → '***').
    """
    import psycopg2
    import psycopg2.errors  # type: ignore[import]

    # Build a psycopg2-compatible DSN from the raw URL.
    dsn = raw_db_url
    if dsn.startswith("postgresql+psycopg2://"):
        dsn = "postgresql://" + dsn[len("postgresql+psycopg2://"):]
    elif dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        conn.set_session(isolation_level=isolation)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tickets "
                "SET locked_at = %s, locked_by = %s, lock_timeout_seconds = 1800 "
                "WHERE id = %s AND locked_at IS NULL",
                (_utcnow_str(), f"agent-{actor_id}", ticket_id),
            )
            rowcount = cur.rowcount
            conn.commit()
            return rowcount
        except psycopg2.errors.SerializationFailure:
            conn.rollback()
            return 0
        except Exception:
            conn.rollback()
            return 0
        finally:
            conn.close()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# SQLite test (always runs)
# ---------------------------------------------------------------------------

class TestAtomicCheckoutSQLite:
    """Concurrent checkout on SQLite — exactly one winner."""

    @pytest.fixture
    def sqlite_engine(self, tmp_path):
        """SQLite engine with full alembic schema (tickets table exists in 0002)."""
        import subprocess
        db_url = f"sqlite:///{tmp_path}/checkout_test.db"
        env = {**os.environ, "DATABASE_URL": db_url}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(_ALEMBIC_DIR),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
        engine = sa.create_engine(db_url, connect_args={"check_same_thread": False})
        yield engine
        engine.dispose()

    def test_concurrent_checkout_one_winner(self, sqlite_engine):
        """10 concurrent threads race to checkout one ticket — exactly 1 wins."""
        ticket_id = _create_ticket(sqlite_engine)

        try:
            with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
                futures = [
                    ex.submit(_try_checkout_sqlite, sqlite_engine, ticket_id, i)
                    for i in range(_WORKERS)
                ]
                results = [f.result() for f in as_completed(futures)]

            winners = sum(r for r in results if r == 1)
            losers = sum(1 for r in results if r == 0)

            assert winners == 1, (
                f"Expected exactly 1 winner under SQLite, got {winners}. "
                f"Results: {results}"
            )
            assert losers == _WORKERS - 1, f"Expected {_WORKERS - 1} losers, got {losers}"
        finally:
            _cleanup_ticket(sqlite_engine, ticket_id)


# ---------------------------------------------------------------------------
# Postgres tests (parametrised by isolation level)
# ---------------------------------------------------------------------------

@pytest.mark.postgres
@pytest.mark.parametrize("isolation_level", ["READ COMMITTED", "REPEATABLE READ"])
class TestAtomicCheckoutPostgres:
    """Concurrent checkout on Postgres — exactly one winner per isolation level."""

    @pytest.fixture
    def pg_engine_and_url(self):
        """Yields (engine, raw_db_url) so workers can build fresh psycopg2 connections."""
        db_url = os.environ.get("DATABASE_URL", "")
        if not (db_url.startswith("postgresql") or db_url.startswith("postgres://")):
            pytest.skip("Postgres not configured (DATABASE_URL not set)")
        import subprocess
        env = {**os.environ, "DATABASE_URL": db_url}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(_ALEMBIC_DIR),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
        engine = sa.create_engine(_norm_pg_url(db_url), pool_pre_ping=True)
        yield engine, db_url
        engine.dispose()

    def test_concurrent_checkout_one_winner(self, pg_engine_and_url, isolation_level):
        """10 threads race checkout of the same ticket; exactly 1 must win."""
        pg_engine, raw_db_url = pg_engine_and_url
        ticket_id = _create_ticket(pg_engine)

        try:
            with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
                futures = [
                    ex.submit(_try_checkout_pg, raw_db_url, ticket_id, i, isolation_level)
                    for i in range(_WORKERS)
                ]
                results = [f.result() for f in as_completed(futures)]

            winners = sum(r for r in results if r == 1)
            losers = sum(1 for r in results if r == 0)

            assert winners == 1, (
                f"Expected exactly 1 winner under {isolation_level}, got {winners}. "
                f"Results: {results}"
            )
            assert losers == _WORKERS - 1, (
                f"Expected {_WORKERS - 1} losers under {isolation_level}, got {losers}"
            )
        finally:
            _cleanup_ticket(pg_engine, ticket_id)

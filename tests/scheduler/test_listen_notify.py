"""Scheduler LISTEN/NOTIFY integration test — routine_definitions hot-reload.

Tests that scheduler._start_routine_listen_thread detects DB changes to
routine_definitions and sets _reload_flag within 3s.

These tests require a live Postgres instance (same as test_heartbeats_pg.py).
Marked @pytest.mark.postgres — skipped automatically without DATABASE_URL.

Usage:
    DATABASE_URL='postgresql://postgres:test@localhost:55471/postgres' \\
        pytest tests/scheduler/test_listen_notify.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_BACKEND = _REPO_ROOT / "dashboard" / "backend"
_ALEMBIC_DIR = _REPO_ROOT / "dashboard" / "alembic"
_SCHEDULER = _REPO_ROOT / "scheduler.py"

# Both backend (for db.engine) and repo root (for scheduler import) need to
# be on sys.path.
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_REPO_ROOT))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_IS_PG = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres://")


def _run_alembic_upgrade(db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"


def _pg_dsn() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@pytest.fixture(scope="module")
def pg_engine():
    if not _IS_PG:
        pytest.skip("DATABASE_URL not set or not PostgreSQL")

    from sqlalchemy import create_engine
    engine = create_engine(_pg_dsn(), pool_pre_ping=True)
    _run_alembic_upgrade(DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_routines(pg_engine):
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM routine_definitions WHERE slug LIKE 'sched-test-%'"
        ))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM routine_definitions WHERE slug LIKE 'sched-test-%'"
        ))


# ---------------------------------------------------------------------------
# _get_scheduler_dialect returns 'postgresql' when DATABASE_URL is PG
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_get_scheduler_dialect_returns_postgresql():
    """_get_scheduler_dialect() returns 'postgresql' when DATABASE_URL is PG."""
    import scheduler
    assert scheduler._get_scheduler_dialect() == "postgresql"


# ---------------------------------------------------------------------------
# _start_routine_listen_thread — hot reload integration
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_routine_listen_thread_sets_reload_flag(pg_engine, clean_routines):
    """After inserting a routine_definitions row, _reload_flag is set within 3s.

    Strategy:
      1. Clear _reload_flag.
      2. Start the LISTEN thread.
      3. Insert a routine row to fire the PG trigger (0009).
      4. Wait up to 3s — assert _reload_flag is set.
    """
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        pytest.skip("psycopg2 not installed")

    import scheduler
    from db import engine as engine_mod

    # Monkeypatch get_engine so scheduler uses the test engine.
    original_get_engine = engine_mod.get_engine
    engine_mod.get_engine = lambda: pg_engine

    # Clear flag before test.
    scheduler._reload_flag.clear()

    try:
        scheduler._start_routine_listen_thread()
        # Give thread time to register LISTEN.
        time.sleep(0.5)

        # Insert a row to fire the trigger.
        from sqlalchemy import text
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO routine_definitions
                    (slug, name, script, schedule, frequency, enabled,
                     config_json, created_at, updated_at)
                VALUES
                    ('sched-test-reload', 'Sched Test Reload', 'sched_test.py',
                     'daily 06:00', 'daily', false, '{}', NOW(), NOW())
            """))

        # Wait for _reload_flag to be set (up to 3s).
        triggered = scheduler._reload_flag.wait(timeout=3.0)
        assert triggered, (
            "_reload_flag was not set within 3s after INSERT triggered NOTIFY on "
            "routine_definitions. Expected hot-reload latency ≤2s (AC6)."
        )
    finally:
        engine_mod.get_engine = original_get_engine
        scheduler._reload_flag.clear()


@pytest.mark.postgres
def test_routine_listen_thread_ignores_heartbeat_notify(pg_engine):
    """_reload_flag is NOT set when a 'heartbeats' table NOTIFY arrives.

    Ensures the filter ``payload["table"] == "routine_definitions"`` works.
    """
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        pytest.skip("psycopg2 not installed")

    import scheduler

    scheduler._reload_flag.clear()

    # Send a manual NOTIFY for heartbeats (wrong table).
    db_url = DATABASE_URL
    dsn = db_url.replace("postgresql+psycopg2://", "postgresql://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]

    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    payload = json.dumps({"table": "heartbeats", "op": "INSERT", "id": "fake-hb"})
    cur.execute(f"SELECT pg_notify('config_changed', {repr(payload)});")
    conn.close()

    # _reload_flag should NOT be set (wrong table).
    time.sleep(0.5)
    assert not scheduler._reload_flag.is_set(), (
        "_reload_flag was set on a heartbeats NOTIFY — filter not working"
    )

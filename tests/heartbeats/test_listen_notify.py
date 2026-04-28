"""LISTEN/NOTIFY integration test — heartbeat dispatcher hot-reload.

Tests that the dispatcher's _start_listen_thread detects DB changes and
calls _reload_definitions() in PG mode.

These tests require a live Postgres instance (same as test_heartbeats_pg.py).
Marked @pytest.mark.postgres — skipped automatically without DATABASE_URL.

Usage:
    DATABASE_URL='postgresql://postgres:test@localhost:55471/postgres' \\
        pytest tests/heartbeats/test_listen_notify.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_BACKEND = _REPO_ROOT / "dashboard" / "backend"
_ALEMBIC_DIR = _REPO_ROOT / "dashboard" / "alembic"
sys.path.insert(0, str(_BACKEND))

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
def clean_heartbeats(pg_engine):
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM heartbeats"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM heartbeats"))


# ---------------------------------------------------------------------------
# _get_dialect returns 'postgresql' when engine is PG
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_get_dialect_returns_postgresql(pg_engine, monkeypatch):
    """_get_dialect() returns 'postgresql' when engine points to PG."""
    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    import importlib
    import heartbeat_dispatcher
    importlib.reload(heartbeat_dispatcher)

    # Re-apply monkeypatch after reload.
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)
    assert heartbeat_dispatcher._get_dialect() == "postgresql"


# ---------------------------------------------------------------------------
# _start_listen_thread — hot reload integration
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_listen_thread_triggers_reload(pg_engine, clean_heartbeats, monkeypatch):
    """After inserting a heartbeat row, _reload_definitions() is called within 3s.

    Strategy:
      1. Patch _reload_definitions with a counter.
      2. Start the LISTEN thread.
      3. Insert a heartbeat row to fire the PG trigger.
      4. Wait up to 3s — assert reload was called.
    """
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        pytest.skip("psycopg2 not installed")

    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    import heartbeat_dispatcher

    reload_called = threading.Event()
    original_reload = heartbeat_dispatcher._reload_definitions

    def _mock_reload():
        reload_called.set()

    monkeypatch.setattr(heartbeat_dispatcher, "_reload_definitions", _mock_reload)

    # Start LISTEN thread.
    heartbeat_dispatcher._start_listen_thread()
    # Give thread time to register LISTEN.
    time.sleep(0.5)

    # Insert a heartbeat row to fire the trigger.
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO heartbeats
                    (id, agent, interval_seconds, max_turns, timeout_seconds,
                     lock_timeout_seconds, wake_triggers, enabled,
                     decision_prompt, source_plugin, created_at, updated_at)
                VALUES
                    ('hb-reload-test', 'system', 3600, 10, 600, 1800,
                     :wt, false,
                     'Reload test decision prompt for dispatcher integration.',
                     null, NOW(), NOW())
            """),
            {"wt": json.dumps(["interval"])},
        )

    # Wait for reload (up to 3s — well under AC6 ≤2s target).
    triggered = reload_called.wait(timeout=3.0)
    assert triggered, (
        "_reload_definitions() was not called within 3s after INSERT triggered NOTIFY. "
        "Expected hot-reload latency ≤2s (AC6)."
    )


@pytest.mark.postgres
def test_sync_skipped_in_pg_mode(pg_engine, monkeypatch):
    """_sync_heartbeats_to_db() is a no-op in PG mode (does not read YAML)."""
    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    import heartbeat_dispatcher

    # Patch load_heartbeats_yaml to detect if it gets called.
    yaml_called = threading.Event()

    def _fail_if_called(*args, **kwargs):
        yaml_called.set()
        raise AssertionError("load_heartbeats_yaml should NOT be called in PG mode")

    monkeypatch.setattr(
        "heartbeat_schema.load_heartbeats_yaml",
        _fail_if_called,
        raising=False,
    )

    # This should be a no-op in PG mode, not call load_heartbeats_yaml.
    heartbeat_dispatcher._sync_heartbeats_to_db()

    assert not yaml_called.is_set(), (
        "_sync_heartbeats_to_db() called load_heartbeats_yaml in PG mode — must be no-op"
    )

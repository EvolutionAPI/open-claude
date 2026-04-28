"""Heartbeats PG-native tests — Fase 3 (pg-native-configs).

Tests:
  - Migration 0008 creates trg_heartbeats_notify trigger on PG.
  - LISTEN on 'config_changed' receives notification after INSERT/DELETE.
  - load_heartbeats() in PG mode returns rows from DB, not from YAML.
  - load_heartbeats(include_plugins=False) excludes plugin-sourced rows.
  - Schema allows source_plugin to be set (AC4 prerequisite).

All tests in this file require a live Postgres instance and are marked
@pytest.mark.postgres.  They are skipped automatically when DATABASE_URL
is absent or points to SQLite.

Usage:
    docker run -d --name pg-phase3-hb -e POSTGRES_PASSWORD=test -p 55471:5432 postgres:16
    sleep 4
    DATABASE_URL='postgresql://postgres:test@localhost:55471/postgres' \\
        pytest tests/db/test_heartbeats_pg.py -v
    docker rm -f pg-phase3-hb
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
sys.path.insert(0, str(_BACKEND))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_IS_PG = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres://")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pg_dsn() -> str:
    """Return a psycopg2-compatible DSN from DATABASE_URL."""
    url = DATABASE_URL
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _run_alembic_upgrade(db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def pg_engine():
    """Module-scoped PG engine with schema applied."""
    if not _IS_PG:
        pytest.skip("DATABASE_URL not set or not PostgreSQL")

    from sqlalchemy import create_engine

    engine = create_engine(_pg_dsn(), pool_pre_ping=True)
    _run_alembic_upgrade(DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_heartbeats(pg_engine):
    """Delete all heartbeats rows before/after each test."""
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM heartbeats"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM heartbeats"))


def _insert_heartbeat(conn, hb_id: str, source_plugin: str | None = None) -> None:
    from sqlalchemy import text
    conn.execute(
        text("""
            INSERT INTO heartbeats
                (id, agent, interval_seconds, max_turns, timeout_seconds,
                 lock_timeout_seconds, wake_triggers, enabled,
                 decision_prompt, source_plugin, created_at, updated_at)
            VALUES
                (:id, 'system', 3600, 10, 600, 1800,
                 :wt, false, 'Test heartbeat decision prompt for unit tests.',
                 :sp,
                 NOW(), NOW())
        """),
        {
            "id": hb_id,
            "wt": json.dumps(["interval"]),
            "sp": source_plugin,
        },
    )


# ---------------------------------------------------------------------------
# Migration 0008 — trigger exists
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_trigger_exists_after_migration(pg_engine):
    """Migration 0008 must have created trg_heartbeats_notify trigger."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT trigger_name
                FROM information_schema.triggers
                WHERE event_object_table = 'heartbeats'
                  AND trigger_name = 'trg_heartbeats_notify'
            """)
        ).fetchone()

    assert row is not None, (
        "trg_heartbeats_notify trigger not found on heartbeats table after migration 0008"
    )


@pytest.mark.postgres
def test_notify_function_exists(pg_engine):
    """notify_heartbeat_change() PL/pgSQL function must exist."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT proname FROM pg_proc
                WHERE proname = 'notify_heartbeat_change'
            """)
        ).fetchone()

    assert row is not None, "notify_heartbeat_change() function not found"


# ---------------------------------------------------------------------------
# LISTEN/NOTIFY — trigger fires
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_listen_notify_on_insert(pg_engine, clean_heartbeats):
    """INSERT into heartbeats triggers pg_notify('config_changed', ...) payload."""
    try:
        import psycopg2  # type: ignore[import]
        import select as _select
    except ImportError:
        pytest.skip("psycopg2 not installed")

    raw_url = DATABASE_URL
    if raw_url.startswith("postgresql+psycopg2://"):
        dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
    else:
        dsn = raw_url

    # Open a dedicated LISTEN connection.
    lconn = psycopg2.connect(dsn)
    lconn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    lcur = lconn.cursor()
    lcur.execute("LISTEN config_changed;")

    try:
        # Insert via SQLAlchemy (fires trigger).
        with pg_engine.begin() as conn:
            _insert_heartbeat(conn, "hb-listen-test-insert")

        # Wait up to 3s for notification.
        ready = _select.select([lconn], [], [], 3.0)
        assert ready != ([], [], []), "No NOTIFY received within 3s after INSERT"

        lconn.poll()
        assert lconn.notifies, "notifies queue is empty after poll()"

        notif = lconn.notifies.pop(0)
        assert notif.channel == "config_changed"
        payload = json.loads(notif.payload)
        assert payload["table"] == "heartbeats"
        assert payload["op"] == "INSERT"
        assert payload["id"] == "hb-listen-test-insert"
    finally:
        lconn.close()


@pytest.mark.postgres
def test_listen_notify_on_delete(pg_engine, clean_heartbeats):
    """DELETE from heartbeats triggers pg_notify('config_changed', ...) payload."""
    try:
        import psycopg2  # type: ignore[import]
        import select as _select
    except ImportError:
        pytest.skip("psycopg2 not installed")

    raw_url = DATABASE_URL
    if raw_url.startswith("postgresql+psycopg2://"):
        dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
    else:
        dsn = raw_url

    # Insert the row first (without listener open yet).
    with pg_engine.begin() as conn:
        _insert_heartbeat(conn, "hb-listen-test-delete")

    # Open LISTEN connection.
    lconn = psycopg2.connect(dsn)
    lconn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    lcur = lconn.cursor()
    lcur.execute("LISTEN config_changed;")

    try:
        # Delete via SQLAlchemy.
        from sqlalchemy import text
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM heartbeats WHERE id = 'hb-listen-test-delete'"))

        ready = _select.select([lconn], [], [], 3.0)
        assert ready != ([], [], []), "No NOTIFY received within 3s after DELETE"

        lconn.poll()
        assert lconn.notifies, "notifies queue is empty after poll()"

        notif = lconn.notifies.pop(0)
        payload = json.loads(notif.payload)
        assert payload["table"] == "heartbeats"
        assert payload["op"] == "DELETE"
        assert payload["id"] == "hb-listen-test-delete"
    finally:
        lconn.close()


# ---------------------------------------------------------------------------
# load_heartbeats() — PG mode reads from DB
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_load_heartbeats_reads_from_db(pg_engine, clean_heartbeats, monkeypatch):
    """load_heartbeats() in PG mode returns rows from DB, not YAML."""
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        _insert_heartbeat(conn, "hb-pg-load-test-a")
        _insert_heartbeat(conn, "hb-pg-load-test-b")

    # Patch get_engine to return our test engine.
    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    from heartbeat_schema import load_heartbeats
    result = load_heartbeats(include_plugins=True)

    ids = {hb.id for hb in result.heartbeats}
    assert "hb-pg-load-test-a" in ids
    assert "hb-pg-load-test-b" in ids


@pytest.mark.postgres
def test_load_heartbeats_exclude_plugins(pg_engine, clean_heartbeats, monkeypatch):
    """load_heartbeats(include_plugins=False) excludes plugin-sourced rows."""
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        _insert_heartbeat(conn, "hb-core", source_plugin=None)
        _insert_heartbeat(conn, "hb-plugin", source_plugin="evo-essentials")

    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    from heartbeat_schema import load_heartbeats
    result = load_heartbeats(include_plugins=False)

    ids = {hb.id for hb in result.heartbeats}
    assert "hb-core" in ids
    assert "hb-plugin" not in ids, (
        "include_plugins=False should exclude rows with source_plugin IS NOT NULL"
    )


@pytest.mark.postgres
def test_load_heartbeats_include_plugins(pg_engine, clean_heartbeats, monkeypatch):
    """load_heartbeats(include_plugins=True) returns both core and plugin rows."""
    with pg_engine.begin() as conn:
        _insert_heartbeat(conn, "hb-core2", source_plugin=None)
        _insert_heartbeat(conn, "hb-plugin2", source_plugin="evo-essentials")

    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

    from heartbeat_schema import load_heartbeats
    result = load_heartbeats(include_plugins=True)

    ids = {hb.id for hb in result.heartbeats}
    assert "hb-core2" in ids
    assert "hb-plugin2" in ids


# ---------------------------------------------------------------------------
# AC4 prerequisite — schema allows source_plugin (already present in 0002)
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_source_plugin_column_accepts_slug(pg_engine, clean_heartbeats):
    """heartbeats.source_plugin column accepts a plugin slug (AC4 schema check)."""
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        _insert_heartbeat(conn, "hb-ac4-check", source_plugin="evo-essentials")

    with pg_engine.connect() as conn:
        row = conn.execute(
            text("SELECT source_plugin FROM heartbeats WHERE id = 'hb-ac4-check'")
        ).fetchone()

    assert row is not None
    assert row.source_plugin == "evo-essentials"

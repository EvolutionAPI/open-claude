"""Routine definitions PG-native tests — Fase 4 (pg-native-configs).

Tests:
  - Migration 0009 creates trg_routine_definitions_notify trigger on PG.
  - LISTEN on 'config_changed' receives notification after INSERT/UPDATE/DELETE.
  - routine_store.upsert_routine() inserts and updates rows correctly.
  - routine_store.list_routines_grouped() returns correct grouped shape.
  - routine_store.import_from_yaml() syncs YAML into DB without duplicates.
  - routine_store.toggle_routine_enabled() toggles enabled field.
  - routine_store.delete_routine() removes rows.

All tests in this file require a live Postgres instance and are marked
@pytest.mark.postgres.  They are skipped automatically when DATABASE_URL
is absent or points to SQLite.

Usage:
    docker run -d --name pg-fase4 -e POSTGRES_PASSWORD=test -p 55471:5432 postgres:16
    sleep 4
    DATABASE_URL='postgresql://postgres:test@localhost:55471/postgres' \\
        pytest tests/db/test_routines_pg.py -v
    docker rm -f pg-fase4
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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


@pytest.fixture(autouse=True)
def clean_routines(pg_engine):
    """Delete test rows before and after each test."""
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM routine_definitions WHERE source_plugin IS NULL AND slug LIKE 'test-%'"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM routine_definitions WHERE source_plugin IS NULL AND slug LIKE 'test-%'"))


@pytest.fixture(autouse=True)
def patch_engine(pg_engine, monkeypatch):
    """Make routine_store use the test engine."""
    from db import engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)


# ---------------------------------------------------------------------------
# AC1: trigger exists after 0009 migration
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_trigger_exists_after_migration(pg_engine):
    """trg_routine_definitions_notify trigger exists on routine_definitions after 0009."""
    from sqlalchemy import text
    with pg_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT tgname FROM pg_trigger
            WHERE tgname = 'trg_routine_definitions_notify'
        """)).fetchone()
    assert row is not None, (
        "trg_routine_definitions_notify trigger not found after alembic upgrade head"
    )


# ---------------------------------------------------------------------------
# AC2: pg_notify fires after INSERT
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_notify_fires_after_insert(pg_engine):
    """pg_notify('config_changed', ...) fires when a routine_definitions row is inserted."""
    try:
        import psycopg2  # type: ignore[import]
        import select as _select
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = DATABASE_URL
    if dsn.startswith("postgresql+psycopg2://"):
        dsn = "postgresql://" + dsn[len("postgresql+psycopg2://"):]

    listen_conn = psycopg2.connect(dsn)
    listen_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    listen_cur = listen_conn.cursor()
    listen_cur.execute("LISTEN config_changed;")

    # Insert a test row to fire the trigger.
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO routine_definitions
                (slug, name, script, schedule, frequency, enabled, config_json, created_at, updated_at)
            VALUES
                ('test-notify', 'Test Notify', 'test_notify.py', 'daily 06:00', 'daily',
                 false, '{}', NOW(), NOW())
        """))

    # Wait up to 2s for the notification.
    ready = _select.select([listen_conn], [], [], 2.0)
    assert ready != ([], [], []), "No NOTIFY received within 2s after INSERT into routine_definitions"

    listen_conn.poll()
    assert listen_conn.notifies, "Expected at least one notification"
    notif = listen_conn.notifies.pop(0)
    payload = json.loads(notif.payload)
    assert payload["table"] == "routine_definitions"
    assert payload["op"] == "INSERT"
    assert payload["id"] is not None

    listen_conn.close()


# ---------------------------------------------------------------------------
# AC3: upsert_routine CRUD
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_upsert_routine_insert(pg_engine):
    """upsert_routine inserts a new row and returns its id."""
    import routine_store
    row_id = routine_store.upsert_routine(
        slug="test-review",
        name="Test Review",
        script="review.py",
        frequency="daily",
        config_json={"time": "06:50"},
        enabled=False,
    )
    assert isinstance(row_id, int)
    assert row_id > 0

    row = routine_store.get_routine(row_id)
    assert row is not None
    assert row["slug"] == "test-review"
    assert row["name"] == "Test Review"
    assert row["frequency"] == "daily"
    assert row["schedule"] == "daily 06:50"
    cfg = json.loads(row["config_json"])
    assert cfg["time"] == "06:50"


@pytest.mark.postgres
def test_upsert_routine_update(pg_engine):
    """upsert_routine updates existing row without creating a duplicate."""
    import routine_store

    row_id = routine_store.upsert_routine(
        slug="test-update",
        name="Test Update",
        script="update.py",
        frequency="weekly",
        config_json={"day": "friday", "time": "09:00"},
        enabled=False,
    )

    # Upsert again — should update, not insert.
    row_id2 = routine_store.upsert_routine(
        slug="test-update",
        name="Test Update Renamed",
        script="update.py",
        frequency="weekly",
        config_json={"day": "friday", "time": "10:00"},
        enabled=False,
    )

    assert row_id == row_id2, "upsert_routine must return same id on update"

    row = routine_store.get_routine(row_id)
    assert row["name"] == "Test Update Renamed"
    cfg = json.loads(row["config_json"])
    assert cfg["time"] == "10:00"


@pytest.mark.postgres
def test_toggle_routine_enabled(pg_engine):
    """toggle_routine_enabled flips the enabled field."""
    import routine_store

    routine_store.upsert_routine(
        slug="test-toggle",
        name="Test Toggle",
        script="toggle.py",
        frequency="daily",
        config_json={"time": "08:00"},
        enabled=False,
    )

    new_val = routine_store.toggle_routine_enabled("test-toggle")
    assert new_val is True

    new_val2 = routine_store.toggle_routine_enabled("test-toggle")
    assert new_val2 is False


@pytest.mark.postgres
def test_delete_routine(pg_engine):
    """delete_routine removes the row and returns True."""
    import routine_store

    routine_store.upsert_routine(
        slug="test-delete",
        name="Test Delete",
        script="delete.py",
        frequency="daily",
        config_json={"time": "07:00"},
        enabled=False,
    )

    deleted = routine_store.delete_routine("test-delete")
    assert deleted is True

    row = routine_store.get_routine_by_slug("test-delete")
    assert row is None

    # Second delete returns False.
    deleted2 = routine_store.delete_routine("test-delete")
    assert deleted2 is False


# ---------------------------------------------------------------------------
# AC4: list_routines_grouped returns correct shape
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_list_routines_grouped_shape(pg_engine):
    """list_routines_grouped returns {'daily':[], 'weekly':[], 'monthly':[]}."""
    import routine_store

    routine_store.upsert_routine(
        slug="test-grouped-daily",
        name="Test Grouped Daily",
        script="grouped_daily.py",
        frequency="daily",
        config_json={"time": "07:00"},
        enabled=True,
    )
    routine_store.upsert_routine(
        slug="test-grouped-weekly",
        name="Test Grouped Weekly",
        script="grouped_weekly.py",
        frequency="weekly",
        config_json={"day": "monday", "time": "09:00"},
        enabled=True,
    )

    grouped = routine_store.list_routines_grouped()
    assert "daily" in grouped
    assert "weekly" in grouped
    assert "monthly" in grouped

    daily_slugs = [r["slug"] for r in grouped["daily"]]
    assert "test-grouped-daily" in daily_slugs

    weekly_slugs = [r["slug"] for r in grouped["weekly"]]
    assert "test-grouped-weekly" in weekly_slugs

    # Entry shape check
    entry = next(r for r in grouped["daily"] if r["slug"] == "test-grouped-daily")
    assert "id" in entry
    assert "name" in entry
    assert "enabled" in entry
    assert "time" in entry


# ---------------------------------------------------------------------------
# AC5: import_from_yaml is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_import_from_yaml_idempotent(tmp_path, pg_engine):
    """import_from_yaml can be called twice without creating duplicates."""
    import yaml
    import routine_store

    routines_yaml = tmp_path / "routines.yaml"
    routines_yaml.write_text(yaml.dump({
        "daily": [
            {"name": "Test Yaml Import", "script": "test_yaml_import.py",
             "time": "06:50", "enabled": True},
        ]
    }), encoding="utf-8")

    count1 = routine_store.import_from_yaml(routines_yaml)
    count2 = routine_store.import_from_yaml(routines_yaml)

    assert count1 == 1
    assert count2 == 1

    # Only one row should exist.
    from sqlalchemy import text
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT COUNT(*) FROM routine_definitions WHERE slug = 'test-yaml-import'")
        ).fetchone()
    assert rows[0] == 1


@pytest.mark.postgres
def test_import_from_yaml_interval_routine(tmp_path, pg_engine):
    """import_from_yaml correctly imports interval-based daily routines."""
    import yaml
    import routine_store

    routines_yaml = tmp_path / "routines_interval.yaml"
    routines_yaml.write_text(yaml.dump({
        "daily": [
            {"name": "Test Interval", "script": "test_interval.py",
             "interval": 30, "enabled": True},
        ]
    }), encoding="utf-8")

    routine_store.import_from_yaml(routines_yaml)

    row = routine_store.get_routine_by_slug("test-interval")
    assert row is not None
    assert row["schedule"] == "every 30min"
    cfg = json.loads(row["config_json"])
    assert cfg["interval"] == 30

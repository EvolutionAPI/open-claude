"""
tests/routines/test_logs_cleanup_pg.py

TTL cleanup for native logs.

AC1: SQLite mode is a no-op (returns empty dict, touches no tables).
AC-PG: Old rows are deleted; recent rows survive; env overrides change the cutoff;
       forever categories (meeting_transcripts, audit_log, brain_repo_transcripts)
       are never touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest
import sqlalchemy as sa
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_BACKEND = _REPO_ROOT / "dashboard" / "backend"
_ALEMBIC_DIR = _REPO_ROOT / "dashboard" / "alembic"
_ADW_ROUTINES = _REPO_ROOT / "ADWs" / "routines"
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ADW_ROUTINES))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_alembic_upgrade(db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stderr}")


def _make_pg_engine(db_url: str):
    url = db_url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return sa.create_engine(url, pool_pre_ping=True)


def _patch_engine_and_dialect(monkeypatch, engine):
    """Redirect db.engine singleton + config_store.get_dialect to test engine."""
    import db.engine as engine_mod
    # Remove cached module state that may reference the old engine
    for mod in list(sys.modules.keys()):
        if mod in ("logs_cleanup", "config_store"):
            del sys.modules[mod]
    monkeypatch.setattr(engine_mod, "_engine", engine)
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)


# ---------------------------------------------------------------------------
# PG fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_url():
    url = os.environ.get("DATABASE_URL", "")
    if not (url.startswith("postgresql") or url.startswith("postgres://")):
        pytest.skip("Postgres not configured (DATABASE_URL not set or points to SQLite)")
    return url


@pytest.fixture(scope="module")
def pg_engine(pg_url):
    engine = _make_pg_engine(pg_url)
    _run_alembic_upgrade(pg_url)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# PG tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_old_rows_deleted_recent_rows_survive(pg_engine, monkeypatch):
    """Old rows (100d) are deleted; rows 1d old survive."""
    _patch_engine_and_dialect(monkeypatch, pg_engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    old_ts = datetime.now(timezone.utc) - timedelta(days=100)
    recent_ts = datetime.now(timezone.utc) - timedelta(days=1)

    with pg_engine.begin() as conn:
        # Insert one old and one recent routine_run row
        conn.execute(
            text(
                "INSERT INTO routine_runs"
                " (routine_slug, started_at, ended_at, exit_code, stdout, stderr,"
                "  truncated, triggered_by, duration_ms)"
                " VALUES"
                " ('__test_old__', :old, :old, 0, '', '', false, 'test', 0),"
                " ('__test_recent__', :recent, :recent, 0, '', '', false, 'test', 0)"
            ),
            {"old": old_ts, "recent": recent_ts},
        )

    import logs_cleanup
    summary = logs_cleanup.cleanup()

    assert "routine_runs" in summary
    assert summary["routine_runs"] >= 1  # at least the old row was deleted

    with pg_engine.connect() as conn:
        remaining = conn.execute(
            text(
                "SELECT routine_slug FROM routine_runs"
                " WHERE routine_slug IN ('__test_old__', '__test_recent__')"
            )
        ).fetchall()

    slugs = {r[0] for r in remaining}
    assert "__test_recent__" in slugs, "Recent row should survive"
    assert "__test_old__" not in slugs, "Old row should be deleted"

    # Cleanup
    with pg_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM routine_runs WHERE routine_slug LIKE '__test_%'")
        )


@pytest.mark.postgres
def test_skipped_categories_not_touched(pg_engine, monkeypatch):
    """SKIPPED categories (meeting_transcripts, audit_log, brain_repo_transcripts) are never deleted."""
    _patch_engine_and_dialect(monkeypatch, pg_engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    import logs_cleanup

    skipped = logs_cleanup.SKIPPED
    assert "meeting_transcripts" in skipped
    assert "audit_log" in skipped
    assert "brain_repo_transcripts" in skipped

    summary = logs_cleanup.cleanup()

    # None of the skipped categories appear as keys in the summary
    for cat in skipped:
        assert cat not in summary, f"SKIPPED category '{cat}' must not appear in summary"


@pytest.mark.postgres
def test_env_override_respected(pg_engine, monkeypatch):
    """EVONEXUS_LOGS_RETAIN_ROUTINE_RUNS_DAYS overrides the default cutoff.

    Default for routine_runs is 30d. We insert a row that is 35d old.
    With override=180d it survives; with override=10d it is deleted.
    """
    import importlib

    _patch_engine_and_dialect(monkeypatch, pg_engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    # 35 days old — older than default 30d but within 180d override
    ts_35d = datetime.now(timezone.utc) - timedelta(days=35)

    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO routine_runs"
                " (routine_slug, started_at, ended_at, exit_code, stdout, stderr,"
                "  truncated, triggered_by, duration_ms)"
                " VALUES"
                " ('__env_override_test__', :ts, :ts, 0, '', '', false, 'test', 0)"
            ),
            {"ts": ts_35d},
        )

    # With 180d retention, the 35d-old row must survive
    monkeypatch.setenv("EVONEXUS_LOGS_RETAIN_ROUTINE_RUNS_DAYS", "180")
    import logs_cleanup
    importlib.reload(logs_cleanup)
    logs_cleanup.cleanup()

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM routine_runs"
                " WHERE routine_slug = '__env_override_test__'"
            )
        ).fetchone()

    assert row is not None, "Row should survive with 180d retention override"

    # Now switch to 10d override — the 35d-old row should be deleted
    monkeypatch.setenv("EVONEXUS_LOGS_RETAIN_ROUTINE_RUNS_DAYS", "10")
    importlib.reload(logs_cleanup)
    logs_cleanup.cleanup()

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM routine_runs"
                " WHERE routine_slug = '__env_override_test__'"
            )
        ).fetchone()

    assert row is None, "Row should be deleted with 10d retention override"

    monkeypatch.delenv("EVONEXUS_LOGS_RETAIN_ROUTINE_RUNS_DAYS", raising=False)


# ---------------------------------------------------------------------------
# SQLite / AC1 tests
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_cleanup_sqlite_is_noop(monkeypatch, tmp_path):
    """AC1: cleanup() returns empty dict and touches nothing in SQLite mode."""
    sqlite_engine = sa.create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    import db.engine as engine_mod
    for mod in list(sys.modules.keys()):
        if mod in ("logs_cleanup", "config_store"):
            del sys.modules[mod]

    monkeypatch.setattr(engine_mod, "_engine", sqlite_engine)
    monkeypatch.setattr(engine_mod, "get_engine", lambda: sqlite_engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    import logs_cleanup
    result = logs_cleanup.cleanup()

    assert result == {}, f"SQLite mode must return empty dict, got {result!r}"

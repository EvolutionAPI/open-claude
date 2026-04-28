"""
tests/routines/test_daily_outputs_pg.py

daily_output_store — dialect-bifurcated persistence.

AC1:  SQLite mode writes to workspace/daily-logs/ (zero behaviour change).
AC-PG: PG mode inserts a row into daily_outputs table.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
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
sys.path.insert(0, str(_BACKEND))

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


# ---------------------------------------------------------------------------
# PG fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_url():
    """Skip if DATABASE_URL is not set or does not point to Postgres."""
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
def test_write_daily_output_pg_creates_row(pg_engine, pg_url):
    """write_daily_output in PG mode inserts a row into daily_outputs."""
    import importlib
    import db.engine as engine_mod

    # Point the module's engine at the test DB
    test_engine = pg_engine
    with mock.patch.object(engine_mod, "_engine", test_engine):
        import daily_output_store
        importlib.reload(daily_output_store)

        today = date.today()
        identifier = daily_output_store.write_daily_output(
            date=today,
            kind="morning",
            content="# Good Morning\nTest content",
            format="md",
            agent="clawdia-assistant",
        )

    assert identifier.startswith("daily_outputs:"), f"Expected 'daily_outputs:<id>', got {identifier!r}"
    db_id = int(identifier.split(":", 1)[1])

    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, date, kind, agent, format, content FROM daily_outputs WHERE id = :id"),
            {"id": db_id},
        ).fetchone()

    assert row is not None, "Row not found in daily_outputs"
    assert row.kind == "morning"
    assert row.agent == "clawdia-assistant"
    assert row.format == "md"
    assert "Test content" in row.content


@pytest.mark.postgres
def test_list_daily_outputs_pg_ordered_desc(pg_engine, pg_url):
    """list_daily_outputs returns rows ordered by date DESC."""
    import importlib
    import db.engine as engine_mod

    test_engine = pg_engine
    with mock.patch.object(engine_mod, "_engine", test_engine):
        import daily_output_store
        importlib.reload(daily_output_store)

        # Insert two rows with distinct dates
        daily_output_store.write_daily_output(
            date=date(2026, 1, 1),
            kind="eod",
            content="Jan 1 EOD",
            format="md",
        )
        daily_output_store.write_daily_output(
            date=date(2026, 1, 15),
            kind="eod",
            content="Jan 15 EOD",
            format="md",
        )

        rows = daily_output_store.list_daily_outputs(kind="eod", limit=10)

    assert len(rows) >= 2
    # Most recent date should come first
    dates = [r["date"] for r in rows if r.get("kind") == "eod"]
    assert dates == sorted(dates, reverse=True), "Rows not ordered by date DESC"


@pytest.mark.postgres
def test_get_daily_output_pg(pg_engine, pg_url):
    """get_daily_output returns the stored content by identifier."""
    import importlib
    import db.engine as engine_mod

    test_engine = pg_engine
    with mock.patch.object(engine_mod, "_engine", test_engine):
        import daily_output_store
        importlib.reload(daily_output_store)

        identifier = daily_output_store.write_daily_output(
            date=date.today(),
            kind="dashboard",
            content="<html>Dashboard</html>",
            format="html",
            agent="clawdia-assistant",
        )

        result = daily_output_store.get_daily_output(identifier)

    assert result is not None, "get_daily_output returned None"
    assert "Dashboard" in result["content"]
    assert result["format"] == "html"


# ---------------------------------------------------------------------------
# SQLite / filesystem tests (AC1 — regression: files still written on disk)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_write_daily_output_sqlite_creates_file(tmp_path):
    """AC1: SQLite mode writes content to workspace/daily-logs/ file."""
    import importlib

    fake_daily_logs = tmp_path / "workspace" / "daily-logs"
    fake_daily_logs.mkdir(parents=True)

    # Patch DAILY_LOGS_DIR and dialect in daily_output_store
    with mock.patch.dict(os.environ, {}, clear=False):
        # Ensure no DATABASE_URL → SQLite dialect
        os.environ.pop("DATABASE_URL", None)

        import db.engine as engine_mod
        # Force a fresh SQLite engine pointing at tmp_path
        sqlite_engine = sa.create_engine(f"sqlite:///{tmp_path}/test.db")
        with mock.patch.object(engine_mod, "_engine", sqlite_engine):
            import daily_output_store
            importlib.reload(daily_output_store)
            # Override the logs dir to tmp_path
            daily_output_store.DAILY_LOGS_DIR = fake_daily_logs

            identifier = daily_output_store.write_daily_output(
                date=date(2026, 4, 26),
                kind="morning",
                content="# Good Morning SQLite",
                format="md",
            )

    # Identifier is a file path
    assert Path(identifier).exists(), f"Expected file at {identifier}"
    content = Path(identifier).read_text(encoding="utf-8")
    assert "Good Morning SQLite" in content


@pytest.mark.sqlite
def test_list_daily_outputs_sqlite_scans_dir(tmp_path):
    """SQLite list_daily_outputs returns entries from the directory scan."""
    import importlib

    fake_daily_logs = tmp_path / "workspace" / "daily-logs"
    fake_daily_logs.mkdir(parents=True)
    (fake_daily_logs / "[C] 2026-04-26-morning.md").write_text("morning", encoding="utf-8")
    (fake_daily_logs / "[C] 2026-04-25-eod.md").write_text("eod", encoding="utf-8")

    os.environ.pop("DATABASE_URL", None)
    sqlite_engine = sa.create_engine(f"sqlite:///{tmp_path}/test2.db")

    import db.engine as engine_mod
    with mock.patch.object(engine_mod, "_engine", sqlite_engine):
        import daily_output_store
        importlib.reload(daily_output_store)
        daily_output_store.DAILY_LOGS_DIR = fake_daily_logs

        entries = daily_output_store.list_daily_outputs(limit=10)

    assert len(entries) == 2
    paths = [e["path"] for e in entries]
    assert all(Path(p).exists() for p in paths)

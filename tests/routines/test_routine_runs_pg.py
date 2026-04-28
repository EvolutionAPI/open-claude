"""
tests/routines/test_routine_runs_pg.py

Área C — routine_run_store persistence, dialect-bifurcated.

AC1:  SQLite mode writes to log file under ADWs/logs/routines/ (zero behaviour change).
AC-PG: PG mode inserts a row into routine_runs table.
Trunc: stdout/stderr > 1 MB are truncated and truncated=True is set.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def _patch_engine(monkeypatch, engine):
    """Monkeypatch db.engine for a specific engine."""
    import db.engine as engine_mod
    for mod in ("routine_run_store", "config_store"):
        if mod in sys.modules:
            del sys.modules[mod]
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)
    if hasattr(engine_mod, "_engine"):
        monkeypatch.setattr(engine_mod, "_engine", engine)


def _ts_pair(duration_seconds: int = 3):
    """Return (started_at, ended_at) pair with given duration."""
    started = datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)
    ended = started + timedelta(seconds=duration_seconds)
    return started, ended


# ---------------------------------------------------------------------------
# PG tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_persist_routine_run_inserts_row(monkeypatch):
    """PG mode: persist_routine_run writes a row to routine_runs."""
    db_url = os.environ["DATABASE_URL"]
    _run_alembic_upgrade(db_url)
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    started, ended = _ts_pair(5)

    import routine_run_store
    routine_run_store.persist_routine_run(
        routine_slug="good_morning",
        started_at=started,
        ended_at=ended,
        exit_code=0,
        stdout="Good morning output\n",
        stderr="",
        triggered_by="scheduler",
    )

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT routine_slug, exit_code, stdout, stderr, "
                "truncated, triggered_by, duration_ms "
                "FROM routine_runs ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()

    assert row is not None
    assert row[0] == "good_morning"    # routine_slug
    assert row[1] == 0                 # exit_code
    assert "Good morning" in row[2]    # stdout
    assert row[3] == ""                # stderr
    assert row[4] is False             # truncated
    assert row[5] == "scheduler"       # triggered_by
    assert row[6] == 5000              # duration_ms


@pytest.mark.postgres
def test_persist_routine_run_truncation_pg(monkeypatch):
    """PG mode: stdout/stderr > 1 MB are truncated and truncated=True."""
    db_url = os.environ["DATABASE_URL"]
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    started, ended = _ts_pair(1)
    big_stdout = "x" * (1024 * 1024 + 100)

    import routine_run_store
    routine_run_store.persist_routine_run(
        routine_slug="memory_sync",
        started_at=started,
        ended_at=ended,
        exit_code=0,
        stdout=big_stdout,
        stderr="",
        triggered_by="scheduler",
    )

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT truncated, length(stdout) "
                "FROM routine_runs ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()

    assert row[0] is True   # truncated flag set
    # stored length ≤ MAX_LEN + len("\n...[TRUNCATED]")
    assert row[1] <= 1048576 + 20


@pytest.mark.postgres
def test_persist_routine_run_failure_exit_code_pg(monkeypatch):
    """PG mode: non-zero exit_code is stored correctly."""
    db_url = os.environ["DATABASE_URL"]
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    started, ended = _ts_pair(2)

    import routine_run_store
    routine_run_store.persist_routine_run(
        routine_slug="end_of_day",
        started_at=started,
        ended_at=ended,
        exit_code=1,
        stdout="",
        stderr="Error: missing config\n",
        triggered_by="manual",
    )

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT exit_code, stderr, triggered_by "
                "FROM routine_runs ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()

    assert row[0] == 1
    assert "missing config" in row[1]
    assert row[2] == "manual"


# ---------------------------------------------------------------------------
# SQLite / AC1 tests
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_persist_routine_run_sqlite_writes_file(monkeypatch, tmp_path):
    """SQLite mode (AC1): persist_routine_run writes a .log file."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(sqlite_url, connect_args={"check_same_thread": False})

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    log_dir = tmp_path / "routines"
    started, ended = _ts_pair(4)

    import routine_run_store
    monkeypatch.setattr(routine_run_store, "SQLITE_LOG_DIR", log_dir)

    routine_run_store.persist_routine_run(
        routine_slug="weekly_review",
        started_at=started,
        ended_at=ended,
        exit_code=0,
        stdout="All good\n",
        stderr="",
        triggered_by="scheduler",
    )

    files = list(log_dir.glob("weekly_review-*.log"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "All good" in content
    assert "=== stdout ===" in content
    assert "=== stderr ===" in content


@pytest.mark.sqlite
def test_persist_routine_run_sqlite_truncation(monkeypatch, tmp_path):
    """SQLite mode (AC1): oversized stdout is truncated before writing to file."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(sqlite_url, connect_args={"check_same_thread": False})

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    log_dir = tmp_path / "routines"
    big = "y" * (1024 * 1024 + 500)
    started, ended = _ts_pair(1)

    import routine_run_store
    monkeypatch.setattr(routine_run_store, "SQLITE_LOG_DIR", log_dir)

    routine_run_store.persist_routine_run(
        routine_slug="backup",
        started_at=started,
        ended_at=ended,
        exit_code=0,
        stdout=big,
        stderr="",
        triggered_by="scheduler",
    )

    files = list(log_dir.glob("backup-*.log"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "[TRUNCATED]" in content

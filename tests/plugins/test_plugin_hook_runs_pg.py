"""Phase 6 — plugin_hook_runs: dialect-aware persistence.

Tests:
  PG mode:
    - Successful hook run → row in plugin_hook_runs with stdout/stderr/exit_code
    - Stdout > 1 MB → row.truncated = True, stdout truncated at 1 MB + marker
    - Stderr > 1 MB → row.truncated = True, stderr truncated at 1 MB + marker
    - Timed-out hook → row.metadata includes timed_out=True

  SQLite mode (AC1 — invariant):
    - Successful hook run → .log file created in ADWs/logs/plugins/
    - plugin_hook_runs table is NOT queried/written

Markers:
  @pytest.mark.postgres — requires DATABASE_URL pointing to PG (Docker)
  @pytest.mark.sqlite   — SQLite only, no Docker required
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import text as sa_text

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

_ALEMBIC_DIR = REPO_ROOT / "dashboard" / "alembic"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alembic_upgrade(db_url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )


def _make_hook_plugin_dir(tmp_path: Path, slug: str, hook_name: str, script_body: str) -> Path:
    """Create a minimal plugin dir with a hooks/<hook_name>.sh script."""
    plugin_dir = tmp_path / slug
    hooks_dir = plugin_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    script = hooks_dir / f"{hook_name}.sh"
    script.write_text(f"#!/usr/bin/env bash\n{script_body}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return plugin_dir


def _make_in_memory_sqlite_engine_with_log_table() -> sa.Engine:
    """Return a SQLite in-memory engine with plugin_hook_runs table."""
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS plugin_hook_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                hook_name TEXT NOT NULL,
                sha256 TEXT,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME,
                duration_ms INTEGER,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                truncated INTEGER NOT NULL DEFAULT 0,
                metadata TEXT
            )
        """))
    return engine


def _patch_dialect_pg(engine: sa.Engine):
    """Patch plugin_hook_runner so _persist_hook_run sees PostgreSQL dialect + given engine."""
    return [
        patch("plugin_hook_runner._get_dialect_name", return_value="postgresql"),
        patch("plugin_hook_runner._get_db_engine", return_value=engine),
    ]


def _patch_dialect_sqlite(engine: sa.Engine):
    """Patch plugin_hook_runner so _persist_hook_run sees SQLite dialect."""
    return [
        patch("plugin_hook_runner._get_dialect_name", return_value="sqlite"),
        patch("plugin_hook_runner._get_db_engine", return_value=engine),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pg_url():
    """PG DATABASE_URL from env; skip if absent."""
    url = os.environ.get("DATABASE_URL", "")
    if not url or "postgresql" not in url:
        pytest.skip("DATABASE_URL not pointing to PostgreSQL — skipping PG test")
    result = _alembic_upgrade(url)
    assert result.returncode == 0, f"PG alembic upgrade failed:\n{result.stderr}"
    return url


@pytest.fixture()
def pg_engine(pg_url):
    return sa.create_engine(
        pg_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        if pg_url.startswith("postgresql://") and "+psycopg2" not in pg_url
        else pg_url
    )


@pytest.fixture()
def mem_engine():
    """In-memory SQLite engine with plugin_hook_runs table."""
    return _make_in_memory_sqlite_engine_with_log_table()


# ---------------------------------------------------------------------------
# Imports (after sys.path is set)
# ---------------------------------------------------------------------------

from plugin_hook_runner import (  # noqa: E402
    _persist_hook_run,
    run_lifecycle_hook,
)

# ---------------------------------------------------------------------------
# PG mode tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_pg_successful_hook_inserts_row(tmp_path, pg_engine):
    """PG: successful hook run → row in plugin_hook_runs with correct fields."""
    # Delete any leftover rows from prior test runs
    with pg_engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM plugin_hook_runs WHERE slug = 'test-phase6'"))

    plugin_dir = _make_hook_plugin_dir(tmp_path, "test-phase6", "post-install", "echo hello")

    patches = _patch_dialect_pg(pg_engine)
    with patches[0], patches[1]:
        result = run_lifecycle_hook(plugin_dir, "post-install", "test-phase6", timeout=10)

    assert result["ran"] is True
    assert result["exit_code"] == 0

    with pg_engine.connect() as conn:
        row = conn.execute(sa_text(
            "SELECT slug, hook_name, exit_code, stdout, stderr, truncated "
            "FROM plugin_hook_runs WHERE slug = 'test-phase6' ORDER BY id DESC LIMIT 1"
        )).fetchone()

    assert row is not None, "Expected a row in plugin_hook_runs"
    assert row[0] == "test-phase6"
    assert row[1] == "post-install"
    assert row[2] == 0
    assert "hello" in (row[3] or "")
    assert row[5] is False or row[5] == 0  # truncated = False


@pytest.mark.postgres
def test_pg_hook_row_has_duration_ms(tmp_path, pg_engine):
    """PG: row includes a positive duration_ms."""
    with pg_engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM plugin_hook_runs WHERE slug = 'test-phase6-dur'"))

    plugin_dir = _make_hook_plugin_dir(tmp_path, "test-phase6-dur", "post-install", "echo dur")

    patches = _patch_dialect_pg(pg_engine)
    with patches[0], patches[1]:
        run_lifecycle_hook(plugin_dir, "post-install", "test-phase6-dur", timeout=10)

    with pg_engine.connect() as conn:
        row = conn.execute(sa_text(
            "SELECT duration_ms FROM plugin_hook_runs "
            "WHERE slug = 'test-phase6-dur' ORDER BY id DESC LIMIT 1"
        )).fetchone()

    assert row is not None
    assert isinstance(row[0], int)
    assert row[0] >= 0


@pytest.mark.postgres
def test_pg_truncate_stdout(pg_engine):
    """PG: stdout > 1 MB → row.truncated = True, stdout cut at 1 MB + marker."""
    with pg_engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM plugin_hook_runs WHERE slug = 'test-trunc-stdout'"))

    big_stdout = "x" * (1024 * 1024 + 500)
    started = datetime(2026, 1, 1, 12, 0, 0)
    ended = datetime(2026, 1, 1, 12, 0, 1)

    patches = _patch_dialect_pg(pg_engine)
    with patches[0], patches[1]:
        _persist_hook_run(
            slug="test-trunc-stdout",
            hook_name="post-install",
            timestamp="20260101T120000Z",
            script_sha256="abc123",
            started_at=started,
            ended_at=ended,
            exit_code=0,
            stdout=big_stdout,
            stderr="",
            timed_out=False,
        )

    with pg_engine.connect() as conn:
        row = conn.execute(sa_text(
            "SELECT stdout, truncated FROM plugin_hook_runs "
            "WHERE slug = 'test-trunc-stdout' ORDER BY id DESC LIMIT 1"
        )).fetchone()

    assert row is not None
    stored_stdout = row[0]
    truncated = row[1]

    assert truncated is True or truncated == 1, "truncated must be True"
    assert len(stored_stdout) <= 1024 * 1024 + len("\n... [TRUNCATED]") + 10
    assert stored_stdout.endswith("\n... [TRUNCATED]")


@pytest.mark.postgres
def test_pg_truncate_stderr(pg_engine):
    """PG: stderr > 1 MB → row.truncated = True, stderr cut at 1 MB + marker."""
    with pg_engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM plugin_hook_runs WHERE slug = 'test-trunc-stderr'"))

    big_stderr = "e" * (1024 * 1024 + 100)
    started = datetime(2026, 1, 1, 13, 0, 0)
    ended = datetime(2026, 1, 1, 13, 0, 1)

    patches = _patch_dialect_pg(pg_engine)
    with patches[0], patches[1]:
        _persist_hook_run(
            slug="test-trunc-stderr",
            hook_name="post-install",
            timestamp="20260101T130000Z",
            script_sha256="def456",
            started_at=started,
            ended_at=ended,
            exit_code=0,
            stdout="",
            stderr=big_stderr,
            timed_out=False,
        )

    with pg_engine.connect() as conn:
        row = conn.execute(sa_text(
            "SELECT stderr, truncated FROM plugin_hook_runs "
            "WHERE slug = 'test-trunc-stderr' ORDER BY id DESC LIMIT 1"
        )).fetchone()

    assert row is not None
    assert row[1] is True or row[1] == 1, "truncated must be True"
    assert row[0].endswith("\n... [TRUNCATED]")


@pytest.mark.postgres
def test_pg_timed_out_hook_metadata(tmp_path, pg_engine):
    """PG: timed-out hook sets metadata.timed_out=True."""
    with pg_engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM plugin_hook_runs WHERE slug = 'test-timeout-meta'"))

    started = datetime(2026, 1, 1, 14, 0, 0)
    ended = datetime(2026, 1, 1, 14, 0, 5)

    patches = _patch_dialect_pg(pg_engine)
    with patches[0], patches[1]:
        _persist_hook_run(
            slug="test-timeout-meta",
            hook_name="post-install",
            timestamp="20260101T140000Z",
            script_sha256="fff000",
            started_at=started,
            ended_at=ended,
            exit_code=None,
            stdout="partial",
            stderr="",
            timed_out=True,
            metadata={"timeout_seconds": 60},
        )

    with pg_engine.connect() as conn:
        row = conn.execute(sa_text(
            "SELECT metadata FROM plugin_hook_runs "
            "WHERE slug = 'test-timeout-meta' ORDER BY id DESC LIMIT 1"
        )).fetchone()

    assert row is not None
    meta = json.loads(row[0])
    assert meta.get("timed_out") is True
    assert meta.get("timeout_seconds") == 60


# ---------------------------------------------------------------------------
# SQLite mode tests (AC1 — invariant: SQLite behaviour unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_successful_hook_creates_log_file(tmp_path):
    """SQLite: successful hook run → .log file in ADWs/logs/plugins/."""
    log_dir = tmp_path / "ADWs" / "logs" / "plugins"

    plugin_dir = _make_hook_plugin_dir(tmp_path, "test-sqlite-hook", "post-install", "echo sqlite-ok")

    # Patch PLUGIN_LOGS_DIR so logs land in tmp_path instead of repo root
    with patch("plugin_hook_runner.PLUGIN_LOGS_DIR", log_dir):
        # Use mem_engine for dialect patching (won't be written to in SQLite mode)
        mem_engine = _make_in_memory_sqlite_engine_with_log_table()
        patches = _patch_dialect_sqlite(mem_engine)
        with patches[0], patches[1]:
            result = run_lifecycle_hook(plugin_dir, "post-install", "test-sqlite-hook", timeout=10)

    assert result["ran"] is True
    assert result["exit_code"] == 0
    assert result["log_path"] is not None

    # Log file must exist
    log_files = list(log_dir.glob("test-sqlite-hook-post-install-*.log"))
    assert len(log_files) == 1, f"Expected 1 log file, found: {log_files}"

    content = log_files[0].read_text(encoding="utf-8")
    assert "plugin: test-sqlite-hook" in content
    assert "hook: post-install" in content
    assert "sqlite-ok" in content


@pytest.mark.sqlite
def test_sqlite_hook_does_not_write_to_db_table(tmp_path):
    """SQLite: hook run does NOT write to plugin_hook_runs (AC1)."""
    log_dir = tmp_path / "ADWs" / "logs" / "plugins"
    plugin_dir = _make_hook_plugin_dir(tmp_path, "test-no-db", "post-install", "echo noop")

    mem_engine = _make_in_memory_sqlite_engine_with_log_table()

    with patch("plugin_hook_runner.PLUGIN_LOGS_DIR", log_dir):
        patches = _patch_dialect_sqlite(mem_engine)
        with patches[0], patches[1]:
            run_lifecycle_hook(plugin_dir, "post-install", "test-no-db", timeout=10)

    with mem_engine.connect() as conn:
        count = conn.execute(sa_text("SELECT COUNT(*) FROM plugin_hook_runs")).scalar()

    assert count == 0, f"SQLite mode must not write to plugin_hook_runs; got {count} rows"


@pytest.mark.sqlite
def test_sqlite_truncation_still_applies_to_log_file(tmp_path):
    """SQLite: stdout > 1 MB is truncated in the log file content."""
    log_dir = tmp_path / "ADWs" / "logs" / "plugins"
    log_dir.mkdir(parents=True, exist_ok=True)

    big_stdout = "x" * (1024 * 1024 + 200)
    started = datetime(2026, 1, 1, 10, 0, 0)
    ended = datetime(2026, 1, 1, 10, 0, 1)

    mem_engine = _make_in_memory_sqlite_engine_with_log_table()

    with patch("plugin_hook_runner.PLUGIN_LOGS_DIR", log_dir):
        patches = _patch_dialect_sqlite(mem_engine)
        with patches[0], patches[1]:
            _persist_hook_run(
                slug="test-sqlite-trunc",
                hook_name="post-install",
                timestamp="20260101T100000Z",
                script_sha256="aaa111",
                started_at=started,
                ended_at=ended,
                exit_code=0,
                stdout=big_stdout,
                stderr="",
                timed_out=False,
            )

    log_files = list(log_dir.glob("test-sqlite-trunc-*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "[TRUNCATED]" in content

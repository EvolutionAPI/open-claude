"""Tests for migration 0010 — seed default configs.

These tests verify that migration 0010 populates runtime_configs and
llm_providers from the .example files, and that the migration is idempotent.

Marked @pytest.mark.postgres — skipped when DATABASE_URL is absent or
points to SQLite (see conftest.py).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKSPACE = Path(__file__).resolve().parents[2]


def _pg_engine_from_url(url: str):
    """Build a psycopg2-backed engine from a DATABASE_URL."""
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


def _run_alembic(url: str, command: str = "upgrade head") -> None:
    """Invoke alembic via subprocess with the given DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    args = command.split()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "dashboard/alembic/alembic.ini"] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_WORKSPACE),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {command} failed:\n{result.stdout}\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql", "postgres://")):
        pytest.skip("Postgres DATABASE_URL not set")
    return url


@pytest.fixture
def pg_db(pg_url):
    """Apply alembic upgrade head and yield the engine. Tears down via downgrade."""
    _run_alembic(pg_url, "upgrade head")
    engine = _pg_engine_from_url(pg_url)
    yield engine
    engine.dispose()
    # Best-effort downgrade to clean state; non-fatal if it fails.
    try:
        _run_alembic(pg_url, "downgrade base")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_migration_0010_populates_runtime_configs(pg_db):
    """After upgrade head, runtime_configs has workspace.* keys seeded."""
    with pg_db.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM runtime_configs WHERE key LIKE 'workspace.%'")
        ).scalar()
    # workspace.example.yaml has at least workspace.name, workspace.timezone,
    # workspace.language, workspace.owner, workspace.company → 5+ keys
    assert count >= 5, f"Expected >= 5 workspace.* keys, got {count}"


@pytest.mark.postgres
def test_migration_0010_populates_llm_providers(pg_db):
    """After upgrade head, llm_providers has at least the anthropic provider."""
    with pg_db.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM llm_providers")
        ).scalar()
        slugs = [
            r[0] for r in conn.execute(
                text("SELECT slug FROM llm_providers ORDER BY slug")
            ).fetchall()
        ]
    assert count >= 1, f"Expected >= 1 provider, got {count}"
    assert "anthropic" in slugs, f"Expected anthropic in providers, got {slugs}"


@pytest.mark.postgres
def test_migration_0010_populates_active_provider(pg_db):
    """After upgrade head, runtime_configs has active_provider key."""
    import json
    with pg_db.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM runtime_configs WHERE key = 'active_provider'")
        ).fetchone()
    assert row is not None, "active_provider not found in runtime_configs"
    assert json.loads(row[0]) == "anthropic"


@pytest.mark.postgres
def test_migration_0010_idempotent(pg_url, pg_db):
    """Running upgrade head twice leaves the DB in the same state (no duplicates)."""
    with pg_db.connect() as conn:
        count_before = conn.execute(
            text("SELECT COUNT(*) FROM runtime_configs WHERE key LIKE 'workspace.%'")
        ).scalar()
        providers_before = conn.execute(
            text("SELECT COUNT(*) FROM llm_providers")
        ).scalar()

    # Run upgrade head again — should be a no-op (already at head).
    _run_alembic(pg_url, "upgrade head")

    with pg_db.connect() as conn:
        count_after = conn.execute(
            text("SELECT COUNT(*) FROM runtime_configs WHERE key LIKE 'workspace.%'")
        ).scalar()
        providers_after = conn.execute(
            text("SELECT COUNT(*) FROM llm_providers")
        ).scalar()

    assert count_after == count_before, (
        f"runtime_configs duplicated: {count_before} → {count_after}"
    )
    assert providers_after == providers_before, (
        f"llm_providers duplicated: {providers_before} → {providers_after}"
    )

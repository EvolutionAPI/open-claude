"""config_store — dialect-bifurcation tests.

Verifies that get_config / set_config / list_configs work correctly on both
SQLite (YAML files) and PostgreSQL (runtime_configs table).

Backend selection:
  - SQLite: always available; spins up a tmp_path with fresh alembic schema.
  - Postgres: available when DATABASE_URL env var points to a reachable PG.
    Skipped automatically when PG is absent (CI sqlite-only job).

Bootstrap strategy: matches test_atomic_checkout.py — run `alembic upgrade head`
via subprocess before each engine fixture so the schema is guaranteed fresh.

Usage:
    # SQLite only (no Docker needed)
    pytest tests/db/test_config_store.py -m 'not postgres' -v

    # Postgres only
    DATABASE_URL=postgresql://postgres:test@localhost:55460/postgres \\
        pytest tests/db/test_config_store.py -m postgres -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import sqlalchemy as sa
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup — ensure dashboard/backend is importable
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
    assert result.returncode == 0, (
        f"alembic upgrade failed for {db_url}:\n{result.stderr}"
    )


def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_env(tmp_path):
    """SQLite engine + isolated config dir, schema migrated to head."""
    db_url = f"sqlite:///{tmp_path}/config_store_test.db"
    _run_alembic_upgrade(db_url)
    engine = sa.create_engine(db_url, connect_args={"check_same_thread": False})

    # Each test gets a private config directory so YAML writes don't interfere.
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    yield {"engine": engine, "db_url": db_url, "config_dir": config_dir}
    engine.dispose()


@pytest.fixture
def pg_env():
    """PG engine, schema migrated to head. Skipped if PG unreachable."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not (raw_url.startswith("postgresql") or raw_url.startswith("postgres://")):
        pytest.skip("Postgres not configured (DATABASE_URL not set to PG)")

    try:
        url = _norm_pg_url(raw_url)
        eng = sa.create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")

    _run_alembic_upgrade(raw_url)
    # Clean out any leftover rows from previous runs.
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))

    yield {"engine": eng, "db_url": raw_url}
    # Cleanup after test.
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))
    eng.dispose()


# ---------------------------------------------------------------------------
# Helper: patch config_store module to use a specific engine + config dir
# ---------------------------------------------------------------------------

def _make_config_store(db_url: str, config_dir: Path | None = None):
    """Return a fresh config_store module patched to the given engine/config."""
    import importlib
    import db.engine as engine_mod

    # Re-create a fresh engine for this URL.
    raw = db_url
    is_pg = raw.startswith("postgresql") or raw.startswith("postgres://")
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg2://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://") and "+psycopg2" not in raw:
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)

    if is_pg:
        engine = sa.create_engine(raw, pool_pre_ping=True)
    else:
        engine = sa.create_engine(
            db_url, connect_args={"check_same_thread": False}
        )

    # Reload config_store with patched engine.
    if "config_store" in sys.modules:
        del sys.modules["config_store"]

    patches = {"db.engine.get_engine": lambda: engine}
    if config_dir is not None:
        patches["config_store.CONFIG_DIR"] = config_dir

    import config_store as cs

    # Monkeypatch get_engine inside the already-imported module.
    cs_engine_patch = mock.patch.object(
        sys.modules["db.engine"], "_engine", engine
    )
    cs_engine_patch.start()

    # Also patch get_engine to return our engine directly.
    original_get_engine = engine_mod.get_engine

    def _patched_get_engine():
        return engine

    engine_mod.get_engine = _patched_get_engine

    if config_dir is not None:
        cs.CONFIG_DIR = config_dir

    yield cs

    engine_mod.get_engine = original_get_engine
    cs_engine_patch.stop()
    engine.dispose()


@pytest.fixture
def cs_sqlite(sqlite_env):
    """config_store patched to the SQLite test engine + isolated config dir."""
    yield from _make_config_store(
        sqlite_env["db_url"], config_dir=sqlite_env["config_dir"]
    )


@pytest.fixture
def cs_pg(pg_env):
    """config_store patched to the PG test engine."""
    yield from _make_config_store(pg_env["db_url"])


# ---------------------------------------------------------------------------
# Test class — same assertions run on both backends via parametrisation
# ---------------------------------------------------------------------------

class TestConfigStoreSQLite:
    """SQLite backend tests."""

    def test_get_missing_returns_default(self, cs_sqlite):
        assert cs_sqlite.get_config("nonexistent.key", "fallback") == "fallback"

    def test_get_missing_no_default_returns_none(self, cs_sqlite):
        assert cs_sqlite.get_config("nonexistent.key") is None

    def test_set_then_get(self, cs_sqlite):
        cs_sqlite.set_config("workspace.name", "Test Workspace")
        assert cs_sqlite.get_config("workspace.name") == "Test Workspace"

    def test_set_overwrites(self, cs_sqlite):
        cs_sqlite.set_config("workspace.name", "A")
        cs_sqlite.set_config("workspace.name", "B")
        assert cs_sqlite.get_config("workspace.name") == "B"

    def test_list_with_prefix(self, cs_sqlite):
        cs_sqlite.set_config("workspace.name", "X")
        cs_sqlite.set_config("workspace.timezone", "BRT")
        cs_sqlite.set_config("workspace.owner", "davidson")
        result = cs_sqlite.list_configs("workspace.")
        assert "workspace.name" in result
        assert "workspace.timezone" in result
        assert "workspace.owner" in result

    def test_list_prefix_excludes_other(self, cs_sqlite):
        cs_sqlite.set_config("workspace.name", "X")
        # dashboard.* written to a separate file
        cs_sqlite.set_config("dashboard.port", 8080)
        ws = cs_sqlite.list_configs("workspace.")
        dash = cs_sqlite.list_configs("dashboard.")
        assert "workspace.name" in ws
        assert "dashboard.port" not in ws
        assert "dashboard.port" in dash

    def test_complex_value_list(self, cs_sqlite):
        cs_sqlite.set_config("workspace.tags", ["a", "b", "c"])
        assert cs_sqlite.get_config("workspace.tags") == ["a", "b", "c"]

    def test_complex_value_dict(self, cs_sqlite):
        cs_sqlite.set_config("workspace.meta", {"k": "v", "n": 42})
        assert cs_sqlite.get_config("workspace.meta") == {"k": "v", "n": 42}

    def test_set_with_actor_id_no_error(self, cs_sqlite):
        # SQLite path ignores actor_id — should not raise.
        cs_sqlite.set_config("workspace.name", "X", actor_id=1)
        assert cs_sqlite.get_config("workspace.name") == "X"

    def test_list_empty_prefix_returns_all(self, cs_sqlite):
        cs_sqlite.set_config("workspace.name", "W")
        cs_sqlite.set_config("dashboard.port", 8080)
        all_keys = cs_sqlite.list_configs("")
        assert "workspace.name" in all_keys
        assert "dashboard.port" in all_keys


@pytest.mark.postgres
class TestConfigStorePostgres:
    """PostgreSQL backend tests."""

    def test_get_missing_returns_default(self, cs_pg):
        assert cs_pg.get_config("nonexistent.key.pg", "fallback") == "fallback"

    def test_get_missing_no_default_returns_none(self, cs_pg):
        assert cs_pg.get_config("nonexistent.key.pg") is None

    def test_set_then_get(self, cs_pg):
        cs_pg.set_config("workspace.name", "PG Test Workspace")
        assert cs_pg.get_config("workspace.name") == "PG Test Workspace"

    def test_set_overwrites(self, cs_pg):
        cs_pg.set_config("workspace.name", "A")
        cs_pg.set_config("workspace.name", "B")
        assert cs_pg.get_config("workspace.name") == "B"

    def test_set_increments_version(self, cs_pg):
        cs_pg.set_config("workspace.name", "V1")
        with cs_pg.get_engine().connect() as conn:
            v1 = conn.execute(
                text("SELECT version FROM runtime_configs WHERE key = 'workspace.name'")
            ).scalar()
        cs_pg.set_config("workspace.name", "V2")
        with cs_pg.get_engine().connect() as conn:
            v2 = conn.execute(
                text("SELECT version FROM runtime_configs WHERE key = 'workspace.name'")
            ).scalar()
        assert v2 == v1 + 1

    def test_list_with_prefix(self, cs_pg):
        cs_pg.set_config("workspace.name", "X")
        cs_pg.set_config("workspace.timezone", "BRT")
        cs_pg.set_config("dashboard.port", 8080)
        result = cs_pg.list_configs("workspace.")
        assert "workspace.name" in result
        assert "workspace.timezone" in result
        assert "dashboard.port" not in result

    def test_list_empty_prefix_returns_all(self, cs_pg):
        cs_pg.set_config("workspace.name", "W")
        cs_pg.set_config("dashboard.port", 8080)
        all_keys = cs_pg.list_configs("")
        assert "workspace.name" in all_keys
        assert "dashboard.port" in all_keys

    def test_complex_value_list(self, cs_pg):
        cs_pg.set_config("workspace.tags", ["a", "b", "c"])
        assert cs_pg.get_config("workspace.tags") == ["a", "b", "c"]

    def test_complex_value_dict(self, cs_pg):
        cs_pg.set_config("workspace.meta", {"k": "v", "n": 42})
        assert cs_pg.get_config("workspace.meta") == {"k": "v", "n": 42}

    def test_set_with_actor_id(self, cs_pg):
        cs_pg.set_config("workspace.name", "X", actor_id=None)
        assert cs_pg.get_config("workspace.name") == "X"

    def test_get_returns_correct_type_int(self, cs_pg):
        cs_pg.set_config("dashboard.port", 8080)
        val = cs_pg.get_config("dashboard.port")
        assert val == 8080
        assert isinstance(val, int)

    def test_get_returns_correct_type_bool(self, cs_pg):
        cs_pg.set_config("dashboard.chat.trustMode", True)
        val = cs_pg.get_config("dashboard.chat.trustMode")
        assert val is True

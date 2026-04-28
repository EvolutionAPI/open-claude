"""
tests/backend/test_settings_pg.py

AC3 — Workspace settings in PG mode persist to runtime_configs DB.
AC9 — Provider switch in PG mode persists to DB (not providers.json).
AC1 — SQLite regression: existing YAML-based paths still work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    assert result.returncode == 0, (
        f"alembic upgrade failed:\n{result.stderr}"
    )


def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_engine():
    """Live PG engine with fresh schema. Skipped if PG not configured."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not (raw_url.startswith("postgresql") or raw_url.startswith("postgres://")):
        pytest.skip("Postgres not configured (DATABASE_URL not set to PG)")

    url = _norm_pg_url(raw_url)
    try:
        eng = sa.create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")

    _run_alembic_upgrade(raw_url)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))
        conn.execute(text("DELETE FROM llm_providers"))

    yield eng

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))
        conn.execute(text("DELETE FROM llm_providers"))
    eng.dispose()


@pytest.fixture
def sqlite_engine(tmp_path):
    """SQLite engine with migrated schema."""
    db_url = f"sqlite:///{tmp_path}/test_settings.db"
    _run_alembic_upgrade(db_url)
    eng = sa.create_engine(db_url, connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


def _patch_engine(monkeypatch, engine):
    """Monkeypatch db.engine so config_store / provider_store use our engine."""
    import db.engine as engine_mod

    # Remove cached modules so they re-import with patched engine.
    for mod in ("config_store", "provider_store"):
        if mod in sys.modules:
            del sys.modules[mod]

    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)
    # Also ensure cached _engine is replaced.
    if hasattr(engine_mod, "_engine"):
        monkeypatch.setattr(engine_mod, "_engine", engine)


# ---------------------------------------------------------------------------
# AC3 — Workspace edit in PG persists to DB
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestWorkspacePG:
    def test_set_and_get_workspace_name(self, pg_engine, monkeypatch):
        """set_config('workspace.name', ...) round-trips via DB."""
        _patch_engine(monkeypatch, pg_engine)
        import config_store as cs

        cs.set_config("workspace.name", "My PG Workspace")
        assert cs.get_config("workspace.name") == "My PG Workspace"

    def test_workspace_row_in_db(self, pg_engine, monkeypatch):
        """After set_config, runtime_configs table has the row."""
        _patch_engine(monkeypatch, pg_engine)
        import config_store as cs

        cs.set_config("workspace.owner", "davidson")
        with pg_engine.connect() as conn:
            val = conn.execute(
                text("SELECT value FROM runtime_configs WHERE key = 'workspace.owner'")
            ).scalar()
        assert json.loads(val) == "davidson"

    def test_list_configs_workspace_prefix(self, pg_engine, monkeypatch):
        """list_configs('workspace.') returns only workspace.* keys."""
        _patch_engine(monkeypatch, pg_engine)
        import config_store as cs

        cs.set_config("workspace.name", "X")
        cs.set_config("workspace.timezone", "BRT")
        cs.set_config("dashboard.port", 8080)

        ws = cs.list_configs("workspace.")
        assert "workspace.name" in ws
        assert "workspace.timezone" in ws
        assert "dashboard.port" not in ws

    def test_update_workspace_overwrites(self, pg_engine, monkeypatch):
        """Second set_config overwrites the value (version increments)."""
        _patch_engine(monkeypatch, pg_engine)
        import config_store as cs

        cs.set_config("workspace.name", "old")
        cs.set_config("workspace.name", "new")
        assert cs.get_config("workspace.name") == "new"


# ---------------------------------------------------------------------------
# AC9 — Provider switch in PG persists to DB, providers.json untouched
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestProviderStorePG:
    def _seed_anthropic(self, engine):
        """Insert minimal anthropic row so set_active_provider validates OK."""
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO llm_providers (slug, name, cli_command, env_vars)
                    VALUES ('anthropic', 'Anthropic', 'claude', '{}')
                    ON CONFLICT (slug) DO NOTHING
                """)
            )

    def test_set_active_provider_writes_db(self, pg_engine, monkeypatch, tmp_path):
        """set_active_provider('anthropic') stores value in runtime_configs."""
        _patch_engine(monkeypatch, pg_engine)
        self._seed_anthropic(pg_engine)
        import provider_store as ps

        ps.set_active_provider("anthropic")

        import config_store as cs
        assert cs.get_config("active_provider") == "anthropic"

    def test_set_active_provider_does_not_touch_json(self, pg_engine, monkeypatch, tmp_path):
        """PG mode never writes providers.json."""
        _patch_engine(monkeypatch, pg_engine)
        self._seed_anthropic(pg_engine)
        import provider_store as ps
        import provider_store as ps_mod

        providers_file = tmp_path / "providers.json"
        # Patch the file path to a tmp location so we can detect writes.
        monkeypatch.setattr(ps_mod, "_PROVIDERS_FILE", providers_file)

        ps.set_active_provider("anthropic")

        assert not providers_file.exists(), "PG mode must NOT write providers.json"

    def test_update_provider_config_writes_db(self, pg_engine, monkeypatch):
        """update_provider_config merges env_vars into llm_providers row."""
        _patch_engine(monkeypatch, pg_engine)
        # Seed a provider row.
        with pg_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO llm_providers (slug, name, cli_command, env_vars)
                    VALUES ('openai', 'OpenAI', 'openclaude', '{"OPENAI_API_KEY": ""}')
                    ON CONFLICT (slug) DO NOTHING
                """)
            )
        import provider_store as ps

        ps.update_provider_config("openai", {"OPENAI_API_KEY": "sk-test-123"})

        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT env_vars FROM llm_providers WHERE slug = 'openai'")
            ).fetchone()
        stored = json.loads(row.env_vars)
        assert stored["OPENAI_API_KEY"] == "sk-test-123"

    def test_list_providers_returns_canonical_shape(self, pg_engine, monkeypatch):
        """list_providers() returns {active_provider, providers: {...}} shape."""
        _patch_engine(monkeypatch, pg_engine)
        self._seed_anthropic(pg_engine)

        import provider_store as ps
        import config_store as cs
        cs.set_config("active_provider", "anthropic")

        result = ps.list_providers()
        assert "active_provider" in result
        assert "providers" in result
        assert "anthropic" in result["providers"]


# ---------------------------------------------------------------------------
# AC1 — SQLite regression: YAML-based paths still work
# ---------------------------------------------------------------------------

class TestWorkspaceSQLiteRegression:
    """Ensure SQLite (YAML) path is unaffected by the refactor."""

    def test_set_and_get_sqlite(self, sqlite_engine, tmp_path, monkeypatch):
        """config_store read/write works on SQLite with a real YAML file."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: sqlite_engine)
        if hasattr(engine_mod, "_engine"):
            monkeypatch.setattr(engine_mod, "_engine", sqlite_engine)
        for mod in ("config_store",):
            if mod in sys.modules:
                del sys.modules[mod]

        import config_store as cs
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        cs.CONFIG_DIR = config_dir

        cs.set_config("workspace.name", "SQLite Workspace")
        assert cs.get_config("workspace.name") == "SQLite Workspace"

    def test_provider_store_sqlite_reads_json(self, sqlite_engine, tmp_path, monkeypatch):
        """In SQLite mode, provider_store reads from providers.json."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: sqlite_engine)
        if hasattr(engine_mod, "_engine"):
            monkeypatch.setattr(engine_mod, "_engine", sqlite_engine)
        for mod in ("config_store", "provider_store"):
            if mod in sys.modules:
                del sys.modules[mod]

        import provider_store as ps

        providers_file = tmp_path / "providers.json"
        providers_file.write_text(json.dumps({
            "active_provider": "anthropic",
            "providers": {"anthropic": {"name": "Anthropic", "cli_command": "claude", "env_vars": {}}},
        }), encoding="utf-8")
        monkeypatch.setattr(ps, "_PROVIDERS_FILE", providers_file)

        result = ps.list_providers()
        assert result["active_provider"] == "anthropic"
        assert "anthropic" in result["providers"]

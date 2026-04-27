"""Tests for query portability — verifies that the migrated queries execute
without syntax errors on both SQLite and PostgreSQL backends.

These tests intentionally avoid complex assertions (covered by feature tests);
they only verify the queries execute cleanly and return expected types.

Coverage:
- ticket_janitor SELECT (no datetime() arithmetic)
- mcp_servers.py enabled IS TRUE pattern (SQLite: truthy; PG: native bool)
- claude_hook_dispatcher.py enabled IS TRUE pattern
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(tmp_path):
    """SQLite in-memory engine with tickets + plugins_installed schema."""
    from sqlalchemy import create_engine
    _engine = create_engine(
        f"sqlite:///{tmp_path}/portability_test.db",
        connect_args={"check_same_thread": False},
    )
    _setup_schema(_engine)
    yield _engine
    _engine.dispose()


@pytest.fixture
def pg_engine():
    """Postgres engine — only usable when DATABASE_URL points to PG."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not (db_url.startswith("postgresql") or db_url.startswith("postgres://")):
        pytest.skip("Postgres not configured (DATABASE_URL not set)")
    from sqlalchemy import create_engine
    if db_url.startswith("postgres://"):
        db_url = "postgresql+psycopg2://" + db_url[len("postgres://"):]
    elif db_url.startswith("postgresql://") and "+psycopg2" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    _engine = create_engine(db_url, pool_pre_ping=True)
    _setup_schema(_engine)
    yield _engine
    with _engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS plugins_installed CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS tickets CASCADE"))
        conn.commit()
    _engine.dispose()


def _setup_schema(engine) -> None:
    """Create minimal tables needed for portability tests."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                locked_at TEXT,
                locked_by TEXT,
                lock_timeout_seconds INTEGER
            )
        """))
        # Use dialect-portable BOOLEAN (SQLAlchemy maps to INTEGER in SQLite)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plugins_installed (
                slug TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                status TEXT DEFAULT 'active',
                manifest_json TEXT,
                capabilities_disabled TEXT
            )
        """))
        conn.commit()


# ---------------------------------------------------------------------------
# Janitor SELECT portability
# ---------------------------------------------------------------------------

class TestJanitorQueryPortability:

    def test_janitor_select_runs_on_sqlite(self, engine):
        """The janitor's portable SELECT runs on SQLite without error."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, locked_by, locked_at, "
                    "COALESCE(lock_timeout_seconds, 1800) AS timeout_secs "
                    "FROM tickets WHERE locked_at IS NOT NULL"
                )
            ).fetchall()
        assert isinstance(rows, list)

    @pytest.mark.postgres
    def test_janitor_select_runs_on_pg(self, pg_engine):
        """The janitor's portable SELECT runs on PostgreSQL without error."""
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, locked_by, locked_at, "
                    "COALESCE(lock_timeout_seconds, 1800) AS timeout_secs "
                    "FROM tickets WHERE locked_at IS NOT NULL"
                )
            ).fetchall()
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# Boolean IS TRUE portability
# ---------------------------------------------------------------------------

class TestBooleanIsTruePortability:

    def _insert_plugin(self, conn, slug: str, enabled: bool, status: str = "active") -> None:
        conn.execute(
            text("INSERT INTO plugins_installed (slug, enabled, status, manifest_json) "
                 "VALUES (:slug, :enabled, :status, '{}')"),
            {"slug": slug, "enabled": enabled, "status": status},
        )

    def test_is_true_finds_enabled_on_sqlite(self, engine):
        """enabled IS TRUE matches rows with enabled=1 on SQLite."""
        with engine.connect() as conn:
            self._insert_plugin(conn, "plugin-a", True)
            self._insert_plugin(conn, "plugin-b", False)
            conn.commit()

            rows = conn.execute(
                text("SELECT slug FROM plugins_installed WHERE enabled IS TRUE AND status = 'active'")
            ).fetchall()

        slugs = [r[0] for r in rows]
        assert "plugin-a" in slugs
        assert "plugin-b" not in slugs

    def test_is_true_empty_when_none_enabled_on_sqlite(self, engine):
        """enabled IS TRUE returns nothing when all rows are disabled."""
        with engine.connect() as conn:
            self._insert_plugin(conn, "plugin-c", False)
            conn.commit()

            rows = conn.execute(
                text("SELECT slug FROM plugins_installed WHERE enabled IS TRUE")
            ).fetchall()

        assert rows == []

    @pytest.mark.postgres
    def test_is_true_finds_enabled_on_pg(self, pg_engine):
        """enabled IS TRUE matches rows with enabled=true on PostgreSQL."""
        with pg_engine.connect() as conn:
            self._insert_plugin(conn, "plugin-pg-a", True)
            self._insert_plugin(conn, "plugin-pg-b", False)
            conn.commit()

            rows = conn.execute(
                text("SELECT slug FROM plugins_installed WHERE enabled IS TRUE AND status = 'active'")
            ).fetchall()

        slugs = [r[0] for r in rows]
        assert "plugin-pg-a" in slugs
        assert "plugin-pg-b" not in slugs

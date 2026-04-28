"""Tests for --skip-incompatible-plugins flag.

Uses SQLite→SQLite to avoid requiring a live Postgres instance.
The plugin-table detection logic (_get_plugin_tables) uses sqlite_master,
which works identically to the real production path.
The skip_incompatible_plugins=True path is tested end-to-end via the
migrate() function; the fail-fast (skip_incompatible_plugins=False) path
is tested by mocking _check_plugin_compat to return a non-empty list.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

from dashboard.cli.evonexus_migrate import (
    migrate,
    _check_plugin_compat,
    _get_plugin_tables,
    _row_count,
    _table_exists,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(path: Path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    return engine


def _apply_schema(engine):
    """Run alembic upgrade head on the given engine."""
    import subprocess
    import sys

    env = os.environ.copy()
    env["DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "dashboard/alembic/alembic.ini",
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
        )


def _seed_core(engine):
    """Insert minimal core rows (no plugin tables)."""
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO users
                (username, password_hash, role, is_active,
                 onboarding_completed_agents_visit, created_at)
            VALUES
                ('alice', 'h1', 'admin', 1, 0, '2024-01-01T00:00:00'),
                ('bob',   'h2', 'viewer', 1, 0, '2024-01-02T00:00:00')
        """)
        )
        conn.execute(
            text("""
            INSERT INTO missions (slug, title, status, created_at, updated_at)
            VALUES ('m1', 'Mission One', 'active',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """)
        )
        conn.execute(
            text("""
            INSERT INTO heartbeats
                (id, agent, interval_seconds, max_turns, timeout_seconds,
                 lock_timeout_seconds, wake_triggers, enabled, decision_prompt,
                 created_at, updated_at)
            VALUES ('hb1', 'atlas', 3600, 10, 600, 1800, '["interval"]', 0,
                    'Check linear.', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """)
        )


def _seed_plugin_row(engine, slug: str = "pm-essentials"):
    """Insert a plugins_installed row for a SQLite-only plugin."""
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO plugins_installed
                (id, slug, name, version, enabled, installed_at, status)
            VALUES (:pid, :slug, :name, '1.0.0', 1,
                    '2024-01-01T00:00:00', 'active')
        """),
            {
                "pid": f"pi-{slug}",
                "slug": slug,
                "name": slug.replace("-", " ").title(),
            },
        )


def _create_plugin_tables(engine, slug: str = "pm-essentials"):
    """Create fake plugin-specific tables in SQLite to simulate an installed plugin."""
    prefix = slug.replace("-", "_")
    with engine.begin() as conn:
        conn.execute(
            text(f"""
            CREATE TABLE IF NOT EXISTS {prefix}_projects (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text(f"""
            CREATE TABLE IF NOT EXISTS {prefix}_tasks (
                id         TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title      TEXT NOT NULL
            )
        """)
        )
        # Seed a couple of rows
        conn.execute(
            text(
                f"INSERT INTO {prefix}_projects (id, name) VALUES ('p1', 'Alpha'), ('p2', 'Beta')"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {prefix}_tasks (id, project_id, title)"
                f" VALUES ('t1', 'p1', 'Task One'), ('t2', 'p2', 'Task Two')"
            )
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSkipIncompatiblePlugins:
    def test_without_flag_fails_fast(self, tmp_path):
        """Without --skip-incompatible-plugins, an incompatible plugin aborts migration.

        We force is_pg_target=True by patching _build_engine on the target side so
        the plugin-compat guard is exercised (it is Postgres-only by design).
        """
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        # Use a postgresql:// URL so is_pg_target=True; we swap the engine below.
        dst_url_fake = "postgresql://fake/db"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_core(src_engine)
        _seed_plugin_row(src_engine)
        _create_plugin_tables(src_engine)

        import dashboard.cli.evonexus_migrate as _mod

        original_build = _mod._build_engine

        def _fake_build(url, is_source=False):
            # Return the real SQLite engines regardless of URL so no actual
            # Postgres connection is attempted during this unit test.
            return src_engine if is_source else dst_engine

        with (
            patch.object(_mod, "_build_engine", side_effect=_fake_build),
            patch.object(_mod, "_check_plugin_compat", return_value=["pm-essentials"]),
        ):
            ok = migrate(
                source_url=src_url,
                target_url=dst_url_fake,  # postgresql:// → is_pg_target=True
                skip_incompatible_plugins=False,
            )

        assert not ok, "migrate() must return False when incompatible plugin found without flag"
        # Target must be untouched (no migration ran)
        with dst_engine.connect() as dc:
            assert _row_count(dc, "users") == 0, "Target must be empty after abort"

    def test_with_flag_migrates_core_data(self, tmp_path):
        """With --skip-incompatible-plugins, core tables are migrated; plugin tables skipped."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_core(src_engine)
        _seed_plugin_row(src_engine)
        _create_plugin_tables(src_engine)

        with patch(
            "dashboard.cli.evonexus_migrate._check_plugin_compat",
            return_value=["pm-essentials"],
        ):
            ok = migrate(
                source_url=src_url,
                target_url=dst_url,
                skip_incompatible_plugins=True,
            )

        assert ok, "migrate() should return True with --skip-incompatible-plugins"

        with src_engine.connect() as sc, dst_engine.connect() as dc:
            # Core tables must match
            for table in ("users", "heartbeats", "missions"):
                src_n = _row_count(sc, table)
                dst_n = _row_count(dc, table)
                assert src_n == dst_n, (
                    f"{table}: source={src_n} target={dst_n}"
                )
            # plugins_installed registry row must be migrated
            assert _row_count(dc, "plugins_installed") == 1, (
                "plugins_installed registry row must be present in target"
            )

    def test_with_flag_plugin_tables_not_in_target(self, tmp_path):
        """Plugin-specific tables must not exist in target (they were never created there)."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_core(src_engine)
        _seed_plugin_row(src_engine)
        _create_plugin_tables(src_engine)

        with patch(
            "dashboard.cli.evonexus_migrate._check_plugin_compat",
            return_value=["pm-essentials"],
        ):
            migrate(
                source_url=src_url,
                target_url=dst_url,
                skip_incompatible_plugins=True,
            )

        with dst_engine.connect() as dc:
            assert not _table_exists(dc, "pm_essentials_projects"), (
                "pm_essentials_projects must NOT be created in target"
            )
            assert not _table_exists(dc, "pm_essentials_tasks"), (
                "pm_essentials_tasks must NOT be created in target"
            )

    def test_get_plugin_tables_returns_correct_tables(self, tmp_path):
        """_get_plugin_tables detects tables by slug prefix."""
        db_path = tmp_path / "test.db"
        engine = _make_engine(db_path)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pm_essentials_projects (id TEXT PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE pm_essentials_tasks (id TEXT PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE unrelated_table (id TEXT PRIMARY KEY)"))

        with engine.connect() as conn:
            tables = _get_plugin_tables(conn, "pm-essentials")

        assert set(tables) == {"pm_essentials_projects", "pm_essentials_tasks"}, (
            f"Expected plugin tables, got {tables}"
        )
        assert "unrelated_table" not in tables

    def test_no_incompatible_plugins_no_skip_needed(self, tmp_path):
        """When all plugins are compatible, --skip-incompatible-plugins is a no-op."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_core(src_engine)

        # No incompatible plugins returned
        with patch(
            "dashboard.cli.evonexus_migrate._check_plugin_compat",
            return_value=[],
        ):
            ok = migrate(
                source_url=src_url,
                target_url=dst_url,
                skip_incompatible_plugins=True,
            )

        assert ok, "migration must succeed when no incompatible plugins exist"

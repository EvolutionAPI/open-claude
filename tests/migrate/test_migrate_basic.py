"""Basic migration tests — happy path and --dry-run.

Tests use SQLite→SQLite to avoid requiring a live Postgres instance.
The trigger-disable/enable dance is Postgres-only, so SQLite→SQLite skips it.
Postgres-specific behaviour is validated in test_migrate_edge_cases.py when
DATABASE_URL points to Postgres.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, inspect

from dashboard.cli.evonexus_migrate import (
    TABLES_IN_ORDER,
    migrate,
    _dry_run,
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
    import subprocess, os, sys
    env = os.environ.copy()
    # render_as_string(hide_password=False) is required — str(engine.url) masks
    # the password as '***' in SQLAlchemy 2.0, breaking the subprocess call.
    env["DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "dashboard/alembic/alembic.ini", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
        )


def _seed_source(engine):
    """Insert minimal data into every migratable table."""
    with engine.begin() as conn:
        # users (required by many FKs)
        conn.execute(text("""
            INSERT INTO users (username, password_hash, role, is_active, onboarding_completed_agents_visit, created_at)
            VALUES ('alice', 'hash1', 'admin', 1, 0, '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO users (username, password_hash, role, is_active, onboarding_completed_agents_visit, created_at)
            VALUES ('bob', 'hash2', 'viewer', 1, 0, '2024-01-02T00:00:00')
        """))
        # roles
        conn.execute(text("""
            INSERT INTO roles (name, created_at) VALUES ('admin', '2024-01-01T00:00:00')
        """))
        # missions
        conn.execute(text("""
            INSERT INTO missions (slug, title, status, created_at, updated_at)
            VALUES ('m1', 'Mission One', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # projects
        conn.execute(text("""
            INSERT INTO projects (slug, mission_id, title, status, created_at, updated_at)
            VALUES ('p1', 1, 'Project One', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # goals — 1 achieved, 1 active-borderline
        conn.execute(text("""
            INSERT INTO goals (slug, project_id, title, metric_type, target_value, current_value, status, created_at, updated_at)
            VALUES ('g-achieved', 1, 'Achieved Goal', 'count', 3.0, 3.0, 'achieved', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO goals (slug, project_id, title, metric_type, target_value, current_value, status, created_at, updated_at)
            VALUES ('g-borderline', 1, 'Borderline Goal', 'count', 2.0, 1.0, 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # goal_tasks: 3 done for achieved-goal, 1 done + 1 in_progress for borderline
        for i in range(3):
            conn.execute(text("""
                INSERT INTO goal_tasks (goal_id, title, priority, status, created_at, updated_at)
                VALUES (1, :t, 3, 'done', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
            """), {"t": f"Task {i+1}"})
        conn.execute(text("""
            INSERT INTO goal_tasks (goal_id, title, priority, status, created_at, updated_at)
            VALUES (2, 'Done Task', 3, 'done', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO goal_tasks (goal_id, title, priority, status, created_at, updated_at)
            VALUES (2, 'In-Progress Task', 3, 'in_progress', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # heartbeats
        conn.execute(text("""
            INSERT INTO heartbeats (id, agent, interval_seconds, max_turns, timeout_seconds,
                lock_timeout_seconds, wake_triggers, enabled, decision_prompt, created_at, updated_at)
            VALUES ('hb1', 'atlas', 3600, 10, 600, 1800, '["interval"]', 0,
                    'Check linear.', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # heartbeat_runs
        conn.execute(text("""
            INSERT INTO heartbeat_runs (run_id, heartbeat_id, status, started_at)
            VALUES ('run-1', 'hb1', 'completed', '2024-01-01T00:00:00')
        """))
        # heartbeat_triggers
        conn.execute(text("""
            INSERT INTO heartbeat_triggers (id, heartbeat_id, trigger_type, created_at)
            VALUES ('trig-1', 'hb1', 'interval', '2024-01-01T00:00:00')
        """))
        # tickets
        conn.execute(text("""
            INSERT INTO tickets (id, title, status, priority, priority_rank, created_by, created_at, updated_at)
            VALUES ('ticket-1', 'Bug #1', 'open', 'high', 3, 'alice', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # ticket_comments
        conn.execute(text("""
            INSERT INTO ticket_comments (id, ticket_id, author, body, created_at)
            VALUES ('cmt-1', 'ticket-1', 'alice', 'First comment', '2024-01-01T00:00:00')
        """))
        # ticket_activity
        conn.execute(text("""
            INSERT INTO ticket_activity (id, ticket_id, actor, action, created_at)
            VALUES ('act-1', 'ticket-1', 'alice', 'created', '2024-01-01T00:00:00')
        """))
        # plugins_installed
        conn.execute(text("""
            INSERT INTO plugins_installed (id, slug, name, version, enabled, installed_at, status)
            VALUES ('pi-1', 'pm-essentials', 'PM Essentials', '1.0.0', 1,
                    '2024-01-01T00:00:00', 'active')
        """))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMigrateHappyPath:
    def test_happy_path_sqlite_to_sqlite(self, tmp_path):
        """Migrate from a seeded SQLite source to an empty SQLite target."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)

        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        ok = migrate(
            source_url=src_url,
            target_url=dst_url,
            allow_non_empty=False,
        )
        assert ok, "migrate() should return True"

        # Verify key tables have the same row count
        with src_engine.connect() as sc:
            with dst_engine.connect() as dc:
                for table in ["users", "goals", "goal_tasks", "heartbeats", "tickets"]:
                    src_n = _row_count(sc, table)
                    dst_n = _row_count(dc, table)
                    assert src_n == dst_n, (
                        f"{table}: source has {src_n} rows, target has {dst_n}"
                    )

    def test_dry_run_does_not_write(self, tmp_path):
        """--dry-run should not write any rows to the target."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)

        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        ok = migrate(
            source_url=src_url,
            target_url=dst_url,
            dry_run=True,
        )
        assert ok, "dry-run should succeed"

        # Target must be empty after dry-run
        with dst_engine.connect() as dc:
            assert _row_count(dc, "users") == 0, "dry-run must not write rows"
            assert _row_count(dc, "goals") == 0, "dry-run must not write rows"

    def test_tables_in_order_are_all_valid(self, tmp_path):
        """Every table in TABLES_IN_ORDER must exist after alembic upgrade head."""
        db_path = tmp_path / "check.db"
        engine = _make_engine(db_path)
        _apply_schema(engine)

        insp = inspect(engine)
        existing = set(insp.get_table_names())

        for table in TABLES_IN_ORDER:
            assert table in existing, (
                f"Table {table!r} in TABLES_IN_ORDER not found after alembic upgrade head"
            )

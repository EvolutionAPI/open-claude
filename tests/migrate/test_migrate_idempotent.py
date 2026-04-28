"""Idempotency tests — running migrate twice must be a no-op.

Also tests --resume after a simulated mid-run interruption.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from dashboard.cli.evonexus_migrate import migrate, _row_count


def _make_engine(path: Path):
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def _apply_schema(engine):
    import subprocess, os, sys
    env = os.environ.copy()
    env["DATABASE_URL"] = str(engine.url)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "dashboard/alembic/alembic.ini", "upgrade", "head"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic failed:\n{result.stdout}\n{result.stderr}")


def _seed_source(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (username, password_hash, role, is_active,
                onboarding_completed_agents_visit, created_at)
            VALUES ('alice', 'h', 'admin', 1, 0, '2024-01-01T00:00:00'),
                   ('bob',   'h', 'viewer', 1, 0, '2024-01-02T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO missions (slug, title, status, created_at, updated_at)
            VALUES ('m1', 'Mission', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO projects (slug, mission_id, title, status, created_at, updated_at)
            VALUES ('p1', 1, 'Project', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO goals (slug, project_id, title, metric_type, target_value, current_value, status, created_at, updated_at)
            VALUES ('g1', 1, 'Goal', 'count', 2.0, 1.0, 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO goal_tasks (goal_id, title, priority, status, created_at, updated_at)
            VALUES (1, 'Task 1', 3, 'done', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO tickets (id, title, status, priority, priority_rank, created_by, created_at, updated_at)
            VALUES ('t1', 'Ticket', 'open', 'medium', 2, 'alice', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))


class TestIdempotency:
    def test_second_run_is_noop(self, tmp_path):
        """Running migrate twice must leave the same row counts."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # First run
        ok1 = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok1

        # Capture counts after first run
        with dst_engine.connect() as dc:
            counts_after_1 = {
                t: _row_count(dc, t)
                for t in ["users", "goals", "goal_tasks", "tickets"]
            }

        # Second run — must be idempotent
        ok2 = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=True)
        assert ok2

        with dst_engine.connect() as dc:
            counts_after_2 = {
                t: _row_count(dc, t)
                for t in ["users", "goals", "goal_tasks", "tickets"]
            }

        assert counts_after_1 == counts_after_2, (
            f"Second run changed row counts:\n"
            f"  after run 1: {counts_after_1}\n"
            f"  after run 2: {counts_after_2}"
        )

    def test_resume_skips_completed_tables(self, tmp_path):
        """--resume marks tables complete and skips them on restart."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # First run with --resume (marks state)
        ok1 = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False, resume=True)
        assert ok1

        with dst_engine.connect() as dc:
            first_counts = {
                t: _row_count(dc, t)
                for t in ["users", "goals"]
            }

        # Second run with --resume — should skip completed tables
        ok2 = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=True, resume=True)
        assert ok2

        with dst_engine.connect() as dc:
            second_counts = {
                t: _row_count(dc, t)
                for t in ["users", "goals"]
            }

        assert first_counts == second_counts, (
            "Resume second run changed counts unexpectedly"
        )

    def test_resume_simulated_interruption(self, tmp_path):
        """Simulate mid-run interruption: manually mark first 3 tables done,
        then run with --resume and confirm final state is consistent."""
        from dashboard.cli.evonexus_migrate import (
            _ensure_state_table,
            _mark_table_completed,
            TABLES_IN_ORDER,
        )

        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # Manually bootstrap state table and mark first 3 tables as "complete"
        # (but don't actually copy data — simulates a crash that wrote state but not rows)
        with dst_engine.connect() as dc:
            _ensure_state_table(dc)
            for table in TABLES_IN_ORDER[:3]:
                _mark_table_completed(dc, table, 0)

        # Resume should migrate remaining tables and complete successfully
        ok = migrate(
            source_url=src_url,
            target_url=dst_url,
            allow_non_empty=True,
            resume=True,
            skip_verify=True,  # skip verify since state is artificial
        )
        assert ok

        # Key tables not in the first 3 should have data
        with dst_engine.connect() as dc:
            # goals is well past the first 3 tables
            assert _row_count(dc, "goals") > 0, (
                "goals should have been migrated by resume run"
            )

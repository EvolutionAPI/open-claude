"""AC5 edge case tests — achieved and borderline goals.

These tests verify the trigger-disable/enable discipline.

SQLite→SQLite: trigger dance is skipped (source of truth on SQLite is the
SQLite trigger, not the PG plpgsql one).  The AC5 correctness proof still
works because we verify data values, not trigger invocations.

Postgres-specific trigger tests are marked @pytest.mark.postgres and run
only when DATABASE_URL points to a live PG instance.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from dashboard.cli.evonexus_migrate import migrate, _row_count


def _make_sqlite_engine(path: Path):
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def _make_pg_engine(url: str):
    from dashboard.cli.evonexus_migrate import _build_engine
    return _build_engine(url, is_source=False)


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


def _seed_ac5_source(engine):
    """Insert:
    - 1 achieved goal (current=3, target=3, status='achieved') with 3 done tasks
    - 1 borderline goal (current=1, target=2, status='active') with 1 done + 1 in_progress task
    """
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (username, password_hash, role, is_active,
                onboarding_completed_agents_visit, created_at)
            VALUES ('tester', 'x', 'admin', 1, 0, '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO missions (slug, title, status, created_at, updated_at)
            VALUES ('m1', 'Mission', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO projects (slug, mission_id, title, status, created_at, updated_at)
            VALUES ('p1', 1, 'Proj', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # Goal 1: already achieved
        conn.execute(text("""
            INSERT INTO goals (id, slug, project_id, title, metric_type, target_value,
                current_value, status, created_at, updated_at)
            VALUES (1, 'g-achieved', 1, 'Achieved', 'count', 3.0, 3.0, 'achieved',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # 3 done tasks for achieved goal
        for i in range(3):
            conn.execute(text("""
                INSERT INTO goal_tasks (goal_id, title, priority, status, created_at, updated_at)
                VALUES (1, :t, 3, 'done', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
            """), {"t": f"AchTask{i}"})

        # Goal 2: borderline (1/2 done, needs 1 more to achieve)
        conn.execute(text("""
            INSERT INTO goals (id, slug, project_id, title, metric_type, target_value,
                current_value, status, created_at, updated_at)
            VALUES (2, 'g-borderline', 1, 'Borderline', 'count', 2.0, 1.0, 'active',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        # 1 done + 1 in_progress for borderline goal
        conn.execute(text("""
            INSERT INTO goal_tasks (id, goal_id, title, priority, status, created_at, updated_at)
            VALUES (10, 2, 'Done Task', 3, 'done', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))
        conn.execute(text("""
            INSERT INTO goal_tasks (id, goal_id, title, priority, status, created_at, updated_at)
            VALUES (11, 2, 'InProgress Task', 3, 'in_progress',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))


class TestAC5EdgeCases:
    def test_achieved_goal_stays_achieved_after_migrate(self, tmp_path):
        """After migration, achieved goal must remain achieved with same current_value."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_sqlite_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok

        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value, status FROM goals WHERE id=1")
            ).fetchone()
            assert row is not None, "achieved goal must be in target"
            assert row[0] == 3.0, f"current_value must be 3, got {row[0]}"
            assert row[1] == "achieved", f"status must be 'achieved', got {row[1]}"

    def test_borderline_goal_preserves_state_after_migrate(self, tmp_path):
        """After migration, borderline goal retains original values (1/2, active)."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_sqlite_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok

        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value, target_value, status FROM goals WHERE id=2")
            ).fetchone()
            assert row is not None
            assert row[0] == 1.0, f"borderline current_value must be 1, got {row[0]}"
            assert row[1] == 2.0, f"borderline target_value must be 2, got {row[1]}"
            assert row[2] == "active", f"borderline status must be 'active', got {row[2]}"

    def test_borderline_goal_achieves_on_next_update(self, tmp_path):
        """After migration, completing the in_progress task on the borderline goal
        must trigger the SQLite trigger and set status=achieved.

        This proves the trigger was not permanently damaged by the migrate process
        (for Postgres, the disable/enable dance preserves trigger integrity).
        """
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_sqlite_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok

        # Now simulate the "next ORM update" — transition in_progress task to done
        with dst_engine.begin() as dc:
            dc.execute(text("""
                UPDATE goal_tasks SET status='done' WHERE id=11
            """))

        # The SQLite trigger should have fired and updated the goal
        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value, status FROM goals WHERE id=2")
            ).fetchone()
            # current_value should now be 2 (trigger incremented from 1)
            assert row[0] == 2.0, (
                f"After completing the last task, current_value should be 2, got {row[0]}"
            )
            assert row[1] == "achieved", (
                f"After completing the last task, status should be 'achieved', got {row[1]}"
            )

    def test_no_double_increment_on_already_done_task(self, tmp_path):
        """Updating a task that is already 'done' must NOT re-increment the goal.

        This validates ADR PG-Q3 trigger semantics: OLD.status != 'done' guard.
        """
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_sqlite_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok

        # "Update" an already-done task to 'done' again — should not re-increment
        with dst_engine.begin() as dc:
            dc.execute(text("""
                UPDATE goal_tasks SET status='done' WHERE id=10
            """))

        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value FROM goals WHERE id=2")
            ).fetchone()
            # Must still be 1 (not 2), since task was already 'done'
            assert row[0] == 1.0, (
                f"Re-setting already-done task must NOT re-increment. Got {row[0]}"
            )

    def test_goal_tasks_count_matches_source(self, tmp_path):
        """Row counts for goals and goal_tasks must match between source and target."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_sqlite_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok

        with src_engine.connect() as sc:
            with dst_engine.connect() as dc:
                for table in ("goals", "goal_tasks"):
                    src_n = _row_count(sc, table)
                    dst_n = _row_count(dc, table)
                    assert src_n == dst_n, (
                        f"{table}: source={src_n} target={dst_n}"
                    )


@pytest.mark.postgres
class TestAC5EdgeCasesPostgres:
    """Postgres-specific tests: verify trigger DISABLE/ENABLE dance works correctly."""

    def test_pg_achieved_goal_no_double_increment(self, tmp_path):
        """On Postgres, migrating goal_tasks with trigger disabled must not
        double-increment an already-achieved goal."""
        pg_url = os.environ.get("DATABASE_URL", "")
        if not pg_url.startswith("postgresql") and not pg_url.startswith("postgres://"):
            pytest.skip("Requires Postgres DATABASE_URL")

        src_path = tmp_path / "src.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = pg_url

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_pg_engine(dst_url)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(
            source_url=src_url,
            target_url=dst_url,
            allow_non_empty=True,
        )
        assert ok

        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value, status FROM goals WHERE id=1")
            ).fetchone()
            assert row[0] == 3.0, f"PG: achieved goal current_value must be 3, got {row[0]}"
            assert row[1] == "achieved"

    def test_pg_borderline_goal_achieves_post_migrate(self, tmp_path):
        """On Postgres, after re-enabling the trigger, completing the last task
        must fire the plpgsql trigger and set status=achieved."""
        pg_url = os.environ.get("DATABASE_URL", "")
        if not pg_url.startswith("postgresql") and not pg_url.startswith("postgres://"):
            pytest.skip("Requires Postgres DATABASE_URL")

        src_path = tmp_path / "src.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = pg_url

        src_engine = _make_sqlite_engine(src_path)
        dst_engine = _make_pg_engine(dst_url)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_ac5_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=True)
        assert ok

        # Trigger the last task
        with dst_engine.begin() as dc:
            dc.execute(text("UPDATE goal_tasks SET status='done' WHERE id=11"))

        with dst_engine.connect() as dc:
            row = dc.execute(
                text("SELECT current_value, status FROM goals WHERE id=2")
            ).fetchone()
            assert row[0] == 2.0, f"PG: borderline should reach 2, got {row[0]}"
            assert row[1] == "achieved"

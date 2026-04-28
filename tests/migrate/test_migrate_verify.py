"""Verification tests — tool detects and reports mismatches.

Tests that the --verify step catches row count and checksum differences
between source and target, and exits non-zero.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from dashboard.cli.evonexus_migrate import migrate, _verify, _row_count


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
            VALUES ('p1', 1, 'Proj', 'active', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """))


class TestVerification:
    def test_verify_passes_after_clean_migrate(self, tmp_path):
        """_verify() returns True after a clean migration."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False)
        assert ok, "migrate() must succeed"

        # Run _verify directly to double-check
        result = _verify(src_engine, dst_engine)
        assert result is True, "_verify() should return True after clean migration"

    def test_verify_fails_when_target_mutated(self, tmp_path):
        """_verify() returns False if extra rows exist in target after migration."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # Migrate first
        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False, skip_verify=True)
        assert ok

        # Inject an extra row into target after migration — simulates drift
        with dst_engine.begin() as dc:
            dc.execute(text("""
                INSERT INTO users (username, password_hash, role, is_active,
                    onboarding_completed_agents_visit, created_at)
                VALUES ('ghost', 'h', 'viewer', 1, 0, '2024-06-01T00:00:00')
            """))

        # _verify should now detect the mismatch
        result = _verify(src_engine, dst_engine)
        assert result is False, "_verify() should return False when target has extra rows"

    def test_verify_fails_when_target_missing_rows(self, tmp_path):
        """_verify() returns False when target has fewer rows than source."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # Partial migration — skip verify, then delete a row from target
        ok = migrate(source_url=src_url, target_url=dst_url, allow_non_empty=False, skip_verify=True)
        assert ok

        with dst_engine.begin() as dc:
            dc.execute(text("DELETE FROM users WHERE username='bob'"))

        result = _verify(src_engine, dst_engine)
        assert result is False

    def test_migrate_returns_false_on_verify_failure(self, tmp_path):
        """migrate() returns False (exit non-zero) when post-migration verify detects drift."""
        src_path = tmp_path / "src.db"
        dst_path = tmp_path / "dst.db"
        src_url = f"sqlite:///{src_path}"
        dst_url = f"sqlite:///{dst_path}"

        src_engine = _make_engine(src_path)
        dst_engine = _make_engine(dst_path)
        _apply_schema(src_engine)
        _apply_schema(dst_engine)
        _seed_source(src_engine)

        # We'll monkey-patch _verify to inject a failure after migration
        import dashboard.cli.evonexus_migrate as mod
        original_verify = mod._verify

        def _patched_verify(src_eng, dst_eng, skipped_tables=None):
            # First inject a ghost row to cause real mismatch
            with dst_eng.begin() as dc:
                dc.execute(text("""
                    INSERT INTO users (username, password_hash, role, is_active,
                        onboarding_completed_agents_visit, created_at)
                    VALUES ('ghost', 'h', 'viewer', 1, 0, '2024-01-01T00:00:00')
                """))
            return original_verify(src_eng, dst_eng, skipped_tables=skipped_tables)

        mod._verify = _patched_verify
        try:
            ok = migrate(
                source_url=src_url,
                target_url=dst_url,
                allow_non_empty=False,
            )
        finally:
            mod._verify = original_verify

        assert ok is False, "migrate() must return False when verify fails"

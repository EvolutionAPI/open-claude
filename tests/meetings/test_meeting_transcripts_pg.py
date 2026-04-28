"""tests/meetings/test_meeting_transcripts_pg.py

Meeting transcript storage — bifurcated by dialect.

Tests
-----
- upsert_meeting() in PG creates a row; second call with same fathom_id does UPDATE
- upsert_meeting() in SQLite (dialect.name != 'postgresql') writes files to workspace/meetings/
- list_recent_meetings() returns rows ordered by started_at DESC (PG)
- list_recent_meetings() scans files (SQLite)
- get_meeting() returns full dict (PG)
- get_meeting() reads files and returns dict (SQLite)
- AC1: SQLite path is unaffected — no files written to workspace/meetings/ when not expected

Markers
-------
@pytest.mark.postgres   — requires DATABASE_URL pointing to Postgres
@pytest.mark.sqlite     — runs against SQLite only
(unmarked helpers are dialect-agnostic)

Usage
-----
    # SQLite only (no Docker):
    pytest tests/meetings/test_meeting_transcripts_pg.py -m 'not postgres' -v

    # Postgres only:
    DATABASE_URL=postgresql://postgres:test@localhost:55494/postgres \\
        pytest tests/meetings/test_meeting_transcripts_pg.py -m postgres -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest
import sqlalchemy as sa
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Paths — make dashboard/backend importable from the test
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
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"


def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _unique_id() -> str:
    return f"fathom-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_engine():
    """Live PG engine with full schema. Skipped if PG not configured."""
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

    # Wipe meetings inserted by this test run to keep tests idempotent.
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM meeting_transcripts"))

    yield eng

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM meeting_transcripts"))
    eng.dispose()


@pytest.fixture
def sqlite_engine(tmp_path):
    """SQLite engine with fully migrated schema."""
    db_url = f"sqlite:///{tmp_path}/test_meetings.db"
    _run_alembic_upgrade(db_url)
    eng = sa.create_engine(db_url, connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


def _patch_meeting_store(monkeypatch, engine):
    """Point meeting_store (and db.engine) at the given engine."""
    import db.engine as engine_mod

    # Remove cached module so it re-imports clean.
    for mod in list(sys.modules.keys()):
        if mod in ("meeting_store",) or mod.startswith("meeting_store."):
            del sys.modules[mod]

    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)
    if hasattr(engine_mod, "_engine"):
        monkeypatch.setattr(engine_mod, "_engine", engine)

    # Patch dialect proxy so dialect.name returns the correct value.
    class _MockDialect:
        name = engine.dialect.name

    monkeypatch.setattr(engine_mod, "dialect", _MockDialect())


# ---------------------------------------------------------------------------
# PG tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestMeetingStorePG:
    """Postgres-backed storage tests."""

    def test_upsert_creates_row(self, pg_engine, monkeypatch):
        """upsert_meeting() inserts a new row in meeting_transcripts."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        fid = _unique_id()
        identifier = ms.upsert_meeting(
            fathom_id=fid,
            title="Sprint Planning",
            started_at=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
            attendees=["davidson@etus.com.br"],
            summary="Quarterly planning session.",
        )

        assert identifier == f"meeting_transcripts:fathom_id={fid}"

        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT title, summary FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fid},
            ).fetchone()

        assert row is not None
        assert row.title == "Sprint Planning"
        assert row.summary == "Quarterly planning session."

    def test_upsert_second_call_updates(self, pg_engine, monkeypatch):
        """Calling upsert_meeting twice with the same fathom_id updates the row."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        fid = _unique_id()
        ms.upsert_meeting(fathom_id=fid, title="Old Title")
        ms.upsert_meeting(fathom_id=fid, title="New Title", summary="Updated summary.")

        with pg_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fid},
            ).scalar()
            title = conn.execute(
                text("SELECT title FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fid},
            ).scalar()

        assert count == 1, "Only one row should exist after two upserts of the same fathom_id"
        assert title == "New Title"

    def test_list_recent_meetings_ordered(self, pg_engine, monkeypatch):
        """list_recent_meetings() returns rows ordered by started_at DESC."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        older = _unique_id()
        newer = _unique_id()

        ms.upsert_meeting(
            fathom_id=older,
            title="Older Meeting",
            started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        )
        ms.upsert_meeting(
            fathom_id=newer,
            title="Newer Meeting",
            started_at=datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc),
        )

        results = ms.list_recent_meetings(limit=10)
        fids = [r["fathom_id"] for r in results]

        assert fids.index(newer) < fids.index(older), (
            "Newer meeting should appear before older one in list_recent_meetings"
        )

    def test_get_meeting_returns_full_dict(self, pg_engine, monkeypatch):
        """get_meeting() returns a dict with all expected keys."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        fid = _unique_id()
        raw = {"id": fid, "participants": ["alice"]}
        ms.upsert_meeting(
            fathom_id=fid,
            title="Design Review",
            summary="Reviewed new UI.",
            raw_payload=raw,
        )

        result = ms.get_meeting(fid)

        assert result is not None
        assert result["fathom_id"] == fid
        assert result["title"] == "Design Review"
        assert result["summary"] == "Reviewed new UI."

    def test_get_meeting_returns_none_for_missing(self, pg_engine, monkeypatch):
        """get_meeting() returns None when fathom_id does not exist."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        assert ms.get_meeting("nonexistent-id-xyz") is None

    def test_upsert_stores_json_fields(self, pg_engine, monkeypatch):
        """attendees and action_items are stored as JSON text and round-trip."""
        _patch_meeting_store(monkeypatch, pg_engine)
        import meeting_store as ms

        fid = _unique_id()
        attendees = ["alice@etus.com.br", "bob@etus.com.br"]
        actions = [{"description": "Write tests", "assignee": "alice"}]

        ms.upsert_meeting(
            fathom_id=fid,
            title="Team Sync",
            attendees=attendees,
            action_items=actions,
        )

        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT attendees, action_items FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fid},
            ).fetchone()

        assert json.loads(row.attendees) == attendees
        assert json.loads(row.action_items) == actions


# ---------------------------------------------------------------------------
# SQLite tests (AC1 regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
class TestMeetingStoreSQLite:
    """SQLite file-based storage tests — AC1 regression guard."""

    def test_upsert_writes_raw_json(self, sqlite_engine, monkeypatch, tmp_path):
        """In SQLite mode, upsert_meeting writes a JSON file to workspace/meetings/."""
        _patch_meeting_store(monkeypatch, sqlite_engine)
        import meeting_store as ms

        # Redirect MEETINGS_DIR to tmp_path so we don't pollute the real workspace.
        fake_meetings = tmp_path / "meetings"
        monkeypatch.setattr(ms, "MEETINGS_DIR", fake_meetings)

        fid = _unique_id()
        payload = {"id": fid, "title": "Product Demo"}
        identifier = ms.upsert_meeting(
            fathom_id=fid,
            title="Product Demo",
            started_at=datetime(2026, 4, 26, 9, 0, tzinfo=timezone.utc),
            raw_payload=payload,
        )

        assert identifier == f"meetings/{fid}", "SQLite identifier should be meetings/<fid>"

        # Verify file was created somewhere under fake_meetings/fathom/
        written = list(fake_meetings.glob("**/*.json"))
        assert len(written) == 1, f"Expected 1 JSON file, found {written}"
        stored = json.loads(written[0].read_text(encoding="utf-8"))
        assert stored["id"] == fid

    def test_upsert_writes_summary_file(self, sqlite_engine, monkeypatch, tmp_path):
        """In SQLite mode, a summary string is written to workspace/meetings/summaries/."""
        _patch_meeting_store(monkeypatch, sqlite_engine)
        import meeting_store as ms

        fake_meetings = tmp_path / "meetings"
        monkeypatch.setattr(ms, "MEETINGS_DIR", fake_meetings)

        fid = _unique_id()
        ms.upsert_meeting(
            fathom_id=fid,
            title="Grooming",
            summary="# Meeting Summary\n\nDiscussed backlog items.",
        )

        summaries = list(fake_meetings.glob("**/*.md"))
        assert len(summaries) == 1
        content = summaries[0].read_text(encoding="utf-8")
        assert "Discussed backlog items." in content

    def test_list_recent_meetings_sqlite(self, sqlite_engine, monkeypatch, tmp_path):
        """list_recent_meetings() in SQLite mode scans files, returns list of dicts."""
        _patch_meeting_store(monkeypatch, sqlite_engine)
        import meeting_store as ms

        fake_meetings = tmp_path / "meetings"
        monkeypatch.setattr(ms, "MEETINGS_DIR", fake_meetings)

        # Create two raw JSON files.
        raw_dir = fake_meetings / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "abc123.json").write_text('{"id": "abc123"}', encoding="utf-8")
        (raw_dir / "def456.json").write_text('{"id": "def456"}', encoding="utf-8")

        results = ms.list_recent_meetings(limit=10)
        assert len(results) == 2
        assert all("fathom_id" in r for r in results)

    def test_get_meeting_sqlite_reads_files(self, sqlite_engine, monkeypatch, tmp_path):
        """get_meeting() in SQLite mode reads from files."""
        _patch_meeting_store(monkeypatch, sqlite_engine)
        import meeting_store as ms

        fake_meetings = tmp_path / "meetings"
        monkeypatch.setattr(ms, "MEETINGS_DIR", fake_meetings)

        fid = _unique_id()
        payload = {"id": fid, "title": "Retro"}
        ms.upsert_meeting(
            fathom_id=fid,
            title="Retro",
            raw_payload=payload,
        )

        result = ms.get_meeting(fid)
        assert result is not None
        assert result["fathom_id"] == fid
        assert result["raw_payload"]["title"] == "Retro"

    def test_no_db_write_in_sqlite_mode(self, sqlite_engine, monkeypatch, tmp_path):
        """AC1: upsert_meeting in SQLite mode must NOT write to meeting_transcripts table.

        The table might not even exist in a bare SQLite DB (i.e., the alembic
        migrations ran, but the important thing is no accidental DB write).
        We verify by checking the row count stays zero.
        """
        _patch_meeting_store(monkeypatch, sqlite_engine)
        import meeting_store as ms

        fake_meetings = tmp_path / "meetings"
        monkeypatch.setattr(ms, "MEETINGS_DIR", fake_meetings)

        fid = _unique_id()
        ms.upsert_meeting(fathom_id=fid, title="Should go to files only")

        with sqlite_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fid},
            ).scalar()

        assert count == 0, "SQLite mode must not write to meeting_transcripts table"

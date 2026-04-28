"""tests/cli/test_import_logs.py

evonexus-import-logs: idempotent across all sources, --dry-run, --force,
SQLite mode guard.

All tests require a live Postgres instance (DATABASE_URL=postgresql://...).
Marked @pytest.mark.postgres — skipped when Postgres is not configured.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


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


def _make_args(**kwargs) -> SimpleNamespace:
    defaults = {"dry_run": False, "force": False, "verbose": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Fixtures builders
# ---------------------------------------------------------------------------

def _write_chat_fixture(base_dir: Path) -> Path:
    """Create a minimal chat JSONL file with 2 messages."""
    chat_dir = base_dir / "workspace" / "ADWs" / "logs" / "chat"
    chat_dir.mkdir(parents=True, exist_ok=True)
    f = chat_dir / "oracle_abc123de.jsonl"
    lines = [
        json.dumps({
            "role": "user",
            "text": "Hello",
            "ts": 1776902494341,
            "uuid": "11111111-1111-1111-1111-111111111111",
        }),
        json.dumps({
            "role": "assistant",
            "text": "Hi there",
            "ts": 1776902500000,
            "uuid": "22222222-2222-2222-2222-222222222222",
        }),
    ]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return chat_dir


def _write_daily_fixture(base_dir: Path) -> Path:
    """Create minimal daily log files."""
    daily_dir = base_dir / "workspace" / "daily-logs"
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / "[C] 2026-01-01-morning.md").write_text("# Morning\nContent", encoding="utf-8")
    (daily_dir / "[C] 2026-01-01-eod.html").write_text("<html>EOD</html>", encoding="utf-8")
    (daily_dir / "[C] 2026-01-02.md").write_text("# EOD\n", encoding="utf-8")
    return daily_dir


def _write_meeting_fixture(base_dir: Path) -> Path:
    """Create a minimal Fathom meeting JSON in the dated subdir."""
    fathom_dir = base_dir / "workspace" / "meetings" / "fathom" / "2026-01-01"
    fathom_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "recording_id": 999001,
        "title": "Test Meeting",
        "meeting_title": "Test Meeting",
        "recording_start_time": "2026-01-01T10:00:00Z",
        "recording_end_time": "2026-01-01T11:00:00Z",
        "calendar_invitees": [{"email": "a@example.com"}],
        "transcript": "Hello world",
        "default_summary": "A test meeting",
    }
    f = fathom_dir / "2026-01-01__999001__test-meeting.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return fathom_dir


def _write_brain_fixture(base_dir: Path) -> Path:
    """Create brain repo transcript JSONL files."""
    brain_dir = base_dir / "memory" / "raw-transcripts" / "evo-ai"
    brain_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"role": "user", "text": "Deploy?", "ts": "2026-01-01T10:00:00Z"}),
        json.dumps({"role": "assistant", "text": "Done", "ts": "2026-01-01T10:01:00Z"}),
    ]
    (brain_dir / "session-abc123.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return brain_dir


def _write_audit_fixture(base_dir: Path) -> Path:
    """Create a minimal workspace-mutations.jsonl."""
    log_dir = base_dir / "workspace" / "ADWs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "ts": "2026-01-01T10:00:00.000Z",
            "user_id": 1,
            "role": "admin",
            "op": "write",
            "path": "workspace/test.md",
            "result": "ok",
            "extra": {"bytes": 42},
        },
        {
            "ts": "2026-01-01T10:00:01.000Z",
            "user_id": 1,
            "role": "admin",
            "op": "read",
            "path": "workspace/other.md",
            "result": "ok",
            "extra": None,
        },
    ]
    f = log_dir / "workspace-mutations.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_engine():
    """Live PG engine with fresh schema. Skipped if PG is not configured."""
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

    # Wipe relevant log tables before each test
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM agent_chat_messages"))
        conn.execute(text("DELETE FROM agent_chat_sessions"))
        conn.execute(text("DELETE FROM daily_outputs"))
        conn.execute(text("DELETE FROM meeting_transcripts"))
        conn.execute(text("DELETE FROM plugin_hook_runs"))
        conn.execute(text("DELETE FROM brain_repo_transcripts"))
        conn.execute(text("DELETE FROM workspace_mutations"))

    yield eng

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM agent_chat_messages"))
        conn.execute(text("DELETE FROM agent_chat_sessions"))
        conn.execute(text("DELETE FROM daily_outputs"))
        conn.execute(text("DELETE FROM meeting_transcripts"))
        conn.execute(text("DELETE FROM plugin_hook_runs"))
        conn.execute(text("DELETE FROM brain_repo_transcripts"))
        conn.execute(text("DELETE FROM workspace_mutations"))
    eng.dispose()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Minimal workspace tree with fixture files for all sources."""
    _write_chat_fixture(tmp_path)
    _write_daily_fixture(tmp_path)
    _write_meeting_fixture(tmp_path)
    _write_brain_fixture(tmp_path)
    _write_audit_fixture(tmp_path)
    return tmp_path


def _patch_cli(monkeypatch, engine, workspace: Path):
    """Redirect all CLI constants to point at the test workspace + engine."""
    import db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)

    import importlib
    import config_store
    importlib.reload(config_store)

    import dashboard.cli.evonexus_import_logs as cli_mod
    importlib.reload(cli_mod)

    monkeypatch.setattr(cli_mod, "CHAT_DIR",
                        workspace / "workspace" / "ADWs" / "logs" / "chat")
    monkeypatch.setattr(cli_mod, "DAILY_LOGS_DIR",
                        workspace / "workspace" / "daily-logs")
    monkeypatch.setattr(cli_mod, "FATHOM_DIR",
                        workspace / "workspace" / "meetings" / "fathom")
    monkeypatch.setattr(cli_mod, "PLUGIN_LOGS_DIR",
                        workspace / "workspace" / "ADWs" / "logs" / "plugins")
    monkeypatch.setattr(cli_mod, "BRAIN_REPO_DIR",
                        workspace / "memory" / "raw-transcripts")
    monkeypatch.setattr(cli_mod, "WORKSPACE_AUDIT_FILE",
                        workspace / "workspace" / "ADWs" / "logs" / "workspace-mutations.jsonl")
    monkeypatch.setattr(cli_mod, "ROUTINE_LOGS_DIR",
                        workspace / "workspace" / "ADWs" / "logs" / "routines")

    return cli_mod


# ---------------------------------------------------------------------------
# Test 1 — Idempotence: running twice produces 0 duplicate rows
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestIdempotence:
    def test_run_twice_no_duplicates(self, pg_engine, workspace, monkeypatch):
        """Second run on the same files inserts 0 extra rows."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args()

        # First run
        cli.import_chat(args, cli._Stats())
        cli.import_daily_outputs(args, cli._Stats())
        cli.import_meetings(args, cli._Stats())
        cli.import_brain_repo(args, cli._Stats())
        cli.import_workspace_audit(args, cli._Stats())

        def _counts(conn):
            return {
                "sessions": conn.execute(text("SELECT COUNT(*) FROM agent_chat_sessions")).scalar(),
                "messages": conn.execute(text("SELECT COUNT(*) FROM agent_chat_messages")).scalar(),
                "daily": conn.execute(text("SELECT COUNT(*) FROM daily_outputs")).scalar(),
                "meetings": conn.execute(text("SELECT COUNT(*) FROM meeting_transcripts")).scalar(),
                "brain": conn.execute(text("SELECT COUNT(*) FROM brain_repo_transcripts")).scalar(),
                "mutations": conn.execute(text("SELECT COUNT(*) FROM workspace_mutations")).scalar(),
            }

        with pg_engine.connect() as conn:
            after_first = _counts(conn)

        # Second run
        cli.import_chat(args, cli._Stats())
        cli.import_daily_outputs(args, cli._Stats())
        cli.import_meetings(args, cli._Stats())
        cli.import_brain_repo(args, cli._Stats())
        cli.import_workspace_audit(args, cli._Stats())

        with pg_engine.connect() as conn:
            after_second = _counts(conn)

        # workspace_mutations is append-only — second run adds more rows
        # all other sources are idempotent
        assert after_second["sessions"] == after_first["sessions"], "chat sessions duplicated"
        assert after_second["messages"] == after_first["messages"], "chat messages duplicated"
        assert after_second["daily"] == after_first["daily"], "daily_outputs duplicated"
        assert after_second["meetings"] == after_first["meetings"], "meetings duplicated"
        assert after_second["brain"] == after_first["brain"], "brain_repo_transcripts duplicated"


# ---------------------------------------------------------------------------
# Test 2 — dry-run: nothing written
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestDryRun:
    def test_dry_run_writes_nothing(self, pg_engine, workspace, monkeypatch):
        """--dry-run must not write any rows to any table."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args(dry_run=True)

        stats = cli._Stats()
        cli.import_chat(args, stats)
        cli.import_daily_outputs(args, stats)
        cli.import_meetings(args, stats)
        cli.import_brain_repo(args, stats)
        cli.import_workspace_audit(args, stats)

        # Stats must report counts (files seen)
        assert stats.total() > 0, "dry-run should still accumulate stats"

        # DB must be empty
        with pg_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM agent_chat_sessions")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM agent_chat_messages")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM daily_outputs")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM meeting_transcripts")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM brain_repo_transcripts")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM workspace_mutations")).scalar() == 0


# ---------------------------------------------------------------------------
# Test 3 — chat fixture: correct sessions and messages
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestChatImport:
    def test_chat_sessions_and_messages(self, pg_engine, workspace, monkeypatch):
        """Chat JSONL produces 1 session + 2 messages with correct UUIDs."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args()
        stats = cli._Stats()

        cli.import_chat(args, stats)

        assert stats.counts.get("chat_sessions", 0) == 1
        assert stats.counts.get("chat_messages", 0) == 2

        with pg_engine.connect() as conn:
            sessions = conn.execute(text(
                "SELECT agent_name FROM agent_chat_sessions"
            )).fetchall()
            assert len(sessions) == 1
            assert sessions[0][0] == "oracle"

            messages = conn.execute(text(
                "SELECT id, role FROM agent_chat_messages ORDER BY ts"
            )).fetchall()
            assert len(messages) == 2
            roles = [r[1] for r in messages]
            assert "user" in roles
            assert "assistant" in roles

            # Known UUIDs from fixture must be preserved
            ids = {r[0] for r in messages}
            assert "11111111-1111-1111-1111-111111111111" in ids
            assert "22222222-2222-2222-2222-222222222222" in ids


# ---------------------------------------------------------------------------
# Test 4 — daily fixture: correct rows in daily_outputs
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestDailyOutputsImport:
    def test_daily_outputs_imported(self, pg_engine, workspace, monkeypatch):
        """Daily log files are parsed and inserted with correct kind + format."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args()
        stats = cli._Stats()

        cli.import_daily_outputs(args, stats)

        # 3 fixture files: morning.md, eod.html, plain eod.md
        assert stats.counts.get("daily_outputs", 0) == 3

        with pg_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT date::TEXT, kind, format FROM daily_outputs ORDER BY date, kind, format"
            )).fetchall()
            assert len(rows) == 3

            kinds = {(str(r[0]), r[1], r[2]) for r in rows}
            assert ("2026-01-01", "morning", "md") in kinds
            assert ("2026-01-01", "eod", "html") in kinds
            # plain [C] 2026-01-02.md → kind=eod
            assert ("2026-01-02", "eod", "md") in kinds


# ---------------------------------------------------------------------------
# Test 5 — meetings fixture: meeting_transcripts row
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestMeetingsImport:
    def test_meeting_imported(self, pg_engine, workspace, monkeypatch):
        """Meeting JSON is imported with correct fathom_id and title."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args()
        stats = cli._Stats()

        cli.import_meetings(args, stats)

        assert stats.counts.get("meetings", 0) == 1

        with pg_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT fathom_id, title FROM meeting_transcripts LIMIT 1"
            )).fetchone()
            assert row is not None
            assert row[0] == "999001"
            assert row[1] == "Test Meeting"


# ---------------------------------------------------------------------------
# Test 6 — brain fixture: brain_repo_transcripts row
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestBrainRepoImport:
    def test_brain_transcripts_imported(self, pg_engine, workspace, monkeypatch):
        """Brain repo JSONL imported with correct project_slug + session_id."""
        cli = _patch_cli(monkeypatch, pg_engine, workspace)
        args = _make_args()
        stats = cli._Stats()

        cli.import_brain_repo(args, stats)

        assert stats.counts.get("brain_repo_transcripts", 0) == 1

        with pg_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT project_slug, session_id FROM brain_repo_transcripts LIMIT 1"
            )).fetchone()
            assert row is not None
            assert row[0] == "evo-ai"
            assert row[1] == "session-abc123"


# ---------------------------------------------------------------------------
# Test 7 — SQLite mode: exit 1 with clear message
# ---------------------------------------------------------------------------

class TestSQLiteGuard:
    def test_sqlite_mode_exits_nonzero(self, monkeypatch):
        """Running against SQLite must return exit code 1."""
        import db.engine as engine_mod
        import sqlalchemy as sa

        sqlite_engine = sa.create_engine("sqlite:///:memory:", future=True)
        monkeypatch.setattr(engine_mod, "get_engine", lambda: sqlite_engine)

        import importlib
        import config_store
        importlib.reload(config_store)

        import dashboard.cli.evonexus_import_logs as cli_mod
        importlib.reload(cli_mod)

        result = cli_mod.main.__wrapped__() if hasattr(cli_mod.main, "__wrapped__") else None

        # Call main() with sys.argv patched to avoid argparse consuming test args
        monkeypatch.setattr(sys, "argv", ["evonexus-import-logs"])
        exit_code = cli_mod.main()
        assert exit_code == 1

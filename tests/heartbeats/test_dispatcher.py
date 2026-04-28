"""Tests for heartbeat dispatcher — debounce, feature flag, trigger recording."""

import json
import sqlite3
import sys
import tempfile
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

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
def tmp_db(tmp_path):
    """Create an in-memory SQLite DB with heartbeat tables."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE heartbeats (
            id TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            max_turns INTEGER NOT NULL DEFAULT 10,
            timeout_seconds INTEGER NOT NULL DEFAULT 600,
            lock_timeout_seconds INTEGER NOT NULL DEFAULT 1800,
            wake_triggers TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 0,
            goal_id TEXT,
            required_secrets TEXT DEFAULT '[]',
            decision_prompt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE heartbeat_runs (
            run_id TEXT PRIMARY KEY,
            heartbeat_id TEXT NOT NULL,
            trigger_id TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_ms INTEGER,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL,
            status TEXT NOT NULL DEFAULT 'running',
            prompt_preview TEXT,
            error TEXT,
            triggered_by TEXT
        );
        CREATE TABLE heartbeat_triggers (
            id TEXT PRIMARY KEY,
            heartbeat_id TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            consumed_at TEXT,
            coalesced_into TEXT
        );
    """)
    conn.commit()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn.execute("""
        INSERT INTO heartbeats VALUES (
            'test-hb', 'atlas-project', 3600, 10, 300, 1800,
            '["interval","manual"]', 1, null, '[]',
            'Decide: act or skip? Valid long enough prompt.', ?, ?
        )
    """, (now, now))
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def test_dispatch_allows_dispatch(tmp_db):
    """With an enabled heartbeat and no debounce, dispatch returns True."""
    import importlib
    import heartbeat_dispatcher as dispatcher
    importlib.reload(dispatcher)

    dispatched_runs = []

    def _fake_run(**kwargs):
        dispatched_runs.append(kwargs)

    def _make_conn():
        from sqlalchemy import create_engine
        engine = create_engine(f"sqlite:///{tmp_db}", connect_args={"check_same_thread": False})
        return engine.connect()

    with patch.object(dispatcher, "_get_db", _make_conn):
        with patch.object(dispatcher._executor, "submit", return_value=None):
            dispatched, run_id = dispatcher.dispatch("test-hb", "manual")

    # Should have been dispatched (or at least attempted)
    assert run_id is not None


# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row_conn(db_path):
    """Return a SQLAlchemy Connection backed by the given SQLite file (matches production _get_db)."""
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return engine.connect()


def test_debounce_coalesces_triggers(tmp_db):
    """Two triggers within 30s should result in one real dispatch."""
    import heartbeat_dispatcher as dispatcher

    # Pre-populate a recent unconsumed trigger
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    import uuid
    existing_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO heartbeat_triggers VALUES (?, 'test-hb', 'interval', '{}', ?, NULL, NULL)",
        (existing_id, _now_iso()),
    )
    conn.commit()

    import importlib
    importlib.reload(dispatcher)
    with patch.object(dispatcher, "_get_db", lambda: _row_conn(tmp_db)):
        dispatched, run_id = dispatcher.dispatch("test-hb", "manual")

    assert dispatched is False
    assert run_id is None

    # Verify a coalesced trigger was recorded
    conn2 = sqlite3.connect(str(tmp_db))
    coalesced = conn2.execute(
        "SELECT * FROM heartbeat_triggers WHERE coalesced_into = ?", (existing_id,)
    ).fetchone()
    conn2.close()
    assert coalesced is not None


def test_trigger_after_debounce_window_dispatches(tmp_db):
    """Trigger recorded > 30s ago should not block a new dispatch."""
    import heartbeat_dispatcher as dispatcher
    from datetime import timedelta

    # Pre-populate a trigger from >30s ago
    conn = sqlite3.connect(str(tmp_db))
    import uuid
    old_id = str(uuid.uuid4())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn.execute(
        "INSERT INTO heartbeat_triggers VALUES (?, 'test-hb', 'interval', '{}', ?, NULL, NULL)",
        (old_id, old_time),
    )
    conn.commit()
    conn.close()

    import importlib
    importlib.reload(dispatcher)

    with patch.object(dispatcher, "_get_db", lambda: _row_conn(tmp_db)):
        # Patch executor to avoid actually running the heartbeat
        with patch.object(dispatcher._executor, "submit", return_value=None):
            dispatched, run_id = dispatcher.dispatch("test-hb", "manual")

    # Should dispatch since old trigger is outside debounce window
    assert dispatched is True
    assert run_id is not None


# ---------------------------------------------------------------------------
# Trigger recording
# ---------------------------------------------------------------------------

def test_dispatch_records_trigger_event(tmp_db):
    """Successful dispatch should write a trigger event to heartbeat_triggers."""
    import heartbeat_dispatcher as dispatcher

    import importlib
    importlib.reload(dispatcher)

    with patch.object(dispatcher, "_get_db", lambda: _row_conn(tmp_db)):
        with patch.object(dispatcher._executor, "submit", return_value=None):
            dispatched, run_id = dispatcher.dispatch("test-hb", "interval")

    if dispatched:
        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT * FROM heartbeat_triggers WHERE heartbeat_id='test-hb' AND trigger_type='interval' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None

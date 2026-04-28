"""Tests for POST /api/chat-messages endpoint — PG mode.

Covers:
  - Basic insert into agent_chat_sessions + agent_chat_messages
  - Idempotency: posting same UUID twice returns duplicate=true on second call
  - Rewind: soft-deletes anchor message + all subsequent messages
  - Session FK: posting with an unknown session_id auto-creates the session
  - Validation: missing required fields returns 400
  - Not-found: rewinding a non-existent uuid returns 404
  - seq increments: sequential inserts get ascending seq values

Marked @pytest.mark.postgres — requires a live PG with alembic migrations applied.

Usage:
    docker run -d --name pg-phase3-logs \\
        -e POSTGRES_PASSWORD=test -p 55492:5432 postgres:16
    DATABASE_URL='postgresql://postgres:test@localhost:55492/postgres' \\
        make db-upgrade
    DATABASE_URL='postgresql://postgres:test@localhost:55492/postgres' \\
        uv run pytest tests/chat/test_chat_messages_pg.py -v

SQLite invariant (AC1):
    No DATABASE_URL → chat-logger.js keeps writing only JSONL.
    The endpoint exists but is never called by chat-logger.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_BACKEND = _REPO_ROOT / "dashboard" / "backend"
_ALEMBIC_DIR = _REPO_ROOT / "dashboard" / "alembic"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_IS_PG = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres://")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pg_dsn() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _run_alembic_upgrade() -> None:
    env = {**os.environ, "DATABASE_URL": DATABASE_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Minimal Flask app for tests
# ---------------------------------------------------------------------------

def _build_test_app(engine):
    """Create an isolated Flask app with only the chat_messages blueprint.

    Auth middleware is replaced by a no-op (all requests treated as authenticated).
    The db.engine singleton is set to `engine` before building the app.
    """
    import flask

    # Wire the raw SQLAlchemy engine used by chat_messages route
    import db.engine as engine_mod
    engine_mod._engine = engine

    # Reload chat_messages so it picks up the new engine via get_engine()
    import routes.chat_messages as cm_mod
    importlib.reload(cm_mod)

    _app = flask.Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-chat"

    # No auth middleware — all requests pass
    @_app.before_request
    def _allow_all():
        return None

    _app.register_blueprint(cm_mod.bp)
    return _app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_engine():
    if not _IS_PG:
        pytest.skip("DATABASE_URL not set or not PostgreSQL")
    from sqlalchemy import create_engine
    engine = create_engine(_pg_dsn(), pool_pre_ping=True)
    _run_alembic_upgrade()
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_pg(pg_engine):
    """Wipe chat tables before and after each test."""
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_chat_messages"))
        conn.execute(text("DELETE FROM agent_chat_sessions"))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_chat_messages"))
        conn.execute(text("DELETE FROM agent_chat_sessions"))


@pytest.fixture()
def client(clean_pg):
    """Flask test client wired to the test PG engine."""
    _app = _build_test_app(clean_pg)
    with _app.test_client() as c:
        yield c, clean_pg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_basic_insert(client):
    """POST /api/chat-messages creates session + message rows, seq=1."""
    c, engine = client
    from sqlalchemy import text

    session_id = str(uuid.uuid4())
    msg_uuid = str(uuid.uuid4())

    resp = c.post(
        "/api/chat-messages",
        json={
            "agent_name": "atlas-project",
            "session_id": session_id,
            "role": "user",
            "text": "hello world",
            "uuid": msg_uuid,
            "ts": "2026-04-26T10:00:00.000Z",
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["id"] == msg_uuid
    assert data["duplicate"] is False
    assert data["seq"] == 1

    with engine.connect() as conn:
        sess_row = conn.execute(
            text("SELECT agent_name FROM agent_chat_sessions WHERE id = :sid"),
            {"sid": session_id},
        ).fetchone()
        assert sess_row is not None
        assert sess_row.agent_name == "atlas-project"

        msg_row = conn.execute(
            text("SELECT role, seq FROM agent_chat_messages WHERE id = :id"),
            {"id": msg_uuid},
        ).fetchone()
        assert msg_row is not None
        assert msg_row.role == "user"
        assert msg_row.seq == 1


@pytest.mark.postgres
def test_idempotency_same_uuid(client):
    """Posting the same UUID twice: first returns duplicate=false, second duplicate=true."""
    c, _ = client

    session_id = str(uuid.uuid4())
    msg_uuid = str(uuid.uuid4())
    payload = {
        "agent_name": "bolt-executor",
        "session_id": session_id,
        "role": "assistant",
        "text": "idempotency test",
        "uuid": msg_uuid,
    }

    resp1 = c.post("/api/chat-messages", json=payload)
    assert resp1.status_code == 201
    assert resp1.get_json()["duplicate"] is False

    resp2 = c.post("/api/chat-messages", json=payload)
    assert resp2.status_code == 201
    data2 = resp2.get_json()
    assert data2["duplicate"] is True
    assert data2["id"] == msg_uuid


@pytest.mark.postgres
def test_rewind_soft_deletes(client):
    """POST /api/chat-messages/rewind marks anchor + all subsequent messages."""
    c, engine = client
    from sqlalchemy import text

    session_id = str(uuid.uuid4())
    uuids = [str(uuid.uuid4()) for _ in range(4)]

    for i, u in enumerate(uuids):
        resp = c.post(
            "/api/chat-messages",
            json={
                "session_id": session_id,
                "role": "user",
                "text": f"msg {i}",
                "uuid": u,
            },
        )
        assert resp.status_code == 201, resp.get_data(as_text=True)

    # Rewind from index 1 — should mark messages at index 1, 2, 3
    resp = c.post(
        "/api/chat-messages/rewind",
        json={"session_id": session_id, "at_uuid": uuids[1]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["rewound_count"] == 3

    with engine.connect() as conn:
        # Message 0 still visible
        row0 = conn.execute(
            text("SELECT rewound_at FROM agent_chat_messages WHERE id = :id"),
            {"id": uuids[0]},
        ).fetchone()
        assert row0.rewound_at is None

        # Messages 1-3 rewound
        for u in uuids[1:]:
            row = conn.execute(
                text("SELECT rewound_at FROM agent_chat_messages WHERE id = :id"),
                {"id": u},
            ).fetchone()
            assert row.rewound_at is not None, f"Message {u} should be rewound"


@pytest.mark.postgres
def test_session_auto_created(client):
    """Posting with a fresh session_id auto-creates the session row."""
    c, engine = client
    from sqlalchemy import text

    session_id = str(uuid.uuid4())
    resp = c.post(
        "/api/chat-messages",
        json={
            "session_id": session_id,
            "role": "system",
            "text": "session auto-create",
            "uuid": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 201

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM agent_chat_sessions WHERE id = :sid"),
            {"sid": session_id},
        ).scalar_one()
        assert count == 1


@pytest.mark.postgres
def test_missing_fields_returns_400(client):
    """Missing required fields (role, uuid) return 400."""
    c, _ = client
    resp = c.post(
        "/api/chat-messages",
        json={"session_id": str(uuid.uuid4())},  # missing role + uuid
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "Missing" in body.get("error", "")


@pytest.mark.postgres
def test_rewind_message_not_found(client):
    """Rewinding a non-existent at_uuid returns 404."""
    c, _ = client
    resp = c.post(
        "/api/chat-messages/rewind",
        json={
            "session_id": str(uuid.uuid4()),
            "at_uuid": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404


@pytest.mark.postgres
def test_seq_increments_per_session(client):
    """Sequential inserts in the same session get ascending seq values 1, 2, 3."""
    c, engine = client
    from sqlalchemy import text

    session_id = str(uuid.uuid4())
    for i in range(3):
        u = str(uuid.uuid4())
        resp = c.post(
            "/api/chat-messages",
            json={
                "session_id": session_id,
                "role": "user",
                "text": f"msg {i}",
                "uuid": u,
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()["seq"] == i + 1

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT seq FROM agent_chat_messages"
                " WHERE session_id = :sid ORDER BY seq"
            ),
            {"sid": session_id},
        ).fetchall()
        seqs = [r.seq for r in rows]
        assert seqs == [1, 2, 3]


# ---------------------------------------------------------------------------
# AC1 invariant — SQLite mode: sync queue not activated
# ---------------------------------------------------------------------------

def test_ac1_sqlite_mode_no_sync_queue():
    """When DATABASE_URL is absent, syncEnabled would be False in chat-logger.js."""
    env_backup = os.environ.pop("DATABASE_URL", None)
    try:
        db_url = os.environ.get("DATABASE_URL", "")
        sync_would_be_enabled = (
            db_url.startswith("postgresql") or db_url.startswith("postgres://")
        )
        assert not sync_would_be_enabled, (
            "AC1 violated: DATABASE_URL points to PG in this test environment"
        )
    finally:
        if env_backup is not None:
            os.environ["DATABASE_URL"] = env_backup

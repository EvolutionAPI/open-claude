"""
tests/backend/test_workspace_audit_pg.py

Área A — workspace_audit helper, dialect-bifurcated.

AC1:  SQLite mode writes to JSONL file (zero behaviour change).
AC-PG: PG mode inserts a row into workspace_mutations table.
extra: dict is serialised as JSON; None is stored as SQL NULL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stderr}")


def _make_pg_engine(db_url: str):
    url = db_url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return sa.create_engine(url, pool_pre_ping=True)


def _patch_engine(monkeypatch, engine):
    """Monkeypatch db.engine so workspace_audit uses our engine."""
    import db.engine as engine_mod
    for mod in ("workspace_audit", "config_store"):
        if mod in sys.modules:
            del sys.modules[mod]
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)
    if hasattr(engine_mod, "_engine"):
        monkeypatch.setattr(engine_mod, "_engine", engine)


# ---------------------------------------------------------------------------
# PG tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_audit_mutation_inserts_pg_row(monkeypatch):
    """PG mode: audit_mutation writes a row to workspace_mutations."""
    db_url = os.environ["DATABASE_URL"]
    _run_alembic_upgrade(db_url)
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)

    # Also patch get_dialect to return 'postgresql'
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    import workspace_audit
    workspace_audit.audit_mutation(
        user_id=None,
        role="admin",
        op="upload",
        path="workspace/test/file.txt",
        result="ok",
        extra={"size": 1024},
    )

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT user_id, role, op, path, result, extra "
                "FROM workspace_mutations ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()

    assert row is not None
    assert row[0] is None            # user_id NULL (no FK violation)
    assert row[1] == "admin"         # role
    assert row[2] == "upload"        # op
    assert row[3] == "workspace/test/file.txt"
    assert row[4] == "ok"            # result
    extra = json.loads(row[5])
    assert extra["size"] == 1024


@pytest.mark.postgres
def test_audit_mutation_extra_none_pg(monkeypatch):
    """PG mode: extra=None is stored as SQL NULL."""
    db_url = os.environ["DATABASE_URL"]
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    import workspace_audit
    workspace_audit.audit_mutation(
        user_id=None,
        role="anonymous",
        op="denied",
        path="workspace/secret",
        result="denied",
        extra=None,
    )

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT extra FROM workspace_mutations ORDER BY id DESC LIMIT 1")
        ).fetchone()

    assert row is not None
    assert row[0] is None


# ---------------------------------------------------------------------------
# SQLite / AC1 tests
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_audit_mutation_sqlite_writes_jsonl(monkeypatch, tmp_path):
    """SQLite mode (AC1): audit_mutation appends to JSONL file."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(sqlite_url, connect_args={"check_same_thread": False})

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    import workspace_audit
    log_file = tmp_path / "workspace-mutations.jsonl"
    monkeypatch.setattr(workspace_audit, "AUDIT_LOG_FILE", log_file)

    workspace_audit.audit_mutation(
        user_id=1,
        role="user",
        op="delete",
        path="workspace/notes/old.md",
        result="ok",
        extra={"reason": "cleanup"},
    )

    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["op"] == "delete"
    assert entry["path"] == "workspace/notes/old.md"
    assert entry["result"] == "ok"
    assert entry["extra"]["reason"] == "cleanup"


@pytest.mark.sqlite
def test_audit_mutation_sqlite_extra_none(monkeypatch, tmp_path):
    """SQLite mode (AC1): extra=None writes null to JSONL."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(sqlite_url, connect_args={"check_same_thread": False})

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    import workspace_audit
    log_file = tmp_path / "workspace-mutations.jsonl"
    monkeypatch.setattr(workspace_audit, "AUDIT_LOG_FILE", log_file)

    workspace_audit.audit_mutation(
        user_id=None,
        role=None,
        op="rename",
        path="workspace/foo.md",
        result="ok",
        extra=None,
    )

    entry = json.loads(log_file.read_text().strip())
    assert entry["extra"] is None

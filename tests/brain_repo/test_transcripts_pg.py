"""
tests/brain_repo/test_transcripts_pg.py

Área B — brain_repo transcripts mirror, dialect-bifurcated.

AC1:  SQLite mode copies files to memory/raw-transcripts/ (zero behaviour change).
AC-PG: PG mode upserts rows into brain_repo_transcripts.
Idempotent: second call with same session_id does UPDATE (not duplicate row).
"""

from __future__ import annotations

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
    """Monkeypatch db.engine for a specific engine."""
    import db.engine as engine_mod
    for mod in ("config_store",):
        if mod in sys.modules:
            del sys.modules[mod]
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)
    if hasattr(engine_mod, "_engine"):
        monkeypatch.setattr(engine_mod, "_engine", engine)


def _make_fake_projects_dir(tmp_path: Path, content: str = '{"role":"user","content":"hello"}\n') -> Path:
    """Create a minimal Claude Code projects directory layout."""
    proj = tmp_path / "projects" / "-Users-foo-Projects-myproject"
    proj.mkdir(parents=True)
    session_file = proj / "abc123def456.jsonl"
    session_file.write_text(content, encoding="utf-8")
    return tmp_path / "projects"


# ---------------------------------------------------------------------------
# PG tests
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_mirror_transcripts_inserts_pg_row(monkeypatch, tmp_path):
    """PG mode: mirror_transcripts upserts a row into brain_repo_transcripts."""
    db_url = os.environ["DATABASE_URL"]
    _run_alembic_upgrade(db_url)
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    projects_dir = _make_fake_projects_dir(tmp_path)

    from brain_repo import transcripts_mirror
    with monkeypatch.context() as m:
        m.setattr(transcripts_mirror, "find_claude_projects_dir", lambda *a, **kw: projects_dir)
        count = transcripts_mirror.mirror_transcripts(
            install_dir=tmp_path,
            brain_repo_dir=tmp_path / "brain_repo",
        )

    assert count == 1

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT project_slug, session_id, content "
                "FROM brain_repo_transcripts ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()

    assert row is not None
    assert row[1] == "abc123def456"   # session_id
    assert "hello" in row[2]          # content


@pytest.mark.postgres
def test_mirror_transcripts_upsert_idempotent(monkeypatch, tmp_path):
    """PG mode: second call with same session updates, does not duplicate."""
    db_url = os.environ["DATABASE_URL"]
    engine = _make_pg_engine(db_url)

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "postgresql")

    projects_dir = _make_fake_projects_dir(tmp_path, content='{"v":1}\n')
    session_file = projects_dir / "-Users-foo-Projects-myproject" / "abc123def456.jsonl"

    from brain_repo import transcripts_mirror
    with monkeypatch.context() as m:
        m.setattr(transcripts_mirror, "find_claude_projects_dir", lambda *a, **kw: projects_dir)
        transcripts_mirror.mirror_transcripts(
            install_dir=tmp_path,
            brain_repo_dir=tmp_path / "brain_repo",
        )
        # Update content and mirror again
        session_file.write_text('{"v":2}\n', encoding="utf-8")
        transcripts_mirror.mirror_transcripts(
            install_dir=tmp_path,
            brain_repo_dir=tmp_path / "brain_repo",
        )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT count(*), MAX(content) FROM brain_repo_transcripts "
                "WHERE session_id = 'abc123def456'"
            )
        ).fetchone()

    # Exactly 1 row with updated content
    assert rows[0] == 1
    assert '{"v":2}' in rows[1]


# ---------------------------------------------------------------------------
# SQLite / AC1 tests
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_mirror_transcripts_sqlite_copies_file(monkeypatch, tmp_path):
    """SQLite mode (AC1): mirror_transcripts copies JSONL to raw-transcripts/."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(sqlite_url, connect_args={"check_same_thread": False})

    _patch_engine(monkeypatch, engine)
    monkeypatch.setattr("config_store.get_dialect", lambda: "sqlite")

    projects_dir = _make_fake_projects_dir(tmp_path)
    brain_repo_dir = tmp_path / "brain_repo"

    from brain_repo import transcripts_mirror
    with monkeypatch.context() as m:
        m.setattr(transcripts_mirror, "find_claude_projects_dir", lambda *a, **kw: projects_dir)
        count = transcripts_mirror.mirror_transcripts(
            install_dir=tmp_path,
            brain_repo_dir=brain_repo_dir,
        )

    assert count == 1
    raw_root = brain_repo_dir / "memory" / "raw-transcripts"
    files = list(raw_root.rglob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name == "abc123def456.jsonl"

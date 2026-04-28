"""
daily_output_store — dialect-bifurcated daily output persistence.

PostgreSQL: outputs are inserted into the daily_outputs table.
SQLite:     outputs are written to workspace/daily-logs/ files (unchanged behaviour).

Public API:
    write_daily_output(date, kind, content, format, agent, metadata) -> str
    list_daily_outputs(kind=None, limit=30) -> list[dict]
    get_daily_output(output_id) -> dict | None
"""

from __future__ import annotations

import json
from datetime import date as date_type
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from db.engine import get_engine

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DAILY_LOGS_DIR = WORKSPACE_ROOT / "workspace" / "daily-logs"


def get_dialect() -> str:
    """Return the active SQLAlchemy dialect name ('postgresql' or 'sqlite')."""
    return get_engine().dialect.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_daily_output(
    *,
    date: date_type,
    kind: str,
    content: str,
    format: str = "md",
    agent: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Persist a daily output.

    Returns:
        PG:     'daily_outputs:<id>'
        SQLite: absolute file path (file was already written by Claude subprocess)
    """
    if get_dialect() == "postgresql":
        return _write_to_db(date, kind, content, format, agent, metadata)
    return _write_to_file(date, kind, content, format)


def list_daily_outputs(*, kind: Optional[str] = None, limit: int = 30) -> list[dict]:
    """Return recent daily outputs, ordered date DESC.

    PG:     queries daily_outputs table.
    SQLite: scans workspace/daily-logs/ directory.
    """
    if get_dialect() == "postgresql":
        return _list_from_db(kind=kind, limit=limit)
    return _list_from_dir(kind=kind, limit=limit)


def get_daily_output(output_id: str) -> Optional[dict]:
    """Fetch one output by identifier.

    PG identifier format:  'daily_outputs:<int>'
    SQLite identifier:      absolute file path string
    """
    if get_dialect() == "postgresql" and output_id.startswith("daily_outputs:"):
        db_id = int(output_id.split(":", 1)[1])
        return _get_from_db(db_id)
    # SQLite (or PG fallback to path)
    p = Path(output_id)
    if p.exists():
        return {"path": str(p), "content": p.read_text(encoding="utf-8"), "format": p.suffix.lstrip(".")}
    return None


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def _write_to_db(
    date_val: date_type,
    kind: str,
    content: str,
    format: str,
    agent: Optional[str],
    metadata: Optional[dict],
) -> str:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO daily_outputs (date, kind, agent, format, content, metadata, created_at)
                VALUES (:date, :kind, :agent, :format, :content, :metadata, NOW())
                RETURNING id
                """
            ),
            {
                "date": date_val,
                "kind": kind,
                "agent": agent,
                "format": format,
                "content": content,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )
        row = result.fetchone()
    return f"daily_outputs:{row.id}"


def _list_from_db(*, kind: Optional[str], limit: int) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        if kind:
            rows = conn.execute(
                text(
                    "SELECT id, date, kind, agent, format, created_at FROM daily_outputs"
                    " WHERE kind = :kind ORDER BY date DESC, created_at DESC LIMIT :limit"
                ),
                {"kind": kind, "limit": limit},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    "SELECT id, date, kind, agent, format, created_at FROM daily_outputs"
                    " ORDER BY date DESC, created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).fetchall()
    return [dict(r._mapping) for r in rows]


def _get_from_db(db_id: int) -> Optional[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM daily_outputs WHERE id = :id"),
            {"id": db_id},
        ).fetchone()
    return dict(row._mapping) if row else None


# ---------------------------------------------------------------------------
# SQLite / filesystem helpers
# ---------------------------------------------------------------------------

def _write_to_file(date_val: date_type, kind: str, content: str, format: str) -> str:
    """Write content to workspace/daily-logs/ and return the file path.

    NOTE: In normal SQLite operation the Claude subprocess has already written
    the file.  This path is only reached when write_daily_output is called
    directly (e.g. from tests or future tooling that generates content in Python).
    """
    DAILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"[C] {date_val.isoformat()}-{kind}.{format}"
    path = DAILY_LOGS_DIR / fname
    path.write_text(content, encoding="utf-8")
    return str(path)


def _list_from_dir(*, kind: Optional[str], limit: int) -> list[dict]:
    if not DAILY_LOGS_DIR.exists():
        return []
    entries = []
    for p in sorted(DAILY_LOGS_DIR.iterdir(), reverse=True):
        if p.suffix not in (".md", ".html"):
            continue
        if kind and kind not in p.name:
            continue
        entries.append({"path": str(p), "format": p.suffix.lstrip(".")})
        if len(entries) >= limit:
            break
    return entries

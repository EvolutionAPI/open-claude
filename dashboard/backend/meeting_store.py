"""Meeting transcript storage — bifurcated by dialect.

PG mode:  upsert_meeting() writes to the `meeting_transcripts` table
          (schema created by migration 0011_native_logs_schema).
SQLite mode: keeps current file layout in workspace/meetings/.

Public API
----------
    upsert_meeting(**kwargs)  -> str          # idempotent upsert, returns identifier
    list_recent_meetings(limit) -> list[dict]
    get_meeting(fathom_id)    -> dict | None
    import_from_files()       -> int          # PG only: ingest raw JSON from files
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from db.engine import dialect, get_engine

logger = logging.getLogger(__name__)

# workspace/meetings/ is two levels up from dashboard/backend/
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
MEETINGS_DIR = WORKSPACE_ROOT / "workspace" / "meetings"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_meeting(
    *,
    fathom_id: str,
    title: str,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    duration_seconds: Optional[int] = None,
    attendees: Optional[list] = None,
    transcript_full: Optional[str] = None,
    summary: Optional[str] = None,
    action_items: Optional[list] = None,
    raw_payload: Optional[dict] = None,
) -> str:
    """Idempotent upsert by fathom_id. Returns a string identifier."""
    if dialect.name == "postgresql":
        return _upsert_db(
            fathom_id, title, started_at, ended_at, duration_seconds,
            attendees, transcript_full, summary, action_items, raw_payload,
        )
    return _upsert_file(fathom_id, title, started_at, transcript_full, summary, raw_payload)


def list_recent_meetings(limit: int = 30) -> list[dict]:
    """Return recent meetings ordered by started_at DESC."""
    if dialect.name == "postgresql":
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, fathom_id, title, started_at, ended_at,
                       duration_seconds, synced_at
                FROM meeting_transcripts
                ORDER BY started_at DESC NULLS LAST
                LIMIT :limit
            """), {"limit": limit}).fetchall()
            return [dict(r._mapping) for r in rows]
    # SQLite: scan raw directory
    raw_dir = MEETINGS_DIR / "raw"
    if not raw_dir.exists():
        return []
    out: list[dict] = []
    for f in sorted(raw_dir.glob("**/*.json"), reverse=True)[:limit]:
        out.append({"path": str(f), "fathom_id": f.stem})
    return out


def get_meeting(fathom_id: str) -> Optional[dict]:
    """Fetch a single meeting by fathom_id. Returns None if not found."""
    if dialect.name == "postgresql":
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM meeting_transcripts WHERE fathom_id = :fid"),
                {"fid": fathom_id},
            ).fetchone()
            return dict(row._mapping) if row else None
    # SQLite: read files
    # The skill writes raw JSONs into workspace/meetings/fathom/YYYY-MM-DD/*.json
    # and summaries into workspace/meetings/summaries/**/*.md
    data: dict = {"fathom_id": fathom_id}
    # Search raw JSON under fathom/ (nested by date)
    found_json: Optional[Path] = None
    for f in (MEETINGS_DIR / "fathom").glob("**/*.json") if (MEETINGS_DIR / "fathom").exists() else []:
        if fathom_id in f.stem:
            found_json = f
            break
    # Fallback: legacy raw/ directory
    if found_json is None:
        for f in (MEETINGS_DIR / "raw").glob("**/*.json") if (MEETINGS_DIR / "raw").exists() else []:
            if fathom_id in f.stem:
                found_json = f
                break
    if found_json is None:
        return None
    data["raw_payload"] = json.loads(found_json.read_text(encoding="utf-8"))
    # Summaries
    for f in (MEETINGS_DIR / "summaries").glob("**/*.md") if (MEETINGS_DIR / "summaries").exists() else []:
        if fathom_id in f.stem:
            data["summary"] = f.read_text(encoding="utf-8")
            break
    return data


def import_from_files() -> int:
    """PG only: scan workspace/meetings/ raw JSON files and upsert into DB.

    Returns the count of newly upserted records.  Idempotent — safe to run
    repeatedly; existing fathom_ids are updated, not duplicated.
    Raises RuntimeError if called in SQLite mode.
    """
    if dialect.name != "postgresql":
        raise RuntimeError("import_from_files() is only supported in PostgreSQL mode")

    count = 0
    # Skill writes to workspace/meetings/fathom/YYYY-MM-DD/*.json
    search_dirs = [MEETINGS_DIR / "fathom", MEETINGS_DIR / "raw"]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for f in sorted(search_dir.glob("**/*.json")):
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("meeting_store: skipping %s — %s", f, exc)
                continue

            fathom_id = payload.get("id") or payload.get("fathom_id") or f.stem
            title = payload.get("title", f.stem)

            # Parse started_at from multiple possible field names
            started_raw = payload.get("started_at") or payload.get("created_at")
            started_at: Optional[datetime] = None
            if started_raw:
                try:
                    started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            ended_raw = payload.get("ended_at")
            ended_at: Optional[datetime] = None
            if ended_raw:
                try:
                    ended_at = datetime.fromisoformat(ended_raw.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            attendees = payload.get("attendees") or payload.get("calendar_invitees")
            action_items = payload.get("action_items")
            summary_text = (
                (payload.get("default_summary") or {}).get("markdown_formatted")
                or payload.get("summary")
            )

            upsert_meeting(
                fathom_id=str(fathom_id),
                title=title,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=payload.get("duration"),
                attendees=attendees if isinstance(attendees, list) else None,
                transcript_full=payload.get("transcript"),
                summary=summary_text,
                action_items=action_items if isinstance(action_items, list) else None,
                raw_payload=payload,
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert_db(
    fathom_id: str,
    title: str,
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
    duration_seconds: Optional[int],
    attendees: Optional[list],
    transcript_full: Optional[str],
    summary: Optional[str],
    action_items: Optional[list],
    raw_payload: Optional[dict],
) -> str:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO meeting_transcripts
                (fathom_id, title, started_at, ended_at, duration_seconds,
                 attendees, transcript_full, summary, action_items, raw_payload)
            VALUES (:fid, :title, :started, :ended, :dur,
                    :att, :full, :summary, :act, :raw)
            ON CONFLICT (fathom_id) DO UPDATE SET
                title            = EXCLUDED.title,
                started_at       = EXCLUDED.started_at,
                ended_at         = EXCLUDED.ended_at,
                duration_seconds = EXCLUDED.duration_seconds,
                attendees        = EXCLUDED.attendees,
                transcript_full  = EXCLUDED.transcript_full,
                summary          = EXCLUDED.summary,
                action_items     = EXCLUDED.action_items,
                raw_payload      = EXCLUDED.raw_payload,
                synced_at        = NOW()
        """), {
            "fid":     fathom_id,
            "title":   title,
            "started": started_at,
            "ended":   ended_at,
            "dur":     duration_seconds,
            "att":     json.dumps(attendees)   if attendees    is not None else None,
            "full":    transcript_full,
            "summary": summary,
            "act":     json.dumps(action_items) if action_items is not None else None,
            "raw":     json.dumps(raw_payload)  if raw_payload  is not None else None,
        })
    return f"meeting_transcripts:fathom_id={fathom_id}"


def _upsert_file(
    fathom_id: str,
    title: str,
    started_at: Optional[datetime],
    transcript_full: Optional[str],
    summary: Optional[str],
    raw_payload: Optional[dict],
) -> str:
    """SQLite mode: keep current file layout in workspace/meetings/."""
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

    date_str = (
        started_at.strftime("%Y-%m-%d")
        if started_at
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    slug = _make_slug(title)

    # Raw JSON — mirrors the layout the skill uses: fathom/YYYY-MM-DD/*.json
    fathom_dir = MEETINGS_DIR / "fathom" / date_str
    fathom_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date_str}__{fathom_id}__{slug}.json"
    if raw_payload:
        (fathom_dir / fname).write_text(
            json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # Summary markdown
    if summary:
        sum_dir = MEETINGS_DIR / "summaries"
        sum_dir.mkdir(parents=True, exist_ok=True)
        sum_fname = f"{date_str}__{fathom_id}__{slug}.summary.md"
        (sum_dir / sum_fname).write_text(summary, encoding="utf-8")

    return f"meetings/{fathom_id}"


def _make_slug(title: str) -> str:
    """Convert title to a URL-friendly slug (matches skill convention)."""
    import re
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:80] or "meeting"

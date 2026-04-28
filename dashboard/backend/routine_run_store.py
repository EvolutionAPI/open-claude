"""Routine run persistence — dialect-bifurcated stdout/stderr capture.

PostgreSQL mode: INSERT into routine_runs table.
SQLite mode:     write a plain-text log file under ADWs/logs/routines/.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from config_store import get_dialect
from db.engine import get_engine

log = logging.getLogger(__name__)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SQLITE_LOG_DIR = WORKSPACE_ROOT / "workspace" / "ADWs" / "logs" / "routines"

MAX_LEN = 1024 * 1024  # 1 MB per stream


def persist_routine_run(
    *,
    routine_id: Optional[int] = None,
    routine_slug: str,
    started_at: datetime,
    ended_at: datetime,
    exit_code: int,
    stdout: str,
    stderr: str,
    triggered_by: str = "scheduler",
    metadata: Optional[dict] = None,
) -> None:
    """Persist the result of a routine execution.

    Parameters
    ----------
    routine_id:    FK to routine_definitions (PG only; None in SQLite mode)
    routine_slug:  human-readable routine identifier (denormalised)
    started_at:    timezone-aware UTC datetime of start
    ended_at:      timezone-aware UTC datetime of end
    exit_code:     process return code
    stdout:        captured stdout (truncated to 1 MB)
    stderr:        captured stderr (truncated to 1 MB)
    triggered_by:  scheduler | manual | api
    metadata:      optional arbitrary dict (serialised as JSON in PG)
    """
    # Truncation
    truncated = len(stdout) > MAX_LEN or len(stderr) > MAX_LEN
    if len(stdout) > MAX_LEN:
        stdout = stdout[:MAX_LEN] + "\n...[TRUNCATED]"
    if len(stderr) > MAX_LEN:
        stderr = stderr[:MAX_LEN] + "\n...[TRUNCATED]"

    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    try:
        if get_dialect() == "postgresql":
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO routine_runs
                            (routine_id, routine_slug, started_at, ended_at, duration_ms,
                             exit_code, stdout, stderr, truncated, triggered_by, metadata)
                        VALUES (:rid, :slug, :start, :end, :dur, :exit, :out, :err,
                                :trunc, :tby, :meta)
                        """
                    ),
                    {
                        "rid": routine_id,
                        "slug": routine_slug,
                        "start": started_at,
                        "end": ended_at,
                        "dur": duration_ms,
                        "exit": exit_code,
                        "out": stdout,
                        "err": stderr,
                        "trunc": truncated,
                        "tby": triggered_by,
                        "meta": json.dumps(metadata) if metadata else None,
                    },
                )
        else:
            SQLITE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            ts = started_at.strftime("%Y%m%dT%H%M%S")
            path = SQLITE_LOG_DIR / f"{routine_slug}-{ts}.log"
            path.write_text(
                f"=== stdout ===\n{stdout}\n\n=== stderr ===\n{stderr}\n",
                encoding="utf-8",
            )
    except Exception as exc:
        log.warning("[routine_run_store] failed to persist run for %s: %s", routine_slug, exc)

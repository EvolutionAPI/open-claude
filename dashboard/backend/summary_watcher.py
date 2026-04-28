"""Summary Watcher — background heartbeat (system heartbeat) that monitors ticket
thread JSONL files and enqueues summary jobs when enough new turns accumulate.

Invoked as a system heartbeat (agent=system, heartbeat_id=summary-watcher).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent
LOGS_DIR = WORKSPACE / "ADWs" / "logs" / "chat"
SUMMARY_EVERY_N = 20   # must match tickets.py SUMMARY_EVERY_N


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _count_lines(path: Path) -> int:
    """Count newline-delimited JSON messages in a JSONL file via streaming."""
    count = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    count += 1
    except OSError:
        pass
    return count


def _find_jsonl(session_id: str, agent_name: str | None) -> Path | None:
    """Locate JSONL file for a given session_id."""
    if agent_name:
        candidate = LOGS_DIR / agent_name / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    flat = LOGS_DIR / f"{session_id}.jsonl"
    if flat.exists():
        return flat
    return None


def _enqueue_summary(ticket_id: str, memory_md_path: str, up_to_turn: int) -> None:
    """Spawn summary_worker.py as a fire-and-forget subprocess."""
    worker = Path(__file__).resolve().parent / "summary_worker.py"
    if not worker.exists():
        print(f"[summary_watcher] summary_worker.py not found at {worker}", flush=True)
        return
    subprocess.Popen(
        [sys.executable, str(worker),
         "--ticket-id", ticket_id,
         "--memory-path", memory_md_path,
         "--up-to-turn", str(up_to_turn)],
        start_new_session=True,
    )
    print(f"[summary_watcher] summary job queued for ticket {ticket_id} (turn {up_to_turn})", flush=True)


def run_watcher() -> dict:
    """Main logic — returns stats dict."""
    from db.session import get_session

    stats = {"checked": 0, "updated": 0, "queued": 0, "skipped": 0}

    try:
        with get_session() as session:
            rows = session.execute(text(
                "SELECT id, assignee_agent, thread_session_id, memory_md_path, "
                "message_count, last_summary_at_message "
                "FROM tickets "
                "WHERE memory_md_path IS NOT NULL AND status != 'archived'"
            )).fetchall()

            now = _now_iso()

            for row in rows:
                ticket_id = row.id
                session_id = row.thread_session_id
                agent_name = row.assignee_agent
                memory_md_path = row.memory_md_path
                db_count = row.message_count
                last_summary = row.last_summary_at_message

                stats["checked"] += 1

                if not session_id:
                    stats["skipped"] += 1
                    continue  # No session yet — nothing to count

                jsonl = _find_jsonl(session_id, agent_name)
                if jsonl is None:
                    stats["skipped"] += 1
                    continue

                # mtime pre-filter: skip if file hasn't changed recently
                try:
                    mtime = jsonl.stat().st_mtime
                    import time
                    if time.time() - mtime > 70:  # heartbeat is 60s; 10s buffer
                        stats["skipped"] += 1
                        continue
                except OSError:
                    stats["skipped"] += 1
                    continue

                actual_count = _count_lines(jsonl)
                if actual_count == db_count:
                    stats["skipped"] += 1
                    continue

                # Update message_count monotonically
                if actual_count > db_count:
                    session.execute(
                        text("UPDATE tickets SET message_count = :mc, updated_at = :now "
                             "WHERE id = :id AND message_count < :mc"),
                        {"mc": actual_count, "now": now, "id": ticket_id},
                    )
                    session.commit()
                    stats["updated"] += 1
                    new_count = actual_count
                else:
                    new_count = db_count  # actual < db: trust DB (rewind scenario)

                delta = new_count - last_summary
                if delta >= SUMMARY_EVERY_N:
                    result = session.execute(
                        text("UPDATE tickets SET last_summary_at_message = :mc, updated_at = :now "
                             "WHERE id = :id AND last_summary_at_message < :mc"),
                        {"mc": new_count, "now": now, "id": ticket_id},
                    )
                    session.commit()
                    if result.rowcount > 0:
                        _enqueue_summary(ticket_id, memory_md_path, new_count)
                        stats["queued"] += 1

    except Exception as exc:
        return {"error": str(exc)}

    return stats


def main():
    print(f"[summary_watcher] Starting at {_now_iso()}", flush=True)
    stats = run_watcher()
    print(f"[summary_watcher] Done: {json.dumps(stats)}", flush=True)
    if "error" in stats:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

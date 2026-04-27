"""Summary Worker — thread-areas (Feature thread-areas, Passo 4b).

CLI usage:
    python summary_worker.py --ticket-id <uuid> --memory-path <rel-path> --up-to-turn <int>

Reads the last SUMMARY_CHUNK_TURNS messages from the ticket's JSONL log,
calls Claude (Haiku) to generate a summary section, and appends it to memory.md.
Spawned as fire-and-forget by tickets.py `_enqueue_summary()`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent
SUMMARY_CHUNK_TURNS = 20          # matches SUMMARY_EVERY_N in tickets.py
LOGS_DIR = WORKSPACE / "ADWs" / "logs" / "chat"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _find_jsonl(ticket_id: str) -> Path | None:
    """Find the JSONL for the ticket's thread_session_id via DB lookup."""
    from db.session import get_session

    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT thread_session_id, assignee_agent FROM tickets WHERE id = :id"),
                {"id": ticket_id},
            ).fetchone()
    except Exception as exc:
        print(f"[summary_worker] DB error for ticket {ticket_id}: {exc}", flush=True)
        return None

    if not row or not row.thread_session_id:
        print(f"[summary_worker] No thread_session_id for ticket {ticket_id}", flush=True)
        return None
    session_id, agent_name = row.thread_session_id, row.assignee_agent or "unknown"
    # ChatLogger writes to ADWs/logs/chat/{agent_name}/{session_id}.jsonl
    candidate = LOGS_DIR / agent_name / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate
    # Fallback: flat directory
    flat = LOGS_DIR / f"{session_id}.jsonl"
    if flat.exists():
        return flat
    print(f"[summary_worker] JSONL not found for session {session_id}", flush=True)
    return None


def _read_last_n_turns(jsonl_path: Path, n: int) -> list[dict]:
    """Stream JSONL and return last N assistant/user messages."""
    messages: list[dict] = []
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = obj.get("role")
                if role in ("user", "assistant"):
                    messages.append(obj)
    except OSError as exc:
        print(f"[summary_worker] Cannot read JSONL {jsonl_path}: {exc}", flush=True)
        return []
    return messages[-n:]


def _call_claude_for_summary(messages: list[dict]) -> str | None:
    """Call Claude Haiku to summarize a chunk of messages."""
    import subprocess
    import shutil

    claude_bin = shutil.which("claude")
    if not claude_bin:
        print("[summary_worker] claude binary not found", flush=True)
        return None

    context = "\n\n".join(
        f"[{msg['role'].upper()}]: {msg.get('content','')[:500]}"
        for msg in messages
    )
    prompt = (
        "You are a concise summarizer. Summarize the following conversation chunk "
        "in 3-5 bullet points suitable for appending to a memory.md file. "
        "Focus on key decisions, actions taken, and open questions.\n\n"
        f"CONVERSATION:\n{context}\n\nSUMMARY:"
    )

    try:
        result = subprocess.run(
            [claude_bin, "--print", "--max-turns", "1", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:
        print(f"[summary_worker] Claude call failed: {exc}", flush=True)
    return None


def main():
    parser = argparse.ArgumentParser(description="Summary Worker")
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--memory-path", required=True)
    parser.add_argument("--up-to-turn", type=int, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    jsonl_path = _find_jsonl(args.ticket_id)
    if not jsonl_path:
        sys.exit(0)  # Nothing to do

    messages = _read_last_n_turns(jsonl_path, SUMMARY_CHUNK_TURNS)
    if not messages:
        sys.exit(0)

    summary = _call_claude_for_summary(messages)
    if not summary:
        sys.exit(0)

    # Append to memory.md
    memory_path = WORKSPACE / args.memory_path
    try:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_path, "a", encoding="utf-8") as f:
            timestamp = _now_iso()
            f.write(f"\n\n## Summary — turns up to {args.up_to_turn} (generated {timestamp})\n\n")
            f.write(summary + "\n")
        print(f"[summary_worker] Summary appended to {memory_path}", flush=True)
    except OSError as exc:
        print(f"[summary_worker] Could not write to {memory_path}: {exc}", flush=True)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

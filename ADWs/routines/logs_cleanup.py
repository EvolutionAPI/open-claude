"""TTL cleanup for native logs (PG mode only).

In SQLite mode this is a no-op. In PG, deletes rows older than the
configured retention per category.

Override defaults via env:
    EVONEXUS_LOGS_RETAIN_CHAT_DAYS=180
    EVONEXUS_LOGS_RETAIN_DAILY_OUTPUTS_DAYS=365
    EVONEXUS_LOGS_RETAIN_PLUGIN_HOOK_RUNS_DAYS=30
    EVONEXUS_LOGS_RETAIN_HEARTBEAT_RUN_PROMPTS_DAYS=60
    EVONEXUS_LOGS_RETAIN_WORKSPACE_MUTATIONS_DAYS=180
    EVONEXUS_LOGS_RETAIN_ROUTINE_RUNS_DAYS=60
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "dashboard" / "backend"))

from config_store import get_dialect
from db.engine import get_engine
from sqlalchemy import text


# Defaults approved by Davidson
DEFAULTS_DAYS: dict[str, int] = {
    "chat": 90,
    "daily_outputs": 180,
    "plugin_hook_runs": 14,
    "heartbeat_run_prompts": 30,
    "workspace_mutations": 90,
    "routine_runs": 30,
}

# Categories with infinite retention (never delete)
SKIPPED = {"meeting_transcripts", "audit_log", "brain_repo_transcripts"}


def _retain_days(category: str) -> int:
    env_var = f"EVONEXUS_LOGS_RETAIN_{category.upper()}_DAYS"
    return int(os.environ.get(env_var, DEFAULTS_DAYS[category]))


def _delete_older_than(
    table: str, ts_column: str, days: int, pk_column: str = "id"
) -> int:
    """Batch-delete rows older than *days* from *table*. Returns total deleted.

    *pk_column* defaults to "id" but can be overridden for tables that use a
    different primary key (e.g. heartbeat_run_prompts uses "run_id").
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    engine = get_engine()
    deleted = 0
    batch = 10_000
    with engine.begin() as conn:
        while True:
            result = conn.execute(
                text(
                    f"DELETE FROM {table}"
                    f" WHERE {pk_column} IN ("
                    f"   SELECT {pk_column} FROM {table}"
                    f"   WHERE {ts_column} < :cutoff"
                    f"   LIMIT :batch"
                    f")"
                ),
                {"cutoff": cutoff, "batch": batch},
            )
            n = result.rowcount or 0
            deleted += n
            if n < batch:
                break
    return deleted


def cleanup() -> dict[str, int]:
    """Run all TTL deletions. Returns summary {category: deleted_count}.

    No-op in SQLite mode — returns an empty dict.
    """
    if get_dialect() != "postgresql":
        print("logs-cleanup: SQLite mode — no-op")
        return {}

    summary: dict[str, int] = {}

    # chat messages
    summary["chat"] = _delete_older_than(
        "agent_chat_messages", "ts", _retain_days("chat")
    )
    # orphaned sessions (all messages already deleted, session itself is stale)
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "DELETE FROM agent_chat_sessions"
                " WHERE id NOT IN ("
                "   SELECT DISTINCT session_id FROM agent_chat_messages"
                " )"
                " AND last_activity_at < NOW() - (:days || ' days')::INTERVAL"
            ),
            {"days": _retain_days("chat")},
        )
        summary["chat_sessions_orphaned"] = result.rowcount or 0

    summary["daily_outputs"] = _delete_older_than(
        "daily_outputs", "created_at", _retain_days("daily_outputs")
    )
    summary["plugin_hook_runs"] = _delete_older_than(
        "plugin_hook_runs", "started_at", _retain_days("plugin_hook_runs")
    )
    summary["heartbeat_run_prompts"] = _delete_older_than(
        "heartbeat_run_prompts", "created_at", _retain_days("heartbeat_run_prompts"),
        pk_column="run_id",
    )
    summary["workspace_mutations"] = _delete_older_than(
        "workspace_mutations", "ts", _retain_days("workspace_mutations")
    )
    summary["routine_runs"] = _delete_older_than(
        "routine_runs", "started_at", _retain_days("routine_runs")
    )

    return summary


def main() -> int:
    summary = cleanup()
    total = sum(v for v in summary.values() if isinstance(v, int))
    if not summary:
        return 0
    print(f"logs-cleanup: {total} rows deleted")
    for cat, n in sorted(summary.items()):
        if n > 0:
            print(f"  {cat}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

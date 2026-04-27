"""
db/listeners.py — SQLAlchemy event listeners (observability layer).

These listeners are for OBSERVABILITY ONLY — they are NOT the source of
truth for goal progress.  The authoritative increment is performed by the
DB-side trigger `trg_task_done_updates_goal` (created in Alembic migration
0003_goal_trigger.py).

Purpose of this layer (ADR PG-Q3):
  - Count how many GoalTask status→'done' transitions pass through the ORM.
  - Surface a warning when the Python-side count diverges from the DB count
    (useful during the SQLite → PostgreSQL migration window).
  - Provide a hook for future metrics/alerting without touching the trigger.

Usage — register once at app boot:
    from db.listeners import register_all
    register_all()

The register_all() call is idempotent (SQLAlchemy deduplicates same-target
listeners by default when propagate=False and the same function object is
passed twice).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Thread-local counter: tracks GoalTask done-transitions observed by ORM
# during the current request/run. Separate from DB ground truth.
_orm_counter: threading.local = threading.local()


def _get_orm_count() -> int:
    """Return the ORM-observed done-transition count for this thread."""
    return getattr(_orm_counter, "done_count", 0)


def _increment_orm_count() -> None:
    _orm_counter.done_count = _get_orm_count() + 1


def reset_orm_count() -> None:
    """Reset the counter for this thread (call between requests in tests)."""
    _orm_counter.done_count = 0


def _on_goal_task_after_update(mapper, connection, target) -> None:  # noqa: ANN001
    """Observability hook — fires after SQLAlchemy flushes a GoalTask UPDATE.

    This listener deliberately does NOT increment current_value on the Goal.
    That is the DB trigger's responsibility.  Here we only track and log
    so that divergence between ORM-path and trigger-path can be detected.
    """
    if target.status == "done":
        _increment_orm_count()
        logger.debug(
            "goal_progress_listener: task_id=%s goal_id=%s status→done "
            "(orm_thread_total=%d)",
            target.id,
            target.goal_id,
            _get_orm_count(),
        )


def register_all() -> None:
    """Register all SQLAlchemy event listeners.

    Safe to call multiple times — SQLAlchemy deduplicates listeners that
    use the same (target, identifier, fn) triple.
    """
    try:
        from sqlalchemy import event as sa_event
        from models import GoalTask  # late import to avoid circular at module load

        sa_event.listen(
            GoalTask,
            "after_update",
            _on_goal_task_after_update,
            propagate=False,
        )
        logger.debug("db.listeners: registered GoalTask after_update listener")
    except ImportError as exc:
        # models not yet importable (e.g. standalone script context) — skip silently
        logger.debug("db.listeners: skipping registration (%s)", exc)

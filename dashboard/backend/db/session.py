"""
db/session.py — session factory for standalone (non-Flask) scripts.

Flask routes continue to use Flask-SQLAlchemy's db.session.
This factory is for scripts that run outside of a Flask app context:
  heartbeat_runner, heartbeat_dispatcher, goal_context, claude_hook_dispatcher,
  summary_watcher, summary_worker, plugin_scan_runner, etc.

Usage:
    from db.session import get_session

    with get_session() as session:
        rows = session.execute(text("SELECT * FROM heartbeats")).fetchall()
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from db.engine import get_engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager that yields a SQLAlchemy Session and handles commit/rollback."""
    engine = get_engine()
    session = Session(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

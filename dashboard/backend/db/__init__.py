"""
dashboard/backend/db — database abstraction layer.

Public surface:
    from db import get_engine, get_session, dialect

    dialect  — sqlalchemy.engine.interfaces.Dialect (use dialect.name in ("sqlite","postgresql"))
    get_engine()   — returns the shared SQLAlchemy engine (Flask-unaware)
    get_session()  — returns a new scoped/regular Session (Flask-unaware)

For Flask routes that already use Flask-SQLAlchemy's db.session, continue using db.session.
This module is the path for standalone scripts (heartbeat_runner, goal_context, etc.) that
run outside of a Flask app context.

Allowlist note: raw sqlite3.connect() is permitted ONLY inside this package and in
dashboard/alembic/env.py.  All other usage is blocked by CI grep guards.
"""

from db.engine import get_engine, dialect  # noqa: F401 — re-exported
from db.session import get_session          # noqa: F401 — re-exported

__all__ = ["get_engine", "get_session", "dialect"]

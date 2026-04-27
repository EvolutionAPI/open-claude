"""
db/exceptions.py — typed exceptions for the database abstraction layer.

These are raised by the engine factory and pool monitoring code.
HTTP routes should catch PoolExhaustedError and return 503.
"""

from __future__ import annotations


class PoolExhaustedError(RuntimeError):
    """Raised when the SQLAlchemy connection pool is exhausted (pool_timeout exceeded).

    HTTP routes should catch this and return 503 Service Unavailable with
    Retry-After: 30 header.
    """


class MigrationDriftError(RuntimeError):
    """Raised when the Alembic revision in the DB does not match the expected head.

    The evonexus-migrate tool raises this when source and target are at
    different revisions.
    """


class OrphanLockError(RuntimeError):
    """Raised when a locked ticket has exceeded its lock_timeout_seconds and the
    janitor cannot safely release it due to a race with an active checkout.
    """

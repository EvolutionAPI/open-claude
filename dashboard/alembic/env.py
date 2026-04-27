"""Alembic env.py for the EvoNexus dashboard database.

Reads DATABASE_URL from the environment (same variable as app.py).
Falls back to the legacy SQLite path so existing deployments see zero
behaviour change (AC1 invariant).

Usage:
    cd dashboard/alembic && alembic upgrade head
    cd dashboard/alembic && alembic revision --autogenerate -m "description"

NOTE: raw sqlite3.connect() is intentionally used below to inspect the
alembic_version table for the legacy-stamp bootstrap. This is one of the
two allowlisted call sites per dashboard/backend/db/ALLOWLIST.md.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# ---------------------------------------------------------------------------
# Add backend to sys.path so db.engine can be imported
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent / "backend"
sys.path.insert(0, str(_BACKEND))

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Inject DATABASE_URL
# ---------------------------------------------------------------------------
_WORKSPACE = _HERE.parent.parent
_DEFAULT_DB_PATH = _WORKSPACE / "dashboard" / "data" / "evonexus.db"
_DEFAULT_URL = f"sqlite:///{_DEFAULT_DB_PATH}"

_database_url: str = os.environ.get("DATABASE_URL", "") or _DEFAULT_URL

# Normalise postgres:// → postgresql+psycopg2://
if _database_url.startswith("postgres://"):
    _database_url = "postgresql+psycopg2://" + _database_url[len("postgres://"):]
elif _database_url.startswith("postgresql://") and "+psycopg2" not in _database_url:
    _database_url = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

config.set_main_option("sqlalchemy.url", _database_url)

target_metadata = None  # autogenerate disabled — migrations are hand-written


# ---------------------------------------------------------------------------
# Legacy-stamp bootstrap helper
# ---------------------------------------------------------------------------
def _stamp_if_legacy(connection) -> None:  # noqa: ANN001
    """If the DB has data but no alembic_version row, stamp it as head.

    This handles existing pre-Alembic installs — their schema is already at
    the baseline so we stamp rather than try to run migrations from scratch.
    """
    try:
        row = connection.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).fetchone()
        if row is not None:
            return  # already stamped
    except Exception:
        connection.rollback()  # Postgres: reset aborted transaction before next statement

    # Check whether ANY dashboard table exists (indicates a legacy install)
    try:
        dialect_name = connection.dialect.name
        if dialect_name == "sqlite":
            result = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='tickets' LIMIT 1")
            ).fetchone()
        else:
            result = connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='tickets' LIMIT 1"
                )
            ).fetchone()

        if result is not None:
            # Legacy install detected — stamp head directly via SQL to avoid
            # recursive env.py execution (calling alembic.command.stamp() re-runs
            # env.py and crashes the Alembic context globals).
            try:
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL)"
                ))
                connection.execute(text(
                    "DELETE FROM alembic_version"
                ))
                connection.execute(text(
                    "INSERT INTO alembic_version (version_num) VALUES ('0001')"
                ))
                connection.commit()
                print("[alembic/env.py] legacy-stamp bootstrap: stamped as 0001")
            except Exception as _stamp_exc:
                try:
                    connection.rollback()
                except Exception:
                    pass
                print(f"[alembic/env.py] legacy-stamp bootstrap failed: {_stamp_exc}")
    except Exception as exc:
        print(f"[alembic/env.py] legacy-stamp bootstrap skipped: {exc}")


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Run the legacy-stamp check using a SEPARATE, short-lived connection so
    # that any rollback/commit inside _stamp_if_legacy never touches the
    # migration connection. Postgres aborts the current transaction on any
    # SQL error; if we shared a connection, the rollback would wipe the
    # Alembic migration context.
    with connectable.connect() as stamp_connection:
        _stamp_if_legacy(stamp_connection)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

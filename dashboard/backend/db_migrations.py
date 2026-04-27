from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config

from structured_logging import emit_json_log


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def build_alembic_config(database_uri: str) -> Config:
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_uri)
    return config


def run_database_migrations(database_uri: str) -> None:
    scheme = urlparse(database_uri).scheme or "unknown"
    emit_json_log(
        "info",
        "database_migration_start",
        service="dashboard",
        database_scheme=scheme,
        script_location=str(MIGRATIONS_DIR),
    )
    try:
        command.upgrade(build_alembic_config(database_uri), "head")
    except Exception as exc:
        emit_json_log(
            "error",
            "database_migration_failed",
            service="dashboard",
            database_scheme=scheme,
            error=str(exc),
        )
        raise
    emit_json_log(
        "info",
        "database_migration_complete",
        service="dashboard",
        database_scheme=scheme,
        revision="head",
    )

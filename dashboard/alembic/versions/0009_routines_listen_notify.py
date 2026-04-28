"""Routines LISTEN/NOTIFY trigger for cache invalidation.

Creates a PG trigger on the routine_definitions table that fires
pg_notify('config_changed', payload) after INSERT, UPDATE, or DELETE.
SQLite is a no-op (no trigger support needed — SQLite path reloads via
YAML on each call).

Payload schema: {"table": "routine_definitions", "op": "INSERT|UPDATE|DELETE", "id": <int>}

Consumer: scheduler._start_routine_listen_thread() listens on 'config_changed'
and calls _reload_routines() on relevant payloads.

Note: schedule column in routine_definitions stores a human-readable description
("daily 06:50", "every 30min", "weekly fri 09:00") for UI display only.
The actual scheduling decision is made by the scheduler reading config_json,
which preserves the original YAML shape ({"time": "06:50"} etc.).

Phase reference: pg-native-configs Fase 4
ADR: PG-NC-8 (single-connection LISTEN direct, 1 dedicated PG conn per listener).
     TODO(PG-NC-8): consolidate via multiplexer if connection budget becomes issue.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_pg():
        return  # SQLite: no-op — YAML-based reload, no trigger needed.

    op.execute("""
        CREATE OR REPLACE FUNCTION notify_routine_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'config_changed',
                json_build_object(
                    'table', 'routine_definitions',
                    'op',    TG_OP,
                    'id',    COALESCE(NEW.id, OLD.id)
                )::text
            );
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_routine_definitions_notify ON routine_definitions;
    """)

    op.execute("""
        CREATE TRIGGER trg_routine_definitions_notify
        AFTER INSERT OR UPDATE OR DELETE ON routine_definitions
        FOR EACH ROW EXECUTE FUNCTION notify_routine_change();
    """)


def downgrade() -> None:
    if not _is_pg():
        return

    op.execute("DROP TRIGGER IF EXISTS trg_routine_definitions_notify ON routine_definitions;")
    op.execute("DROP FUNCTION IF EXISTS notify_routine_change();")

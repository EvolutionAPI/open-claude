"""Heartbeats LISTEN/NOTIFY trigger for cache invalidation.

Creates a PG trigger on the heartbeats table that fires pg_notify('config_changed',
payload) after INSERT, UPDATE, or DELETE.  SQLite is a no-op (no trigger support
needed — SQLite path reloads via YAML on each call).

Payload schema: {"table": "heartbeats", "op": "INSERT|UPDATE|DELETE", "id": "<id>"}

Consumer: heartbeat_dispatcher._start_listen_thread() listens on 'config_changed'
and calls _reload_definitions() on relevant payloads.

Phase reference: pg-native-configs Fase 3
ADR: PG-NC-8 (single-multiplexer target; this migration ships the trigger regardless
     of which listener architecture is active — trigger fires for any listener).

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_pg():
        return  # SQLite: no-op — YAML-based reload, no trigger needed.

    op.execute("""
        CREATE OR REPLACE FUNCTION notify_heartbeat_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'config_changed',
                json_build_object(
                    'table', 'heartbeats',
                    'op',    TG_OP,
                    'id',    COALESCE(NEW.id, OLD.id)
                )::text
            );
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_heartbeats_notify ON heartbeats;
    """)

    op.execute("""
        CREATE TRIGGER trg_heartbeats_notify
        AFTER INSERT OR UPDATE OR DELETE ON heartbeats
        FOR EACH ROW EXECUTE FUNCTION notify_heartbeat_change();
    """)


def downgrade() -> None:
    if not _is_pg():
        return

    op.execute("DROP TRIGGER IF EXISTS trg_heartbeats_notify ON heartbeats;")
    op.execute("DROP FUNCTION IF EXISTS notify_heartbeat_change();")

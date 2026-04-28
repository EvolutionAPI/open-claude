"""Schema cleanup — Category E: align systems/scheduled_tasks/triggers/trigger_executions.

The four tables were created in 0002 with a minimal "config_json blob" design
that was never wired into application code.  All routes and seeds use the full
ORM column set.  With zero rows in all four tables the cleanup is safe.

systems
  REMOVE: slug (UNIQUE), config_json, enabled
  ADD:    url, container, icon, type

scheduled_tasks
  REMOVE: task_type, config_json, updated_at
  ADD:    description, type, payload, agent, scheduled_at, started_at,
          completed_at, result_summary, error, created_by (FK users.id)

triggers
  REMOVE: trigger_type, config_json
  ADD:    slug (UNIQUE), type, source, event_filter, action_type,
          action_payload, agent, secret, from_yaml, remote_trigger_id,
          created_by (FK users.id), updated_at

trigger_executions
  REMOVE: result_json, ended_at
  ADD:    event_data, result_summary, error, duration_seconds, completed_at

Strategy: op.batch_alter_table is used throughout so that SQLite's
table-recreation path handles constraint removal correctly (drop slug from
systems which has UNIQUE(slug), etc.).  Batch mode is a no-op on PostgreSQL
for simple ADD/DROP operations.

All ops are idempotent (_has_column guards inside batch blocks using the
live inspector before entering the block).

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(conn, table: str) -> set:
    """Return the set of column names currently in *table*."""
    insp = inspect(conn)
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    # =========================================================================
    # systems
    #   old:  id, slug(UNIQUE), name, description, config_json, enabled, created_at
    #   new:  id, name, description, url, container, icon, type, created_at
    # =========================================================================
    existing = _cols(conn, "systems")

    with op.batch_alter_table("systems", recreate="auto") as batch:
        # Remove stale columns (batch recreates table on SQLite, dropping constraints)
        for col in ("slug", "config_json", "enabled"):
            if col in existing:
                batch.drop_column(col)
        # Add ORM columns
        if "url" not in existing:
            batch.add_column(sa.Column("url", sa.String(500), nullable=True))
        if "container" not in existing:
            batch.add_column(sa.Column("container", sa.String(120), nullable=True))
        if "icon" not in existing:
            batch.add_column(sa.Column(
                "icon", sa.String(10), nullable=True, server_default="📦"
            ))
        if "type" not in existing:
            batch.add_column(sa.Column(
                "type", sa.String(20), nullable=True, server_default="docker"
            ))

    # =========================================================================
    # scheduled_tasks
    #   old:  id, name, task_type, config_json, status, created_at, updated_at
    #   new:  id, name, description, type, payload, agent, scheduled_at,
    #         status, created_at, started_at, completed_at, result_summary,
    #         error, created_by
    # =========================================================================
    existing = _cols(conn, "scheduled_tasks")

    with op.batch_alter_table("scheduled_tasks", recreate="auto") as batch:
        for col in ("task_type", "config_json", "updated_at"):
            if col in existing:
                batch.drop_column(col)
        if "description" not in existing:
            batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        if "type" not in existing:
            batch.add_column(sa.Column(
                "type", sa.String(20), nullable=False, server_default="prompt"
            ))
        if "payload" not in existing:
            batch.add_column(sa.Column(
                "payload", sa.Text(), nullable=False, server_default=""
            ))
        if "agent" not in existing:
            batch.add_column(sa.Column("agent", sa.String(50), nullable=True))
        if "scheduled_at" not in existing:
            batch.add_column(sa.Column(
                "scheduled_at", sa.DateTime(timezone=True), nullable=False,
                server_default=sa.func.now()
            ))
        if "started_at" not in existing:
            batch.add_column(sa.Column(
                "started_at", sa.DateTime(timezone=True), nullable=True
            ))
        if "completed_at" not in existing:
            batch.add_column(sa.Column(
                "completed_at", sa.DateTime(timezone=True), nullable=True
            ))
        if "result_summary" not in existing:
            batch.add_column(sa.Column("result_summary", sa.Text(), nullable=True))
        if "error" not in existing:
            batch.add_column(sa.Column("error", sa.Text(), nullable=True))
        if "created_by" not in existing:
            batch.add_column(sa.Column(
                "created_by", sa.Integer(),
                sa.ForeignKey("users.id", name="fk_scheduled_tasks_created_by"),
                nullable=True
            ))

    # =========================================================================
    # triggers
    #   old:  id, name, trigger_type, config_json, enabled, source_plugin,
    #         created_at, updated_at
    #   new:  id, name, slug(UNIQUE), type, source, event_filter, action_type,
    #         action_payload, agent, secret, enabled, from_yaml,
    #         remote_trigger_id, source_plugin, created_by, created_at,
    #         updated_at
    # =========================================================================
    existing = _cols(conn, "triggers")

    with op.batch_alter_table("triggers", recreate="auto") as batch:
        for col in ("trigger_type", "config_json"):
            if col in existing:
                batch.drop_column(col)
        if "slug" not in existing:
            batch.add_column(sa.Column("slug", sa.String(200), nullable=True))
        if "type" not in existing:
            batch.add_column(sa.Column(
                "type", sa.String(20), nullable=False, server_default="webhook"
            ))
        if "source" not in existing:
            batch.add_column(sa.Column(
                "source", sa.String(50), nullable=False, server_default="custom"
            ))
        if "event_filter" not in existing:
            batch.add_column(sa.Column(
                "event_filter", sa.Text(), nullable=True, server_default="{}"
            ))
        if "action_type" not in existing:
            batch.add_column(sa.Column(
                "action_type", sa.String(20), nullable=False, server_default="prompt"
            ))
        if "action_payload" not in existing:
            batch.add_column(sa.Column(
                "action_payload", sa.Text(), nullable=False, server_default=""
            ))
        if "agent" not in existing:
            batch.add_column(sa.Column("agent", sa.String(50), nullable=True))
        if "secret" not in existing:
            # Tables are empty; app always calls Trigger.generate_secret() on
            # INSERT so this placeholder is never stored in a real row.
            batch.add_column(sa.Column(
                "secret", sa.String(128), nullable=False,
                server_default="placeholder-secret-regenerate-on-use"
            ))
        if "from_yaml" not in existing:
            batch.add_column(sa.Column(
                "from_yaml", sa.Boolean(), nullable=False, server_default=sa.false()
            ))
        if "remote_trigger_id" not in existing:
            batch.add_column(sa.Column(
                "remote_trigger_id", sa.String(100), nullable=True
            ))
        if "created_by" not in existing:
            batch.add_column(sa.Column(
                "created_by", sa.Integer(),
                sa.ForeignKey("users.id", name="fk_triggers_created_by"),
                nullable=True
            ))
        if "updated_at" not in existing:
            batch.add_column(sa.Column(
                "updated_at", sa.DateTime(timezone=True), nullable=True,
                server_default=sa.func.now()
            ))

    # Populate slug for any existing rows (tables are empty but be safe),
    # then add unique index.
    dialect_name = conn.dialect.name
    if dialect_name == "postgresql":
        conn.execute(text(
            "UPDATE triggers SET slug = 'trigger-' || id::text WHERE slug IS NULL"
        ))
    else:
        conn.execute(text(
            "UPDATE triggers SET slug = 'trigger-' || CAST(id AS TEXT) WHERE slug IS NULL"
        ))
    # Create unique index (idempotent — check first)
    insp = inspect(conn)
    ix_names = {ix["name"] for ix in insp.get_indexes("triggers")}
    if "ix_triggers_slug" not in ix_names:
        op.create_index("ix_triggers_slug", "triggers", ["slug"], unique=True)

    # =========================================================================
    # trigger_executions
    #   old:  id, trigger_id, status, result_json, started_at, ended_at
    #   new:  id, trigger_id, event_data, status, result_summary, error,
    #         duration_seconds, started_at, completed_at
    # =========================================================================
    existing = _cols(conn, "trigger_executions")

    with op.batch_alter_table("trigger_executions", recreate="auto") as batch:
        for col in ("result_json", "ended_at"):
            if col in existing:
                batch.drop_column(col)
        if "event_data" not in existing:
            batch.add_column(sa.Column(
                "event_data", sa.Text(), nullable=True, server_default="{}"
            ))
        if "result_summary" not in existing:
            batch.add_column(sa.Column("result_summary", sa.Text(), nullable=True))
        if "error" not in existing:
            batch.add_column(sa.Column("error", sa.Text(), nullable=True))
        if "duration_seconds" not in existing:
            batch.add_column(sa.Column("duration_seconds", sa.Float(), nullable=True))
        if "completed_at" not in existing:
            batch.add_column(sa.Column(
                "completed_at", sa.DateTime(timezone=True), nullable=True
            ))


def downgrade() -> None:
    conn = op.get_bind()

    # trigger_executions: restore old shape
    existing = _cols(conn, "trigger_executions")
    with op.batch_alter_table("trigger_executions", recreate="auto") as batch:
        for col in ("completed_at", "duration_seconds", "error",
                    "result_summary", "event_data"):
            if col in existing:
                batch.drop_column(col)
        if "result_json" not in existing:
            batch.add_column(sa.Column("result_json", sa.Text(), nullable=True))
        if "ended_at" not in existing:
            batch.add_column(sa.Column(
                "ended_at", sa.DateTime(timezone=True), nullable=True
            ))

    # triggers: drop unique index first
    insp = inspect(conn)
    ix_names = {ix["name"] for ix in insp.get_indexes("triggers")}
    if "ix_triggers_slug" in ix_names:
        op.drop_index("ix_triggers_slug", table_name="triggers")

    existing = _cols(conn, "triggers")
    with op.batch_alter_table("triggers", recreate="auto") as batch:
        for col in ("updated_at", "created_by", "remote_trigger_id", "from_yaml",
                    "secret", "agent", "action_payload", "action_type",
                    "event_filter", "source", "type", "slug"):
            if col in existing:
                batch.drop_column(col)
        if "trigger_type" not in existing:
            batch.add_column(sa.Column(
                "trigger_type", sa.String(50), nullable=False, server_default="webhook"
            ))
        if "config_json" not in existing:
            batch.add_column(sa.Column("config_json", sa.Text(), nullable=True))

    # scheduled_tasks: restore old shape
    existing = _cols(conn, "scheduled_tasks")
    with op.batch_alter_table("scheduled_tasks", recreate="auto") as batch:
        for col in ("created_by", "error", "result_summary", "completed_at",
                    "started_at", "scheduled_at", "agent", "payload",
                    "type", "description"):
            if col in existing:
                batch.drop_column(col)
        if "task_type" not in existing:
            batch.add_column(sa.Column(
                "task_type", sa.String(50), nullable=False, server_default="cron"
            ))
        if "config_json" not in existing:
            batch.add_column(sa.Column("config_json", sa.Text(), nullable=True))
        if "updated_at" not in existing:
            batch.add_column(sa.Column(
                "updated_at", sa.DateTime(timezone=True), nullable=True
            ))

    # systems: restore old shape
    existing = _cols(conn, "systems")
    with op.batch_alter_table("systems", recreate="auto") as batch:
        for col in ("type", "icon", "container", "url"):
            if col in existing:
                batch.drop_column(col)
        if "config_json" not in existing:
            batch.add_column(sa.Column("config_json", sa.Text(), nullable=True))
        if "enabled" not in existing:
            batch.add_column(sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ))
        if "slug" not in existing:
            batch.add_column(sa.Column("slug", sa.String(100), nullable=True))

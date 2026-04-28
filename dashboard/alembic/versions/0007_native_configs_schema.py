"""PG-native configs schema — runtime_configs, llm_providers, routine_definitions.

Creates / upgrades three tables (Postgres-only; skipped on SQLite):

  runtime_configs  — key/value store with optimistic locking version counter.
                     The ORM (models.py RuntimeConfig) may have already created
                     this table without `version` and `updated_by`.  This
                     migration adds those columns idempotently if absent.
                     Planned keys: workspace.name, workspace.company,
                     workspace.language, workspace.timezone, workspace.owner,
                     dashboard.chat.trustMode, active_provider.

  llm_providers    — registered LLM provider definitions (slug-keyed).
                     Active provider lives in runtime_configs['active_provider'].

  routine_definitions — named scheduled routines mirroring config/routines.yaml.
                        source_plugin NULL = core routine; non-NULL = plugin-owned.

Heartbeats: existing `heartbeats` table (alembic 0002) already has source_plugin
column and is the definition table.  No new heartbeats table is created here.
ADR PG-NC-3 confirms reuse of existing `heartbeats` table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_table(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _cols(conn, table: str) -> set:
    return {c["name"] for c in inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    # SQLite: nothing to do — all config stays in YAML files.
    if not _is_pg():
        return

    # -------------------------------------------------------------------------
    # runtime_configs — key/value singletons, namespaced with dots.
    # value is TEXT JSON for portability (PG-Q9 from postgres-compat ADR).
    # version enables optimistic locking (PG-NC-15).
    #
    # The ORM model (RuntimeConfig in models.py) may have already created this
    # table via db.create_all() with a different shape (no version, no
    # updated_by).  We add missing columns idempotently.
    # -------------------------------------------------------------------------
    if not _has_table(conn, "runtime_configs"):
        op.create_table(
            "runtime_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(200), nullable=False, unique=True),
            sa.Column("value", sa.Text(), nullable=False),  # TEXT JSON
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column(
                "updated_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_runtime_configs_key_prefix",
            "runtime_configs",
            ["key"],
        )
    else:
        # Table already exists (created by ORM or earlier migration).
        # Add columns that may be missing.
        existing = _cols(conn, "runtime_configs")
        with op.batch_alter_table("runtime_configs", recreate="never") as batch:
            if "version" not in existing:
                batch.add_column(
                    sa.Column(
                        "version",
                        sa.Integer(),
                        nullable=False,
                        server_default="1",
                    )
                )
            if "updated_by" not in existing:
                batch.add_column(
                    sa.Column(
                        "updated_by",
                        sa.Integer(),
                        nullable=True,
                    )
                )
        # Add FK constraint for updated_by only if column was just added and
        # users table exists.
        if "updated_by" not in existing and _has_table(conn, "users"):
            try:
                op.create_foreign_key(
                    "fk_runtime_configs_updated_by_users",
                    "runtime_configs", "users",
                    ["updated_by"], ["id"],
                    ondelete="SET NULL",
                )
            except Exception:
                pass  # FK may already exist or be unsupported; non-critical.

        # Ensure the key index exists.
        existing_indexes = {
            idx["name"]
            for idx in inspect(conn).get_indexes("runtime_configs")
        }
        if "ix_runtime_configs_key_prefix" not in existing_indexes:
            op.create_index(
                "ix_runtime_configs_key_prefix",
                "runtime_configs",
                ["key"],
            )

    # -------------------------------------------------------------------------
    # llm_providers — registered LLM providers.
    # env_vars: TEXT JSON object.
    # Active provider: runtime_configs['active_provider'] (not a column here).
    # -------------------------------------------------------------------------
    if not _has_table(conn, "llm_providers"):
        op.create_table(
            "llm_providers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("cli_command", sa.String(100), nullable=True),
            sa.Column(
                "env_vars",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),  # TEXT JSON
            sa.Column(
                "requires_logout",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # -------------------------------------------------------------------------
    # routine_definitions — scheduled routine definitions.
    # slug + source_plugin form a compound unique key (NULLs are distinct in PG
    # for UNIQUE indexes — Phase 6 import tool uses slug-only ON CONFLICT for
    # core routines where source_plugin IS NULL).
    # -------------------------------------------------------------------------
    if not _has_table(conn, "routine_definitions"):
        op.create_table(
            "routine_definitions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(100), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("schedule", sa.String(100), nullable=False),  # cron expression
            sa.Column("script", sa.String(200), nullable=False),
            sa.Column("agent", sa.String(50), nullable=True),
            sa.Column("frequency", sa.String(20), nullable=True),  # daily/weekly/monthly
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "goal_id",
                sa.Integer(),
                sa.ForeignKey("goals.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "source_plugin",
                sa.String(100),
                nullable=True,
            ),  # NULL = core routine; plugin slug otherwise
            sa.Column(
                "config_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),  # extra per-routine config
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        # Compound unique: same slug from the same plugin = duplicate.
        op.create_index(
            "uq_routine_def_slug_plugin",
            "routine_definitions",
            ["slug", "source_plugin"],
            unique=True,
        )


def downgrade() -> None:
    if not _is_pg():
        return

    conn = op.get_bind()

    if _has_table(conn, "routine_definitions"):
        op.drop_index("uq_routine_def_slug_plugin", table_name="routine_definitions")
        op.drop_table("routine_definitions")

    if _has_table(conn, "llm_providers"):
        op.drop_table("llm_providers")

    # For runtime_configs: only drop columns we added (version, updated_by).
    # Do NOT drop the table — ORM model may own it.
    if _has_table(conn, "runtime_configs"):
        existing = _cols(conn, "runtime_configs")
        with op.batch_alter_table("runtime_configs", recreate="never") as batch:
            if "version" in existing:
                batch.drop_column("version")
            if "updated_by" in existing:
                batch.drop_column("updated_by")

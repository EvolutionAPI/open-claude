"""ClickUp session resume — per-trigger toggle + dedup-keyed Claude session persistence.

Adds:
  - triggers.resume_sessions BOOLEAN — per-trigger opt-in for `claude --resume`
    behaviour.
  - new table `trigger_session_threads` — maps (trigger_id, dedup_key) →
    claude_session_id, allowing consecutive webhooks for the same logical
    "thread" (e.g. ClickUp task, GitHub PR) to continue the same Claude
    session window instead of starting fresh every time.

Why this matters:
  Without session resume, every webhook spawns a fresh `claude --print`
  subprocess that must re-read all prior comments, re-derive context, and
  re-fetch data via API calls. Long multi-comment workflows (reports →
  follow-up questions → implementations) lose 90% of the model's reasoning
  trace between turns. With resume, the model carries forward its full
  context window across turns at zero re-derivation cost.

  Real-world incident driving this (2026-05-02 ClickUp task 86c9kyquv):
  the user requested a marketing report, then asked to "implement
  recommendation 3". The fresh Oracle had to re-read the entire Google Doc
  and re-derive what "rec 3" meant — wasting ~$2 of work that the prior
  Oracle already had cached in context.

Schema:
  trigger_session_threads(
    id           PK,
    trigger_id   FK triggers(id) on delete cascade,
    dedup_key    TEXT NOT NULL    -- string extracted from event_data
                                   -- (ClickUp task_id, GitHub PR number, etc.)
    claude_session_id TEXT,        -- the session_id captured from claude --print --output-format json
    last_used_at DATETIME,
    created_at   DATETIME
  )
  UNIQUE (trigger_id, dedup_key)
  INDEX  (trigger_id, last_used_at DESC)  -- for cleanup queries

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_table(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _has_column(conn, table: str, column: str) -> bool:
    cols = {c["name"] for c in inspect(conn).get_columns(table)}
    return column in cols


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. triggers.resume_sessions ──────────────────────────────────────
    # Per-trigger toggle. Default FALSE so existing triggers keep their
    # current "fresh subprocess every time" behaviour. Operator opts in
    # explicitly via dashboard checkbox or YAML.
    if not _has_column(conn, "triggers", "resume_sessions"):
        with op.batch_alter_table("triggers") as batch:
            batch.add_column(
                sa.Column(
                    "resume_sessions",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    # ── 2. trigger_session_threads table ─────────────────────────────────
    if not _has_table(conn, "trigger_session_threads"):
        op.create_table(
            "trigger_session_threads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "trigger_id",
                sa.Integer(),
                sa.ForeignKey("triggers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("dedup_key", sa.Text(), nullable=False),
            sa.Column("claude_session_id", sa.Text(), nullable=True),
            sa.Column(
                "last_used_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "trigger_id",
                "dedup_key",
                name="uq_trigger_session_threads_trigger_key",
            ),
        )

        # Cleanup index — DESC last_used so "find stale sessions older
        # than N days" scans only the tail of the table.
        op.create_index(
            "ix_trigger_session_threads_trigger_last_used",
            "trigger_session_threads",
            ["trigger_id", "last_used_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _has_table(conn, "trigger_session_threads"):
        # Drop index first (PG complains otherwise on some versions).
        try:
            op.drop_index(
                "ix_trigger_session_threads_trigger_last_used",
                table_name="trigger_session_threads",
            )
        except Exception:
            pass
        op.drop_table("trigger_session_threads")

    if _has_column(conn, "triggers", "resume_sessions"):
        with op.batch_alter_table("triggers") as batch:
            batch.drop_column("resume_sessions")

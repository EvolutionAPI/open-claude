"""Goal-progress view — ANSI-portable (ADR PG-Q4).

Creates the goal_progress_v view using ANSI SQL constructs that work
identically on both SQLite and Postgres:
  COUNT, CASE WHEN, LEFT JOIN, CAST AS REAL

Previously created by executescript() in app.py on every startup.
This migration makes it part of the versioned schema.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ANSI-portable — no dialect-specific functions.
_VIEW_SQL = """\
CREATE VIEW goal_progress_v AS
SELECT
    g.id                                             AS goal_id,
    g.slug,
    g.target_value,
    COUNT(t.id)                                      AS total_tasks,
    COUNT(CASE WHEN t.status = 'done' THEN 1 END)   AS done_tasks,
    CASE
        WHEN COUNT(t.id) > 0
        THEN CAST(COUNT(CASE WHEN t.status = 'done' THEN 1 END) AS REAL)
             / COUNT(t.id) * 100.0
        ELSE 0
    END                                              AS pct_complete
FROM goals g
LEFT JOIN goal_tasks t ON t.goal_id = g.id
GROUP BY g.id\
"""


def upgrade() -> None:
    # DROP IF EXISTS then CREATE — idempotent on both dialects.
    op.execute(text("DROP VIEW IF EXISTS goal_progress_v"))
    op.execute(text(_VIEW_SQL))


def downgrade() -> None:
    op.execute(text("DROP VIEW IF EXISTS goal_progress_v"))

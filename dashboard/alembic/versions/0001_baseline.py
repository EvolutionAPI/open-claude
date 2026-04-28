"""baseline — empty migration fixing the Alembic starting point.

This migration does NOT create any tables.  The schema already exists on all
pre-Alembic installs (created by the inline executescript() blocks in app.py
that are retained for backward-compatibility).

Purpose:
  - Give every existing deployment a stamped alembic_version row so subsequent
    real migrations (0002, 0003, …) have a clean base to build on.
  - New clean installs (both SQLite and Postgres) also run this migration
    first; since it is a no-op they arrive at the same alembic_version state.

The actual schema creation for Postgres and the trigger/view ports are in
subsequent migrations (Step 2 of the postgres-compat plan).

Revision ID: 0001
Revises: —
Create Date: 2026-04-27
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — this is the baseline stamp.
    # The schema is owned by app.py (SQLite) and will be ported to Alembic
    # migrations 0002+ in postgres-compat Step 2.
    pass


def downgrade() -> None:
    # Cannot downgrade below baseline.
    pass

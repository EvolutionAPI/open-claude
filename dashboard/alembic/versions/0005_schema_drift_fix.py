"""Schema drift fix — categories C, D, F from drift audit (2026-04-26).

Category C — add missing columns to existing tables:
  - roles: permissions_json (NOT NULL DEFAULT '{}'), is_builtin (DEFAULT false)
  - runtime_configs: created_at (DateTime)

Category D — columns that the ORM expects but DB lacks (all confirmed used in code):
  - audit_log: username (auth_routes.py + models.audit()), resource (models.audit())
  - file_shares: view_count (shares.py:211), enabled (app.py:250, shares.py:178/193)
  - login_throttles: failed_attempts (auth_security.py), first_failed_at (auth_security.py)

  Note: login_throttles already has fail_count / last_attempt_at in DB.
  The ORM is aligned to use those names (see models.py renames).
  We only add the net-new columns (failed_attempts alias is resolved via ORM rename;
  first_failed_at is genuinely missing from DB).

Category F — source_plugin already present in projects/goals/goal_tasks/tickets
  per DB inspection — no migration needed for those four tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table: str, column: str) -> bool:
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # Category C — add missing columns
    # -------------------------------------------------------------------------

    # roles.permissions_json
    if not _has_column(conn, "roles", "permissions_json"):
        op.add_column(
            "roles",
            sa.Column("permissions_json", sa.Text(), nullable=False, server_default="{}"),
        )

    # roles.is_builtin
    if not _has_column(conn, "roles", "is_builtin"):
        op.add_column(
            "roles",
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # runtime_configs.created_at
    if not _has_column(conn, "runtime_configs", "created_at"):
        op.add_column(
            "runtime_configs",
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # -------------------------------------------------------------------------
    # Category D — add ORM-expected columns that are missing from the DB
    # -------------------------------------------------------------------------

    # audit_log.username  (used: auth_routes.py L191/200/369, models.audit())
    if not _has_column(conn, "audit_log", "username"):
        op.add_column(
            "audit_log",
            sa.Column("username", sa.String(80), nullable=True),
        )

    # audit_log.resource  (used: models.audit())
    if not _has_column(conn, "audit_log", "resource"):
        op.add_column(
            "audit_log",
            sa.Column("resource", sa.String(100), nullable=True),
        )

    # file_shares.view_count  (used: shares.py L211)
    if not _has_column(conn, "file_shares", "view_count"):
        op.add_column(
            "file_shares",
            sa.Column("view_count", sa.Integer(), nullable=True, server_default="0"),
        )

    # file_shares.enabled  (used: app.py L250, shares.py L178/193)
    if not _has_column(conn, "file_shares", "enabled"):
        op.add_column(
            "file_shares",
            sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.true()),
        )

    # login_throttles.first_failed_at  (used: auth_security.py L146/152)
    if not _has_column(conn, "login_throttles", "first_failed_at"):
        op.add_column(
            "login_throttles",
            sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()

    for table, column in [
        ("login_throttles", "first_failed_at"),
        ("file_shares", "enabled"),
        ("file_shares", "view_count"),
        ("audit_log", "resource"),
        ("audit_log", "username"),
        ("runtime_configs", "created_at"),
        ("roles", "is_builtin"),
        ("roles", "permissions_json"),
    ]:
        if _has_column(conn, table, column):
            op.drop_column(table, column)

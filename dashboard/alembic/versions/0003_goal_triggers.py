"""Goal-progress trigger — defense in depth (ADR PG-Q3).

Creates the goal-progress trigger on BOTH backends:
  - SQLite: trg_task_done_updates_goal (native TRIGGER DSL)
  - Postgres: fn_task_done_updates_goal() plpgsql function + AFTER UPDATE trigger

Business logic is identical on both:
  When a goal_tasks row transitions from any status to 'done'
  and goal_id IS NOT NULL:
    1. Increment goals.current_value by 1, set updated_at = now
    2. If current_value >= target_value and status is 'active': set status = 'achieved'

The trigger is the source of truth (ADR PG-Q3 defense-in-depth).
The ORM after_update listener (Phase 3) is observability only.

Idempotency:
  SQLite:    CREATE TRIGGER IF NOT EXISTS
  Postgres:  CREATE OR REPLACE FUNCTION + DROP TRIGGER IF EXISTS + CREATE TRIGGER

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        # SQLite trigger — original semantics, verbatim from app.py:277-283.
        # CREATE TRIGGER IF NOT EXISTS is idempotent (safe to re-run).
        op.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_task_done_updates_goal
            AFTER UPDATE OF status ON goal_tasks
            WHEN NEW.goal_id IS NOT NULL AND NEW.status = 'done' AND OLD.status != 'done'
            BEGIN
              UPDATE goals
                SET current_value = current_value + 1,
                    updated_at = datetime('now')
              WHERE id = NEW.goal_id;

              UPDATE goals
                SET status = 'achieved'
              WHERE id = NEW.goal_id
                AND current_value >= target_value
                AND status = 'active';
            END
        """))

    elif dialect == "postgresql":
        # Postgres: plpgsql trigger function + AFTER UPDATE ROW trigger.
        #
        # Semantics match SQLite exactly:
        #   - Only fires when NEW.status = 'done' AND OLD.status IS DISTINCT FROM 'done'
        #     (IS DISTINCT FROM is NULL-safe, equivalent to SQLite != for non-NULL statuses)
        #   - goal_id IS NOT NULL check guards orphaned tasks
        #
        # CREATE OR REPLACE FUNCTION is idempotent.
        # DROP TRIGGER IF EXISTS + CREATE is idempotent (PG lacks CREATE TRIGGER IF NOT EXISTS).
        op.execute(text("""
            CREATE OR REPLACE FUNCTION fn_task_done_updates_goal()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
              IF NEW.goal_id IS NOT NULL
                 AND NEW.status = 'done'
                 AND OLD.status IS DISTINCT FROM 'done'
              THEN
                UPDATE goals
                  SET current_value = current_value + 1,
                      updated_at    = now()
                WHERE id = NEW.goal_id;

                UPDATE goals
                  SET status = 'achieved'
                WHERE id = NEW.goal_id
                  AND current_value >= target_value
                  AND status = 'active';
              END IF;
              RETURN NEW;
            END;
            $$
        """))

        op.execute(text(
            "DROP TRIGGER IF EXISTS trg_task_done_updates_goal ON goal_tasks"
        ))

        op.execute(text("""
            CREATE TRIGGER trg_task_done_updates_goal
            AFTER UPDATE OF status ON goal_tasks
            FOR EACH ROW
            EXECUTE FUNCTION fn_task_done_updates_goal()
        """))


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        op.execute(text("DROP TRIGGER IF EXISTS trg_task_done_updates_goal"))

    elif dialect == "postgresql":
        op.execute(text(
            "DROP TRIGGER IF EXISTS trg_task_done_updates_goal ON goal_tasks"
        ))
        op.execute(text("DROP FUNCTION IF EXISTS fn_task_done_updates_goal()"))

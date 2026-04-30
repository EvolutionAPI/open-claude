from __future__ import annotations

from alembic import op

from models import db
from schema_migrations import downgrade_app_schema, upgrade_app_schema


revision = "0001_bootstrap_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    db.metadata.create_all(bind=bind)
    upgrade_app_schema(bind)


def downgrade() -> None:
    bind = op.get_bind()
    downgrade_app_schema(bind)
    db.metadata.drop_all(bind=bind)

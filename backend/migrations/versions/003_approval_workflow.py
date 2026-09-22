"""Add approval state to background tasks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "003_approval_workflow"
down_revision = "002_background_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("task_history")}
    additions = [
        ("approval_status", sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="not_required")),
        ("approval_decision_at", sa.Column("approval_decision_at", sa.DateTime(timezone=True), nullable=True)),
        ("approval_reason", sa.Column("approval_reason", sa.Text(), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("task_history", column)


def downgrade() -> None:
    for name in ("approval_reason", "approval_decision_at", "approval_status"):
        op.drop_column("task_history", name)

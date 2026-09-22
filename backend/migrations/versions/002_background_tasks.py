"""Add background task lifecycle fields.

Revision ID: 002_background_tasks
Revises: 001_initial_memory
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "002_background_tasks"
down_revision = "001_initial_memory"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("task_history")}
    additions = [
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True)),
        ("celery_task_id", sa.Column("celery_task_id", sa.String(length=255), nullable=True)),
        (
            "cancel_requested",
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        ),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("task_history", column)
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("task_history")}
    if "ix_task_history_celery_task_id" not in indexes:
        op.create_index("ix_task_history_celery_task_id", "task_history", ["celery_task_id"])


def downgrade():
    op.drop_index("ix_task_history_celery_task_id", table_name="task_history")
    op.drop_column("task_history", "cancel_requested")
    op.drop_column("task_history", "celery_task_id")
    op.drop_column("task_history", "error_message")
    op.drop_column("task_history", "completed_at")
    op.drop_column("task_history", "started_at")

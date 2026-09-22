"""Create persistent memory tables.

Revision ID: 001_initial_memory
"""
from alembic import op
from sqlalchemy.exc import DBAPIError

revision = "001_initial_memory"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except DBAPIError:
            pass
    from app.database.models import Base
    Base.metadata.create_all(bind=bind)


def downgrade():
    from app.database.models import Base
    Base.metadata.drop_all(bind=op.get_bind())

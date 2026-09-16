"""Create the SURAKSH registry and event foundation."""

from alembic import op
from sqlalchemy import inspect

from app.models.database import Base

revision = "0001_suraksh_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and Base.metadata.tables["cameras"].c.location.type.__class__.__name__ == "Geography":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # The model metadata is used only by this versioned baseline. Runtime startup
    # no longer creates or mutates schema; all future changes must be revisions.
    existing = set(inspect(bind).get_table_names())
    if not existing:
        Base.metadata.create_all(bind=bind)
        return
    # Existing VisionGuard installations receive the new tables and columns via
    # an explicit baseline revision; additive ALTER revisions follow this one.
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade():
    # Baseline downgrade is intentionally conservative for shared deployments.
    pass

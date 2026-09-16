"""Deduplicate authenticated observation retries."""
from alembic import op
import sqlalchemy as sa

revision = "0002_detection_request_id"
down_revision = "0001_suraksh_foundation"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if "request_id" not in {c["name"] for c in sa.inspect(bind).get_columns("detection_events")}:
        op.add_column("detection_events", sa.Column("request_id", sa.String(128), nullable=True))
        op.create_index("ix_detection_events_request_id", "detection_events", ["request_id"], unique=True)


def downgrade():
    with op.batch_alter_table("detection_events") as batch:
        batch.drop_index("ix_detection_events_request_id")
        batch.drop_column("request_id")

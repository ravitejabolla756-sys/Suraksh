"""Add safety event types and durable incident grouping state."""

from alembic import op
import sqlalchemy as sa


revision = "0004_safety_incident_integration"
down_revision = "0003_camera_analytics"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in ("vehicle_collision", "vehicle_crash", "pedestrian_vehicle_collision", "person_fall"):
            op.execute(sa.text(f"ALTER TYPE eventtype ADD VALUE IF NOT EXISTS '{value}'"))
    inspector = sa.inspect(bind)
    if "safety_incident_groups" not in inspector.get_table_names():
        op.create_table(
            "safety_incident_groups",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
            sa.Column("incident_event_id", sa.String(), sa.ForeignKey("events.id"), nullable=False),
            sa.Column("group_key", sa.String(255), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=False),
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("org_id", "camera_id", "group_key", name="uq_safety_group_scope"),
        )
        op.create_index("ix_safety_group_org_id", "safety_incident_groups", ["org_id"])
        op.create_index("ix_safety_group_camera_id", "safety_incident_groups", ["camera_id"])
        op.create_index("ix_safety_group_event_id", "safety_incident_groups", ["incident_event_id"])


def downgrade():
    op.drop_table("safety_incident_groups")

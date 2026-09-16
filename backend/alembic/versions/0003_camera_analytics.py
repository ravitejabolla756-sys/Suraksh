"""Add minute-bucketed anonymous tracking analytics."""
from alembic import op
import sqlalchemy as sa

revision = "0003_camera_analytics"
down_revision = "0002_detection_request_id"
branch_labels = depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "camera_analytics_snapshots" in inspector.get_table_names():
        return
    op.create_table(
        "camera_analytics_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("department_id", sa.String(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("source_vms", sa.String(100), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("people_visible_peak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vehicle_visible_peak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_people", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_cars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_motorcycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_buses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_trucks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cars_crossed_a_to_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cars_crossed_b_to_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("motorcycles_crossed_a_to_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("motorcycles_crossed_b_to_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buses_crossed_a_to_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buses_crossed_b_to_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trucks_crossed_a_to_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trucks_crossed_b_to_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("camera_id", "bucket_start", name="uq_analytics_camera_bucket"),
    )
    op.create_index("ix_analytics_camera_id", "camera_analytics_snapshots", ["camera_id"])
    op.create_index("ix_analytics_department_id", "camera_analytics_snapshots", ["department_id"])
    op.create_index("ix_analytics_source_vms", "camera_analytics_snapshots", ["source_vms"])
    op.create_index("ix_analytics_bucket_start", "camera_analytics_snapshots", ["bucket_start"])


def downgrade():
    op.drop_table("camera_analytics_snapshots")

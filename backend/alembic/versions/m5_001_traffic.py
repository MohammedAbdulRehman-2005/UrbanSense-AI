"""
UrbanSense AI — M5 Traffic Intelligence Migration
===================================================
Creates:
    - traffic_observations table
    - traffic_bottlenecks table
Adds to events table:
    - track_id (String, nullable=True)
    - telemetry_speed_kmh (Float, nullable=True)
Seeds:
    - SEG-TRF-001 (isolated traffic corridor segment)

Revision ID: m5_001_traffic
Revises: m4_002_evidence_lineage
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "m5_001_traffic"
down_revision = "m4_002_evidence_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add track_id and telemetry_speed_kmh to events table
    op.add_column("events", sa.Column("track_id", sa.String(), nullable=True))
    op.add_column("events", sa.Column("telemetry_speed_kmh", sa.Float(), nullable=True))
    op.create_index("ix_events_track_id", "events", ["track_id"])

    # 2. Create traffic_observations table
    op.create_table(
        "traffic_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("traffic_observation_id", sa.String(), nullable=False),
        sa.Column("road_segment_id", sa.String(), sa.ForeignKey("road_segments.segment_id"), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bus_id", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("camera_id", sa.String(), nullable=True),
        sa.Column("sensing_pass_id", sa.String(), nullable=True),
        sa.Column("vehicle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vehicle_class_counts", sa.JSON(), nullable=False),
        sa.Column("average_speed_kmh", sa.Float(), nullable=True),
        sa.Column("density", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("flow_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("congestion_state", sa.String(), nullable=False, server_default="NORMAL"),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("road_segment_id", "window_start", "window_end", name="uq_traffic_obs_segment_window"),
    )
    op.create_index("ix_traffic_observations_traffic_observation_id", "traffic_observations", ["traffic_observation_id"], unique=True)
    op.create_index("ix_traffic_observations_road_segment_id", "traffic_observations", ["road_segment_id"])
    op.create_index("ix_traffic_observations_window_start", "traffic_observations", ["window_start"])
    op.create_index("ix_traffic_observations_window_end", "traffic_observations", ["window_end"])
    op.create_index("ix_traffic_obs_segment_window", "traffic_observations", ["road_segment_id", "window_start"])

    # 3. Create traffic_bottlenecks table
    op.create_table(
        "traffic_bottlenecks",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("bottleneck_id", sa.String(), nullable=False),
        sa.Column("road_segment_id", sa.String(), sa.ForeignKey("road_segments.segment_id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("severity", sa.String(), nullable=False, server_default="HIGH"),
        sa.Column("density_condition", sa.String(), nullable=False, server_default="HIGH"),
        sa.Column("speed_condition", sa.String(), nullable=False, server_default="LOW"),
        sa.Column("qualifying_window_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("required_window_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("first_qualifying_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_qualifying_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_window_ids", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_traffic_bottlenecks_bottleneck_id", "traffic_bottlenecks", ["bottleneck_id"], unique=True)
    op.create_index("ix_traffic_bottlenecks_road_segment_id", "traffic_bottlenecks", ["road_segment_id"])
    op.create_index("ix_bottleneck_segment_status", "traffic_bottlenecks", ["road_segment_id", "status"])

    # 4. Seed SEG-TRF-001 into road_segments
    op.execute(
        sa.text(
            """
            INSERT INTO road_segments (segment_id, name, road_name, city, country, centroid_lat, centroid_lon, created_at)
            VALUES ('SEG-TRF-001', 'Gachibowli ORR Traffic Corridor', 'Outer Ring Road', 'Hyderabad', 'IN', 17.4300, 78.3600, NOW())
            ON CONFLICT (segment_id) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM road_segments WHERE segment_id = 'SEG-TRF-001';"))
    op.drop_table("traffic_bottlenecks")
    op.drop_table("traffic_observations")
    op.drop_index("ix_events_track_id", table_name="events")
    op.drop_column("events", "telemetry_speed_kmh")
    op.drop_column("events", "track_id")

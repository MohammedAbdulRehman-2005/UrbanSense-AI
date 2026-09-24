"""
UrbanSense AI — M3 Evidence table migration
============================================
Creates: evidence

Revision ID: m3_001_evidence
Revises: m1_001_initial
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "m3_001_evidence"
down_revision = "m1_001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        # Primary key
        sa.Column("evidence_id", sa.String(), primary_key=True),

        # Source provenance
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("observation_id", sa.String(), nullable=True),
        sa.Column("opportunity_id", sa.String(), nullable=True),

        # Identity
        sa.Column("polarity", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default="BUS_CAMERA"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("bus_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("camera_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_timestamp", sa.DateTime(timezone=True), nullable=False),

        # Spatial
        sa.Column("matched_road_segment_id", sa.String(), nullable=True),
        sa.Column("map_match_status", sa.String(), nullable=True),

        # Quality signals
        sa.Column("detector_confidence", sa.Float(), nullable=True),
        sa.Column("observation_quality", sa.Float(), nullable=True),
        sa.Column("opportunity_score", sa.Float(), nullable=True),
        sa.Column("gps_quality", sa.Float(), nullable=True),
        sa.Column("sensor_health", sa.Float(), nullable=True),

        # Independence classification
        sa.Column("independence_class", sa.String(), nullable=False),
        sa.Column("correlation_group_id", sa.String(), nullable=True),

        # Computed evidence weight (set ONLY by FusionEngine)
        sa.Column("evidence_weight", sa.Float(), nullable=False),

        # Fusion metadata
        sa.Column("fusion_strategy", sa.String(), nullable=False, server_default="MVP"),
        sa.Column("fusion_version", sa.String(), nullable=False, server_default="1.0"),

        # Negative evidence
        sa.Column("negative_evidence_strength", sa.Float(), nullable=True),

        # Research / future
        sa.Column("source_reliability", sa.Float(), nullable=True),
        sa.Column("temporal_consistency", sa.Float(), nullable=True),
        sa.Column("spatial_consistency", sa.Float(), nullable=True),
        sa.Column("historical_consistency", sa.Float(), nullable=True),
        sa.Column("independence_score", sa.Float(), nullable=True),
        sa.Column("correlation_penalty", sa.Float(), nullable=True),

        # Lineage
        sa.Column("lineage", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evidence_event_id", "evidence", ["event_id"])
    op.create_index("ix_evidence_bus_id", "evidence", ["bus_id"])
    op.create_index("ix_evidence_road_segment", "evidence", ["matched_road_segment_id"])
    op.create_index("ix_evidence_timestamp", "evidence", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_evidence_timestamp", table_name="evidence")
    op.drop_index("ix_evidence_road_segment", table_name="evidence")
    op.drop_index("ix_evidence_bus_id", table_name="evidence")
    op.drop_index("ix_evidence_event_id", table_name="evidence")
    op.drop_table("evidence")

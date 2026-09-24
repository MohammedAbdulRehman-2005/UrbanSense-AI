"""
UrbanSense AI — Initial Milestone 1 schema migration
====================================================
Creates: road_segments, observations, observation_opportunities, events, roadtwin_states
PostGIS must be enabled before running this migration.

Revision ID: m1_001_initial
Revises:
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "m1_001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable PostGIS (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ── road_segments ───────────────────────────────────────────────────────
    op.create_table(
        "road_segments",
        sa.Column("segment_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("road_name", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=False, server_default="IN"),
        sa.Column("geom", Geometry(geometry_type="LINESTRING", srid=4326), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("centroid_lon", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ── observations ────────────────────────────────────────────────────────
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(), primary_key=True),
        sa.Column("frame_id", sa.String(), nullable=False),
        sa.Column("bus_id", sa.String(), nullable=False, index=True),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("detector_confidence", sa.Float(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("mask_reference", sa.String(), nullable=True),
        sa.Column("track_id", sa.String(), nullable=True),
        sa.Column("trajectory_reference", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("evidence_hint", sa.String(), nullable=True),
        sa.Column("road_segment_id", sa.String(), sa.ForeignKey("road_segments.segment_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_observations_timestamp", "observations", ["timestamp"])
    op.create_index("ix_observations_road_segment_id", "observations", ["road_segment_id"])

    # ── observation_opportunities ────────────────────────────────────────────
    op.create_table(
        "observation_opportunities",
        sa.Column("opportunity_id", sa.String(), primary_key=True),
        sa.Column("sensing_pass_id", sa.String(), nullable=False),
        sa.Column("bus_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_scope", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("edge_road_segment_hint", sa.String(), nullable=True),
        sa.Column("fov_valid", sa.Boolean(), nullable=False),
        sa.Column("visibility_score", sa.Float(), nullable=False),
        sa.Column("illumination_score", sa.Float(), nullable=False),
        sa.Column("blur_score", sa.Float(), nullable=False),
        sa.Column("occlusion_score", sa.Float(), nullable=False),
        sa.Column("viewing_angle_score", sa.Float(), nullable=False),
        sa.Column("distance_score", sa.Float(), nullable=False),
        sa.Column("sensor_health_score", sa.Float(), nullable=False),
        sa.Column("gps_quality_score", sa.Float(), nullable=False),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column("validity_status", sa.String(), nullable=False),
        sa.Column("invalid_reasons", sa.JSON(), nullable=True),
        sa.Column("coverage_fraction", sa.Float(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_opportunities_sensing_pass_id", "observation_opportunities", ["sensing_pass_id"])
    op.create_index("ix_opportunities_bus_id", "observation_opportunities", ["bus_id"])

    # ── events ──────────────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(), unique=True, nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="1.0"),
        sa.Column("bus_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        # DISTINCT time fields — never merge
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("edge_road_segment_hint", sa.String(), nullable=True),
        # BACKEND-OWNED map-match fields
        sa.Column("matched_road_segment_id", sa.String(), sa.ForeignKey("road_segments.segment_id"), nullable=True),
        sa.Column("map_match_confidence", sa.Float(), nullable=True),
        sa.Column("map_match_status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("event_type", sa.String(), nullable=False),
        # Cross-references are ORDER-INDEPENDENT logical references, NOT hard database
        # constraints (mirrors backend/app/models/event.py). R4 §33.1 defines no
        # observation-ingestion API, so events may reference observation_ids that have
        # no persisted row; opportunities travel on a separate endpoint and may arrive
        # after their events (R4 §14.3 order-independent transport). Enforcing FKs here
        # would reject the canonical edge → backend flow.
        sa.Column("observation_id", sa.String(), nullable=True),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column("evidence_ref", sa.String(), nullable=True),
        sa.Column("detector_confidence", sa.Float(), nullable=False),
        sa.Column("observation_quality", sa.Float(), nullable=True),
        sa.Column("gps_quality", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False, server_default="P2"),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("producer_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_events_event_id"),
    )
    op.create_index("ix_events_event_id", "events", ["event_id"])
    op.create_index("ix_events_bus_id", "events", ["bus_id"])
    op.create_index("ix_events_event_timestamp", "events", ["event_timestamp"])
    op.create_index("ix_events_matched_road_segment_id", "events", ["matched_road_segment_id"])

    # ── roadtwin_states ──────────────────────────────────────────────────────
    op.create_table(
        "roadtwin_states",
        sa.Column("roadtwin_id", sa.String(), primary_key=True),
        sa.Column("road_segment_id", sa.String(), sa.ForeignKey("road_segments.segment_id"), nullable=False, unique=True),
        sa.Column("subject_id", sa.String(), nullable=True),
        sa.Column("subject_type", sa.String(), nullable=True),
        sa.Column("current_state", sa.String(), nullable=False, server_default="OBSERVED"),
        sa.Column("aggregate_confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("positive_evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("independent_bus_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_status", sa.String(), nullable=False, server_default="FRESH"),
        sa.Column("maintenance_status", sa.String(), nullable=False, server_default="NONE"),
        sa.Column("verification_status", sa.String(), nullable=False, server_default="UNVERIFIED"),
        sa.Column("active_episode_id", sa.String(), nullable=True),
        sa.Column("previous_episode_id", sa.String(), nullable=True),
        sa.Column("history_ref", sa.String(), nullable=True),
        sa.Column("last_event_id", sa.String(), nullable=True),
        sa.Column("last_observation_id", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("road_segment_id", name="uq_roadtwin_segment"),
    )
    op.create_index("ix_roadtwin_road_segment_id", "roadtwin_states", ["road_segment_id"])

    # ── Seed demo road segment (SEG-001) ─────────────────────────────────────
    # Required for PROTOTYPE map-match to resolve events to a segment.
    # DECISION_REQUIRED: replace with real road network import in production.
    op.execute("""
        INSERT INTO road_segments (segment_id, name, road_name, city, country, centroid_lat, centroid_lon, created_at, notes)
        VALUES (
            'SEG-001',
            'HITEC City Main Road Seg 1',
            'HITEC City Road',
            'Hyderabad',
            'IN',
            17.4435,
            78.3772,
            NOW(),
            'PROTOTYPE / SIMULATED seed segment for Milestone 1 demo. DECISION_REQUIRED: replace with real network.'
        )
        ON CONFLICT (segment_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO road_segments (segment_id, name, road_name, city, country, centroid_lat, centroid_lon, created_at, notes)
        VALUES (
            'SEG-002',
            'HITEC City Main Road Seg 2',
            'HITEC City Road',
            'Hyderabad',
            'IN',
            17.4440,
            78.3780,
            NOW(),
            'PROTOTYPE / SIMULATED seed segment for Milestone 1 demo.'
        )
        ON CONFLICT (segment_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("roadtwin_states")
    op.drop_table("events")
    op.drop_table("observation_opportunities")
    op.drop_table("observations")
    op.drop_table("road_segments")

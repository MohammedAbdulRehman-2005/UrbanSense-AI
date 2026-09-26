"""
UrbanSense AI — Traffic ORM Models (Milestone 5)
=================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Phase 19)

Provides relational persistence for:
1. TrafficObservationModel (traffic_observations table):
   Segment-level, time-windowed traffic aggregation preserving vehicle counts,
   class breakdown, fleet speed, density, and flow rate.
2. TrafficBottleneckModel (traffic_bottlenecks table):
   Persistent record of bottleneck states identified by the rolling 3-window condition
   (high density AND low fleet speed across 3 consecutive windows).
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Integer,
    JSON,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class TrafficObservationModel(Base):
    __tablename__ = "traffic_observations"
    __table_args__ = (
        UniqueConstraint(
            "road_segment_id",
            "window_start",
            "window_end",
            name="uq_traffic_obs_segment_window",
        ),
        Index("ix_traffic_obs_segment_window", "road_segment_id", "window_start"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    traffic_observation_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    road_segment_id = Column(
        String,
        ForeignKey("road_segments.segment_id"),
        nullable=False,
        index=True,
    )

    # Time window (event-time semantics)
    window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    window_end = Column(DateTime(timezone=True), nullable=False, index=True)

    # Source context
    bus_id = Column(String, nullable=True)
    device_id = Column(String, nullable=True)
    camera_id = Column(String, nullable=True)
    sensing_pass_id = Column(String, nullable=True)

    # Deduplicated tracked vehicle count in this window
    vehicle_count = Column(Integer, nullable=False, default=0)

    # Breakdown by class: {"car": N, "bus": N, "truck": N, "motorcycle": N, "bicycle": N}
    vehicle_class_counts = Column(JSON, nullable=False, default=dict)

    # Fleet speed: GPS/telemetry-derived average speed in km/h (NULL when unknown)
    average_speed_kmh = Column(Float, nullable=True)

    # Transport metrics
    density = Column(Float, nullable=False, default=0.0)      # veh/km (PROPOSED prototype)
    flow_rate = Column(Float, nullable=False, default=0.0)    # veh/h
    congestion_state = Column(String, nullable=False, default="NORMAL")  # NORMAL | ELEVATED | HIGH

    trace_id = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    segment = relationship("RoadSegment", foreign_keys=[road_segment_id])


class TrafficBottleneckModel(Base):
    __tablename__ = "traffic_bottlenecks"
    __table_args__ = (
        Index("ix_bottleneck_segment_status", "road_segment_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bottleneck_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    road_segment_id = Column(
        String,
        ForeignKey("road_segments.segment_id"),
        nullable=False,
        index=True,
    )

    status = Column(String, nullable=False, default="ACTIVE")  # ACTIVE | RESOLVED
    severity = Column(String, nullable=False, default="HIGH")   # HIGH | CRITICAL

    density_condition = Column(String, nullable=False, default="HIGH")
    speed_condition = Column(String, nullable=False, default="LOW")

    qualifying_window_count = Column(Integer, nullable=False, default=3)
    required_window_count = Column(Integer, nullable=False, default=3)

    first_qualifying_window_start = Column(DateTime(timezone=True), nullable=False)
    latest_qualifying_window_end = Column(DateTime(timezone=True), nullable=False)

    evidence_window_ids = Column(JSON, nullable=False, default=list)

    start_time = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    segment = relationship("RoadSegment", foreign_keys=[road_segment_id])

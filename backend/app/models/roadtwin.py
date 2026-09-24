"""
UrbanSense AI — RoadTwin State ORM Model (Milestone 1)
=======================================================
Milestone 1 scope: OBSERVED state only.
Full 8-state lifecycle is a later milestone.

RoadTwin is BACKEND-OWNED. Never modified by frontend or Edge.
One RoadTwin per road_segment_id — segment-level, not per-pothole.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class RoadTwinStateModel(Base):
    __tablename__ = "roadtwin_states"
    __table_args__ = (
        UniqueConstraint("road_segment_id", name="uq_roadtwin_segment"),
    )

    roadtwin_id = Column(String, primary_key=True)
    road_segment_id = Column(String, ForeignKey("road_segments.segment_id"), nullable=False, unique=True, index=True)

    subject_id = Column(String, nullable=True)
    subject_type = Column(String, nullable=True)

    # Current state — OBSERVED in M1
    current_state = Column(String, nullable=False, default="OBSERVED")

    # Confidence — BACKEND-OWNED aggregate, DISTINCT from detector_confidence
    aggregate_confidence = Column(Float, nullable=False, default=0.0)

    # Evidence counts
    positive_evidence_count = Column(Integer, nullable=False, default=0)
    negative_evidence_count = Column(Integer, nullable=False, default=0)
    independent_bus_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)

    # Status fields
    freshness_status = Column(String, nullable=False, default="FRESH")
    maintenance_status = Column(String, nullable=False, default="NONE")
    verification_status = Column(String, nullable=False, default="UNVERIFIED")

    # Episode tracking (future milestone)
    active_episode_id = Column(String, nullable=True)
    previous_episode_id = Column(String, nullable=True)
    history_ref = Column(String, nullable=True)

    # Traceability
    last_event_id = Column(String, nullable=True)
    last_observation_id = Column(String, nullable=True)

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    segment = relationship("RoadSegment", back_populates="roadtwin_state")

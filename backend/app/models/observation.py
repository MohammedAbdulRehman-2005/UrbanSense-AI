"""
UrbanSense AI — Observation ORM Model (Milestone 1)
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class ObservationModel(Base):
    __tablename__ = "observations"

    observation_id = Column(String, primary_key=True)
    frame_id = Column(String, nullable=False)
    bus_id = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=False)
    camera_id = Column(String, nullable=False)

    # event_timestamp semantics — when the frame was captured
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    object_type = Column(String, nullable=False)

    # Raw model output confidence — NOT evidence/RoadTwin confidence
    detector_confidence = Column(Float, nullable=False)

    bbox = Column(JSON, nullable=False)
    mask_reference = Column(String, nullable=True)
    track_id = Column(String, nullable=True)
    trajectory_reference = Column(String, nullable=True)
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    evidence_hint = Column(String, nullable=True)

    # Backend map-match association (nullable until matched)
    road_segment_id = Column(String, ForeignKey("road_segments.segment_id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    segment = relationship("RoadSegment", back_populates="observations")
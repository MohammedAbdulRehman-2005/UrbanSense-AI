"""
UrbanSense AI — ObservationOpportunity ORM Model (Milestone 1)
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class OpportunityModel(Base):
    __tablename__ = "observation_opportunities"

    opportunity_id = Column(String, primary_key=True)
    sensing_pass_id = Column(String, nullable=False, index=True)
    bus_id = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=False)
    camera_id = Column(String, nullable=False)

    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)

    target_scope = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    edge_road_segment_hint = Column(String, nullable=True)  # ADVISORY only

    fov_valid = Column(Boolean, nullable=False)
    visibility_score = Column(Float, nullable=False)
    illumination_score = Column(Float, nullable=False)
    blur_score = Column(Float, nullable=False)
    occlusion_score = Column(Float, nullable=False)
    viewing_angle_score = Column(Float, nullable=False)
    distance_score = Column(Float, nullable=False)
    sensor_health_score = Column(Float, nullable=False)
    gps_quality_score = Column(Float, nullable=False)
    opportunity_score = Column(Float, nullable=False)
    validity_status = Column(String, nullable=False)
    invalid_reasons = Column(JSON, default=list)
    coverage_fraction = Column(Float, nullable=False)
    trace_id = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    events = relationship("EventModel", back_populates="opportunity")
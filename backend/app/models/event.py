"""
UrbanSense AI — Event ORM Model (Milestone 1)
==============================================
Preserves event_timestamp (historical) and ingestion_timestamp (operational)
as DISTINCT fields. Never merge.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from backend.app.db.base import Base


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_events_event_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)  # internal PK
    event_id = Column(String, unique=True, nullable=False, index=True)  # business key
    schema_version = Column(String, nullable=False, default="1.0")

    bus_id = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=False)
    camera_id = Column(String, nullable=False)

    # DISTINCT time fields — never merge
    event_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ingestion_timestamp = Column(DateTime(timezone=True), nullable=False)

    # Location
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude_m = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    heading_deg = Column(Float, nullable=True)
    # PostGIS point for spatial queries
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    # Advisory from Edge — NOT authoritative
    edge_road_segment_hint = Column(String, nullable=True)

    # BACKEND-OWNED map-match results
    matched_road_segment_id = Column(String, ForeignKey("road_segments.segment_id"), nullable=True, index=True)
    map_match_confidence = Column(Float, nullable=True)
    map_match_status = Column(String, nullable=False, default="PENDING")

    event_type = Column(String, nullable=False)

    # Cross-references
    observation_id = Column(String, ForeignKey("observations.observation_id"), nullable=True)
    opportunity_id = Column(String, ForeignKey("observation_opportunities.opportunity_id"), nullable=True)
    evidence_ref = Column(String, nullable=True)

    # Quality dimensions — DISTINCT, never merge
    detector_confidence = Column(Float, nullable=False)
    observation_quality = Column(Float, nullable=True)
    gps_quality = Column(Float, nullable=True)

    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    priority = Column(String, nullable=False, default="P2")
    trace_id = Column(String, nullable=False)
    producer_sequence = Column(Integer, nullable=False, default=0)
    payload_hash = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    segment = relationship("RoadSegment", back_populates="events", foreign_keys=[matched_road_segment_id])
    observation = relationship("ObservationModel", back_populates="event", foreign_keys=[observation_id])
    opportunity = relationship("OpportunityModel", back_populates="events", foreign_keys=[opportunity_id])

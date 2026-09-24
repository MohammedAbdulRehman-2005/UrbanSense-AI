"""
UrbanSense AI — RoadSegment ORM Model (Milestone 1)
=====================================================
Minimal road segment for first vertical slice.
Full road network ingestion is a later milestone.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Text
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from backend.app.db.base import Base


class RoadSegment(Base):
    __tablename__ = "road_segments"

    segment_id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    road_name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    country = Column(String, default="IN")

    # PostGIS geometry — LINESTRING for the segment path
    geom = Column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=True)

    # Approximate centroid for map-match proximity queries
    centroid_lat = Column(Float, nullable=True)
    centroid_lon = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)

    # Relationships
    roadtwin_state = relationship("RoadTwinStateModel", back_populates="segment", uselist=False)
    events = relationship("EventModel", back_populates="segment")
    observations = relationship("ObservationModel", back_populates="segment")
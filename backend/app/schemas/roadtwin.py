"""
UrbanSense AI — FastAPI schemas for RoadTwin read API (Milestone 1)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RoadTwinResponse(BaseModel):
    """Read model for GET /api/v1/roadtwin. Backend-owned."""
    model_config = ConfigDict(from_attributes=True)

    roadtwin_id: str
    road_segment_id: str
    subject_id: Optional[str] = None
    subject_type: Optional[str] = None
    current_state: str
    aggregate_confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    independent_bus_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    last_validated_at: Optional[datetime] = None
    freshness_status: str
    maintenance_status: str
    verification_status: str
    active_episode_id: Optional[str] = None
    previous_episode_id: Optional[str] = None
    last_event_id: Optional[str] = None
    last_observation_id: Optional[str] = None
    segment_centroid_lat: Optional[float] = None
    segment_centroid_lon: Optional[float] = None
    segment_name: Optional[str] = None

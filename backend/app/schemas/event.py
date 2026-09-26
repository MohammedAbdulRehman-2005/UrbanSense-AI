"""
UrbanSense AI — FastAPI schemas for Event API (Milestone 1)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LocationSchema(BaseModel):
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None
    accuracy_m: Optional[float] = None
    heading_deg: Optional[float] = None


class EventIngest(BaseModel):
    """Request body for POST /api/v1/events — mirrors CanonicalEvent."""
    model_config = ConfigDict(extra="ignore")

    event_id: str
    schema_version: str = "1.0"
    bus_id: str
    device_id: str
    camera_id: str
    event_timestamp: datetime
    location: LocationSchema
    edge_road_segment_hint: Optional[str] = None
    event_type: str
    observation_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    evidence_ref: Optional[str] = None
    track_id: Optional[str] = None
    telemetry_speed_kmh: Optional[float] = None
    detector_confidence: float = Field(ge=0.0, le=1.0)
    observation_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    gps_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    model_name: str
    model_version: str
    priority: str = "P2"
    trace_id: str
    producer_sequence: int = 0
    payload_hash: Optional[str] = None


class EventIngestResponse(BaseModel):
    """Response for POST /api/v1/events."""
    model_config = ConfigDict(from_attributes=True)

    status: str          # "accepted" | "duplicate"
    event_id: str
    message: str
    roadtwin_id: Optional[str] = None
    matched_road_segment_id: Optional[str] = None
    map_match_status: str = "PENDING"
    ingestion_timestamp: datetime

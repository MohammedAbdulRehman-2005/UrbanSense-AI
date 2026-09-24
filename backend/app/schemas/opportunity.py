"""
UrbanSense AI — FastAPI schemas for Opportunity API (Milestone 1)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class OpportunityIngest(BaseModel):
    """Request body for POST /api/v1/opportunities."""
    model_config = ConfigDict(extra="ignore")

    opportunity_id: str
    sensing_pass_id: str
    bus_id: str
    device_id: str
    camera_id: str
    window_start: datetime
    window_end: datetime
    target_scope: str
    target_type: str
    target_id: Optional[str] = None
    edge_road_segment_hint: Optional[str] = None
    fov_valid: bool
    visibility_score: float = Field(ge=0.0, le=1.0)
    illumination_score: float = Field(ge=0.0, le=1.0)
    blur_score: float = Field(ge=0.0, le=1.0)
    occlusion_score: float = Field(ge=0.0, le=1.0)
    viewing_angle_score: float = Field(ge=0.0, le=1.0)
    distance_score: float = Field(ge=0.0, le=1.0)
    sensor_health_score: float = Field(ge=0.0, le=1.0)
    gps_quality_score: float = Field(ge=0.0, le=1.0)
    opportunity_score: float = Field(ge=0.0, le=1.0)
    validity_status: str
    invalid_reasons: List[str] = []
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    trace_id: str


class OpportunityIngestResponse(BaseModel):
    """Response for POST /api/v1/opportunities."""
    model_config = ConfigDict(from_attributes=True)

    status: str          # "accepted" | "duplicate"
    opportunity_id: str
    message: str
    ingestion_timestamp: datetime

"""
UrbanSense AI — Traffic API Schemas (Milestone 5)
==================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Section 33.4)

Pydantic read-model schemas for:
- GET /api/v1/traffic
- GET /api/v1/bottlenecks
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrafficObservationResponse(BaseModel):
    """Read model for windowed traffic observation on a road segment."""
    model_config = ConfigDict(from_attributes=True)

    traffic_observation_id: str
    road_segment_id: str
    window_start: datetime
    window_end: datetime

    bus_id: Optional[str] = None
    device_id: Optional[str] = None
    camera_id: Optional[str] = None
    sensing_pass_id: Optional[str] = None

    vehicle_count: int
    vehicle_class_counts: Dict[str, int] = Field(default_factory=dict)
    average_speed_kmh: Optional[float] = None

    density: float
    flow_rate: float
    congestion_state: str

    trace_id: str
    created_at: Optional[datetime] = None

    # Spatial context
    segment_name: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None


class BottleneckResponse(BaseModel):
    """
    Read model for persistent bottleneck identification.
    Exposes explainability fields:
    - density_condition (HIGH)
    - speed_condition (LOW)
    - qualifying_window_count
    - required_window_count (3)
    - window timestamps and evidence IDs
    """
    model_config = ConfigDict(from_attributes=True)

    bottleneck_id: str
    road_segment_id: str
    status: str
    severity: str

    density_condition: str
    speed_condition: str
    qualifying_window_count: int
    required_window_count: int

    first_qualifying_window_start: datetime
    latest_qualifying_window_end: datetime
    evidence_window_ids: List[str] = Field(default_factory=list)

    start_time: datetime
    resolved_at: Optional[datetime] = None

    # Spatial context
    segment_name: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None

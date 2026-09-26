"""
UrbanSense AI — Traffic Intelligence Data Contracts (Milestone 5)
==================================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Phase 19)

Defines data shapes for:
- Vehicle counts by class
- Time-windowed traffic observations
- Rolling-window bottleneck states

Counting rule:
A tracked object contributes AT MOST ONCE per aggregation window on a given road segment.
Raw frame detections must never multiply vehicle counts.

Speed rule:
Speed is GPS/telemetry-derived. Pixel motion is never converted to physical speed without calibration.
Missing speed remains None (UNKNOWN).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
import uuid


class CongestionState(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


class DensityCondition(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


class SpeedCondition(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class BottleneckStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RESOLVED = "RESOLVED"


class VehicleClass(str, Enum):
    CAR = "car"
    BUS = "bus"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"


class VehicleClassCounts(BaseModel):
    """Counts per vehicle category in an aggregation window."""
    car: int = 0
    bus: int = 0
    truck: int = 0
    motorcycle: int = 0
    bicycle: int = 0


class TrafficObservation(BaseModel):
    """
    Windowed aggregation of vehicle traffic on a specific road segment.
    Lineage is preserved from tracked vehicle observations and GPS telemetry.
    """
    model_config = ConfigDict(extra="ignore")

    traffic_observation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this windowed traffic observation.",
    )
    road_segment_id: str = Field(description="Associated road segment ID.")
    window_start: datetime = Field(description="Start time of the aggregation window (event-time).")
    window_end: datetime = Field(description="End time of the aggregation window (event-time).")

    bus_id: Optional[str] = Field(default=None, description="Observing bus ID if single-pass.")
    device_id: Optional[str] = Field(default=None, description="Observing device ID.")
    camera_id: Optional[str] = Field(default=None, description="Observing camera ID.")
    sensing_pass_id: Optional[str] = Field(default=None, description="Associated sensing pass ID if available.")

    vehicle_count: int = Field(ge=0, description="Deduplicated unique vehicle count in the window.")
    vehicle_class_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of vehicle counts by class (car, bus, truck, motorcycle, bicycle).",
    )

    average_speed_kmh: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="GPS/telemetry-derived fleet speed in km/h. None if speed is UNKNOWN.",
    )

    density: float = Field(
        ge=0.0,
        description="Vehicles per kilometre (veh/km) over segment length (PROPOSED prototype representation).",
    )
    flow_rate: float = Field(
        ge=0.0,
        description="Derived flow rate in vehicles per hour (veh/h).",
    )

    congestion_state: CongestionState = Field(
        default=CongestionState.NORMAL,
        description="Categorical congestion level based on density and speed thresholds.",
    )

    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Distributed tracing identifier.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(datetime.timezone.utc if hasattr(datetime, "timezone") else None),
        description="Record generation timestamp.",
    )


class BottleneckState(BaseModel):
    """
    Bottleneck condition on a road segment identified across rolling 3-windows.
    Requires: HIGH density AND LOW speed across 3 consecutive rolling windows.
    """
    model_config = ConfigDict(extra="ignore")

    bottleneck_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the bottleneck record.",
    )
    road_segment_id: str = Field(description="Associated road segment ID.")
    status: BottleneckStatus = Field(
        default=BottleneckStatus.ACTIVE,
        description="Active, inactive, or resolved status.",
    )
    severity: str = Field(
        default="HIGH",
        description="Severity classification (HIGH or CRITICAL).",
    )

    density_condition: DensityCondition = Field(
        description="Density condition state of the bottleneck (e.g. HIGH).",
    )
    speed_condition: SpeedCondition = Field(
        description="Speed condition state of the bottleneck (e.g. LOW).",
    )

    qualifying_window_count: int = Field(
        ge=0,
        description="Number of consecutive qualifying windows observed.",
    )
    required_window_count: int = Field(
        default=3,
        description="Required consecutive qualifying windows to trigger bottleneck (3 per Master Plan).",
    )

    first_qualifying_window_start: datetime = Field(
        description="Start time of the first qualifying window in the streak.",
    )
    latest_qualifying_window_end: datetime = Field(
        description="End time of the latest qualifying window in the streak.",
    )
    evidence_window_ids: List[str] = Field(
        default_factory=list,
        description="IDs of TrafficObservation windows constituting the bottleneck evidence.",
    )

    start_time: datetime = Field(description="Time when the 3-window condition was confirmed.")
    resolved_at: Optional[datetime] = Field(default=None, description="Time when condition cleared.")

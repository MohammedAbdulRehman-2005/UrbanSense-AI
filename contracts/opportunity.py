"""
UrbanSense AI — Observation Opportunity Contract
=================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

An ObservationOpportunity is a sibling semantic object to Observation.
It answers: "Was there a valid chance to observe the target?"

SEMANTIC NOTES:
- Opportunity is NOT the parent container of all frames.
- Opportunity is a SIBLING of Observation, not a parent.
- validity_status drives downstream semantics:
    VALID + no Observation   → eligible for Negative Evidence (future milestone)
    INVALID + no Observation → inconclusive
    VALID + Observation      → positive evidence path
- score fields are SEPARATE dimensions, never collapsed into one "confidence".
- Negative Evidence is NOT implemented in Milestone 1.

DATA SHAPES ONLY. No business logic here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
import uuid


class TargetScope(str, Enum):
    SEGMENT = "SEGMENT"
    ASSET = "ASSET"
    REGION = "REGION"
    TRACK = "TRACK"


class ValidityStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class ObservationOpportunity(BaseModel):
    """
    Represents a sensing window during which a target could be observed.

    Edge-produced. Backend reads and persists.
    Primary simulation scope: target_scope = SEGMENT.
    """

    opportunity_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable unique identifier for this sensing opportunity.",
    )
    sensing_pass_id: str = Field(
        description="Identifier of the sensing pass (route segment traversal) that produced this."
    )
    bus_id: str = Field(description="Fleet vehicle.")
    device_id: str = Field(description="Edge compute device.")
    camera_id: str = Field(description="Camera module.")

    window_start: datetime = Field(description="UTC start of the sensing window.")
    window_end: datetime = Field(description="UTC end of the sensing window.")

    # Target descriptor
    target_scope: TargetScope = Field(
        description="Scope of what was being observed. SEGMENT is the primary Milestone 1 scope."
    )
    target_type: str = Field(
        description="Type of the target (e.g. 'road_segment', 'pothole', 'vehicle')."
    )
    target_id: Optional[str] = Field(
        default=None,
        description="ID of the target if known at time of observation. Optional for SEGMENT scope.",
    )
    edge_road_segment_hint: Optional[str] = Field(
        default=None,
        description=(
            "Advisory road-segment identifier from Edge GNSS. "
            "ADVISORY ONLY — not authoritative. Backend performs map-match."
        ),
    )

    # Sensing quality scores — DISTINCT dimensions, never merged into one score
    fov_valid: bool = Field(description="Was the target within field of view?")
    visibility_score: float = Field(ge=0.0, le=1.0, description="Atmospheric/lighting visibility.")
    illumination_score: float = Field(ge=0.0, le=1.0, description="Illumination quality.")
    blur_score: float = Field(ge=0.0, le=1.0, description="Motion blur quality (1=sharp).")
    occlusion_score: float = Field(ge=0.0, le=1.0, description="Occlusion quality (1=unoccluded).")
    viewing_angle_score: float = Field(ge=0.0, le=1.0, description="Geometric viewing angle quality.")
    distance_score: float = Field(ge=0.0, le=1.0, description="Distance-to-target quality.")
    sensor_health_score: float = Field(ge=0.0, le=1.0, description="Sensor health at time of observation.")
    gps_quality_score: float = Field(ge=0.0, le=1.0, description="GPS quality during the window.")

    # Composite — derived from individual scores
    opportunity_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Composite opportunity quality. Derived from individual scores. "
            "PROTOTYPE: calculation method is DECISION_REQUIRED for production weighting."
        ),
    )

    validity_status: ValidityStatus = Field(
        description="Whether this was a valid sensing opportunity."
    )
    invalid_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons why this opportunity was invalid (if applicable).",
    )

    coverage_fraction: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of target covered in the sensing window.",
    )

    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Distributed trace identifier for observability.",
    )

    model_config = ConfigDict()

"""
UrbanSense AI — RoadTwin State Contract (Read Model)
=====================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

RoadTwinState is a BACKEND-OWNED read model.
It represents the current world-state assertion for a road segment.

OWNERSHIP: Backend owns all RoadTwin state. Frontend reads only.
Frontend must NOT reconstruct RoadTwin rules.
Frontend must NOT calculate confidence aggregation.
Frontend must NOT perform state transitions.

MILESTONE 1 SCOPE:
- Only OBSERVED (and optionally CANDIDATE) states are implemented.
- The full 8-state lifecycle is NOT implemented yet.
- aggregate_confidence is the backend's fused assessment, NOT detector_confidence.

SEMANTIC NOTES:
- aggregate_confidence is DISTINCT from detector_confidence, observation_quality, gps_quality.
- Never collapse multiple confidence dimensions into one field.
- segment-level: one RoadTwin per road segment, not per pothole.

DATA SHAPES ONLY. No business logic here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RoadTwinState(str, Enum):
    """
    RoadTwin lifecycle states.
    Milestone 1: Only OBSERVED implemented. CANDIDATE may be established.
    Full lifecycle (CONFIRMED, REPAIRED, etc.) is future milestone scope.
    """
    OBSERVED = "OBSERVED"         # First qualifying positive observation
    CANDIDATE = "CANDIDATE"       # Multiple observations building confidence (future)
    # Future states (not implemented in M1):
    # CONFIRMED = "CONFIRMED"
    # ACTIVE = "ACTIVE"
    # UNDER_REPAIR = "UNDER_REPAIR"
    # REPAIRED = "REPAIRED"
    # REAPPEARED = "REAPPEARED"
    # CLOSED = "CLOSED"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"         # Recently validated
    STALE = "STALE"         # Not validated within threshold
    EXPIRED = "EXPIRED"     # Beyond acceptable validity window


class MaintenanceStatus(str, Enum):
    NONE = "NONE"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class RoadTwinStateResponse(BaseModel):
    """
    Read model for frontend consumption.
    This is what the GET /api/v1/roadtwin endpoint returns.
    Backend-owned — never modified by frontend.
    """

    roadtwin_id: str = Field(description="Unique identifier for this RoadTwin record.")
    road_segment_id: str = Field(description="Road segment this RoadTwin monitors.")

    subject_id: Optional[str] = Field(
        default=None,
        description="Specific subject (pothole, asset) if scoped below segment level.",
    )
    subject_type: Optional[str] = Field(
        default=None,
        description="Type of subject if sub-segment scope.",
    )

    # --- State ---
    current_state: RoadTwinState = Field(description="Current backend-asserted state.")

    # --- Confidence (BACKEND-OWNED, DISTINCT from detector_confidence) ---
    aggregate_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Backend-fused aggregate confidence. "
            "DISTINCT from detector_confidence, observation_quality, gps_quality."
        ),
    )

    # --- Evidence counts ---
    positive_evidence_count: int = Field(
        default=0,
        description="Number of valid positive observations contributing to this state.",
    )
    negative_evidence_count: int = Field(
        default=0,
        description="Number of valid Negative Evidence observations (future milestone).",
    )
    independent_bus_count: int = Field(
        default=0,
        description="Number of independent buses that have contributed observations.",
    )

    # --- Timestamps ---
    first_seen_at: datetime = Field(description="When this RoadTwin was first established.")
    last_seen_at: datetime = Field(description="Most recent observation timestamp.")
    last_validated_at: Optional[datetime] = Field(
        default=None,
        description="Most recent validation event timestamp.",
    )

    # --- Status fields ---
    freshness_status: FreshnessStatus = Field(default=FreshnessStatus.FRESH)
    maintenance_status: MaintenanceStatus = Field(default=MaintenanceStatus.NONE)
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)

    # --- Episode tracking (future) ---
    active_episode_id: Optional[str] = Field(
        default=None,
        description="Current active episode identifier (future milestone).",
    )
    previous_episode_id: Optional[str] = Field(
        default=None,
        description="Previous episode identifier (future milestone).",
    )
    history_ref: Optional[str] = Field(
        default=None,
        description="Reference to full history (future milestone).",
    )

    # --- Traceability ---
    last_event_id: Optional[str] = Field(
        default=None,
        description="event_id of the last event that modified this RoadTwin.",
    )
    last_observation_id: Optional[str] = Field(
        default=None,
        description="observation_id of the last observation.",
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

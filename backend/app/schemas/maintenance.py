"""
UrbanSense AI — Maintenance Lifecycle Schemas (Milestone 4)
===========================================================
Pydantic schemas for the maintenance lifecycle API.

Conceptual roles (full RBAC is DECISION-007 / OPEN):
    INSPECTOR      — can dispatch maintenance
    CITY_ENGINEER  — can review / override
    CONTRACTOR     — can report completion
    SYSTEM         — automated actions

REPAIR VERIFICATION NOTE:
- Submitting a REPAIR_COMPLETION_REPORTED action does NOT verify repair.
- Verification requires independent negative sensing evidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class MaintenanceDispatchRequest(BaseModel):
    """POST /api/v1/maintenance/dispatch — Dispatch a maintenance crew."""
    roadtwin_id: str = Field(description="RoadTwin to dispatch for")
    actor_role: str = Field(
        default="INSPECTOR",
        description="Role of the actor performing this action (INSPECTOR | CITY_ENGINEER | SYSTEM)",
    )
    actor_id: str = Field(description="Opaque actor identifier (placeholder for DECISION-007)")
    notes: Optional[str] = Field(default=None, description="Optional maintenance notes")
    work_order_id: Optional[str] = Field(default=None, description="External work order reference")
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="Scheduled maintenance visit time (UTC)",
    )
    trace_id: str = Field(default="", description="Distributed trace ID")


class ReportCompletionRequest(BaseModel):
    """POST /api/v1/maintenance/report-completion — Contractor self-reports repair."""
    roadtwin_id: str = Field(description="RoadTwin where repair was completed")
    actor_role: str = Field(
        default="CONTRACTOR",
        description="Role of the actor (CONTRACTOR | CITY_ENGINEER)",
    )
    actor_id: str = Field(description="Opaque actor identifier")
    notes: Optional[str] = Field(default=None, description="Completion notes / description of work done")
    work_order_id: Optional[str] = Field(default=None, description="External work order reference")
    claimed_completion_at: Optional[datetime] = Field(
        default=None,
        description="UTC time when repair was claimed complete. Defaults to now.",
    )
    trace_id: str = Field(default="", description="Distributed trace ID")


class NegativeEvidenceRequest(BaseModel):
    """POST /api/v1/maintenance/negative-evidence — Submit a VALID pass with no detection."""
    road_segment_id: str = Field(description="Segment that was scanned")
    opportunity_id: str = Field(description="The VALID opportunity that produced no detection")
    opportunity_score: float = Field(ge=0.0, le=1.0, description="Composite opportunity quality score")
    gps_quality: float = Field(ge=0.0, le=1.0, description="GPS quality during the pass")
    bus_id: str = Field(description="Fleet vehicle ID")
    device_id: Optional[str] = Field(default=None)
    camera_id: Optional[str] = Field(default=None)
    timestamp: datetime = Field(description="UTC time of the sensing pass")
    validity_status: str = Field(
        description="Opportunity validity: VALID | INVALID. Only VALID produces negative evidence.",
    )
    trace_id: str = Field(default="", description="Distributed trace ID")
    latitude: Optional[float] = Field(default=None, description="Latitude of the sensing pass")
    longitude: Optional[float] = Field(default=None, description="Longitude of the sensing pass")


class AuthorityActionResponse(BaseModel):
    """Response for maintenance lifecycle actions."""
    status: str
    action_id: str
    roadtwin_id: str
    prior_state: str
    new_state: str
    message: str
    created_at: datetime


class MaintenanceStatusResponse(BaseModel):
    """GET /api/v1/maintenance/{roadtwin_id} — Current maintenance status."""
    roadtwin_id: str
    road_segment_id: str
    current_state: str
    maintenance_status: str
    verification_status: str
    aggregate_confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    active_episode_id: Optional[str] = None
    previous_episode_id: Optional[str] = None
    last_validated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AuthorityActionRecord(BaseModel):
    """Record of a single authority action for the history endpoint."""
    action_id: str
    roadtwin_id: str
    road_segment_id: str
    action_type: str
    actor_role: str
    actor_id: str
    notes: Optional[str] = None
    work_order_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    claimed_completion_at: Optional[datetime] = None
    prior_roadtwin_state: str
    resulting_roadtwin_state: str
    trace_id: str
    created_at: Optional[datetime] = None


class NegativeEvidenceResponse(BaseModel):
    """Response for negative evidence submission."""
    status: str
    evidence_id: Optional[str] = None
    road_segment_id: str
    opportunity_id: str
    validity_status: str
    negative_evidence_strength: Optional[float] = None
    roadtwin_state: Optional[str] = None
    message: str
    created_at: datetime

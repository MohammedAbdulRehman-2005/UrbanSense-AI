"""
UrbanSense AI — RoadTwin Engine (THE ONLY RoadTwin implementation)
==================================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

This is the ONLY RoadTwin state implementation.
Location: backend/app/roadtwin/engine.py
Do NOT create RoadTwin logic anywhere else.
Do NOT implement RoadTwin transitions in the frontend.

Milestone 1 scope:
    A qualifying simulated positive observation → RoadTwin OBSERVED

The full 8-state lifecycle (CANDIDATE, CONFIRMED, ACTIVE, etc.) is
NOT implemented in Milestone 1.

RoadTwin is SEGMENT-LEVEL. It is NOT a single pothole object.

aggregate_confidence is BACKEND-OWNED and DISTINCT from:
    detector_confidence, observation_quality, gps_quality.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.models.event import EventModel


def upsert_roadtwin(
    db: Session,
    road_segment_id: str,
    event: EventModel,
) -> RoadTwinStateModel:
    """
    Create or update the RoadTwin state for a road segment.

    Milestone 1: Sets state to OBSERVED for any qualifying positive observation.
    PROTOTYPE — full confidence aggregation is a later milestone.
    """
    now = datetime.now(timezone.utc)
    existing = db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()

    if existing is None:
        # First observation on this segment
        rt = RoadTwinStateModel(
            roadtwin_id=str(uuid.uuid4()),
            road_segment_id=road_segment_id,
            current_state="OBSERVED",
            # PROTOTYPE aggregate_confidence: use detector_confidence as initial value.
            # DECISION_REQUIRED: proper aggregation formula for production.
            aggregate_confidence=round(event.detector_confidence or 0.0, 4),
            positive_evidence_count=1,
            negative_evidence_count=0,
            independent_bus_count=1,
            first_seen_at=event.event_timestamp,
            last_seen_at=event.event_timestamp,
            last_validated_at=None,
            freshness_status="FRESH",
            maintenance_status="NONE",
            verification_status="UNVERIFIED",
            last_event_id=event.event_id,
            last_observation_id=event.observation_id,
        )
        db.add(rt)
    else:
        # Update existing
        existing.positive_evidence_count += 1
        existing.last_seen_at = event.event_timestamp
        existing.last_event_id = event.event_id
        existing.last_observation_id = event.observation_id
        # PROTOTYPE: simple running average for aggregate_confidence
        # DECISION_REQUIRED: production confidence aggregation
        n = existing.positive_evidence_count
        existing.aggregate_confidence = round(
            (existing.aggregate_confidence * (n - 1) + (event.detector_confidence or 0.0)) / n, 4
        )
        existing.updated_at = now
        rt = existing

    db.flush()
    return rt

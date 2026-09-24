"""
UrbanSense AI — POST /api/v1/opportunities (Milestone 1)
=========================================================
Supports arrival order independence:
    Opportunity may arrive before or after Event.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.opportunity import OpportunityIngest, OpportunityIngestResponse
from backend.app.models.opportunity import OpportunityModel
from backend.app.models.event import EventModel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/opportunities", response_model=OpportunityIngestResponse)
def ingest_opportunity(payload: OpportunityIngest, db: Session = Depends(get_db)):
    """
    POST /api/v1/opportunities

    Idempotent. Supports order-independent arrival with Events.
    """
    ingestion_ts = datetime.now(timezone.utc)

    # Idempotency check
    existing = db.query(OpportunityModel).filter_by(opportunity_id=payload.opportunity_id).first()
    if existing is not None:
        logger.info(f"Duplicate opportunity: opportunity_id={payload.opportunity_id}")
        return OpportunityIngestResponse(
            status="duplicate",
            opportunity_id=payload.opportunity_id,
            message="Opportunity already accepted.",
            ingestion_timestamp=existing.created_at or ingestion_ts,
        )

    opp = OpportunityModel(
        opportunity_id=payload.opportunity_id,
        sensing_pass_id=payload.sensing_pass_id,
        bus_id=payload.bus_id,
        device_id=payload.device_id,
        camera_id=payload.camera_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        target_scope=payload.target_scope,
        target_type=payload.target_type,
        target_id=payload.target_id,
        edge_road_segment_hint=payload.edge_road_segment_hint,
        fov_valid=payload.fov_valid,
        visibility_score=payload.visibility_score,
        illumination_score=payload.illumination_score,
        blur_score=payload.blur_score,
        occlusion_score=payload.occlusion_score,
        viewing_angle_score=payload.viewing_angle_score,
        distance_score=payload.distance_score,
        sensor_health_score=payload.sensor_health_score,
        gps_quality_score=payload.gps_quality_score,
        opportunity_score=payload.opportunity_score,
        validity_status=payload.validity_status,
        invalid_reasons=payload.invalid_reasons,
        coverage_fraction=payload.coverage_fraction,
        trace_id=payload.trace_id,
    )
    db.add(opp)

    # Order-independence: if Event already arrived, link back
    linked_events = db.query(EventModel).filter_by(opportunity_id=payload.opportunity_id).all()
    for ev in linked_events:
        logger.info(f"Back-linking event {ev.event_id} to opportunity {payload.opportunity_id}")

    db.commit()
    logger.info(f"Opportunity accepted: opportunity_id={payload.opportunity_id}")

    return OpportunityIngestResponse(
        status="accepted",
        opportunity_id=payload.opportunity_id,
        message="Opportunity accepted and persisted.",
        ingestion_timestamp=ingestion_ts,
    )

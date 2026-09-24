"""
UrbanSense AI — GET /api/v1/roadtwin (Milestone 1)
===================================================
Read-only API for frontend map rendering.
Frontend must NOT reconstruct RoadTwin rules.
Frontend communicates ONLY through this API.
"""
from __future__ import annotations

from typing import List
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.roadtwin import RoadTwinResponse
from backend.app.models.roadtwin import RoadTwinStateModel

logger = logging.getLogger(__name__)
router = APIRouter()


def _model_to_response(rt: RoadTwinStateModel) -> RoadTwinResponse:
    seg = rt.segment
    return RoadTwinResponse(
        roadtwin_id=rt.roadtwin_id,
        road_segment_id=rt.road_segment_id,
        subject_id=rt.subject_id,
        subject_type=rt.subject_type,
        current_state=rt.current_state,
        aggregate_confidence=rt.aggregate_confidence,
        positive_evidence_count=rt.positive_evidence_count,
        negative_evidence_count=rt.negative_evidence_count,
        independent_bus_count=rt.independent_bus_count,
        first_seen_at=rt.first_seen_at,
        last_seen_at=rt.last_seen_at,
        last_validated_at=rt.last_validated_at,
        freshness_status=rt.freshness_status,
        maintenance_status=rt.maintenance_status,
        verification_status=rt.verification_status,
        active_episode_id=rt.active_episode_id,
        previous_episode_id=rt.previous_episode_id,
        last_event_id=rt.last_event_id,
        last_observation_id=rt.last_observation_id,
        segment_centroid_lat=seg.centroid_lat if seg else None,
        segment_centroid_lon=seg.centroid_lon if seg else None,
        segment_name=seg.name if seg else None,
    )


@router.get("/roadtwin", response_model=List[RoadTwinResponse])
def list_roadtwins(db: Session = Depends(get_db)):
    """List all RoadTwin states."""
    results = db.query(RoadTwinStateModel).all()
    return [_model_to_response(rt) for rt in results]


@router.get("/roadtwin/{roadtwin_id}", response_model=RoadTwinResponse)
def get_roadtwin(roadtwin_id: str, db: Session = Depends(get_db)):
    """Get a specific RoadTwin state by ID."""
    rt = db.query(RoadTwinStateModel).filter_by(roadtwin_id=roadtwin_id).first()
    if rt is None:
        raise HTTPException(status_code=404, detail=f"RoadTwin {roadtwin_id} not found")
    return _model_to_response(rt)

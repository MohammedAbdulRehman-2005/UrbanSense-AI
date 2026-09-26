"""
UrbanSense AI — GET /api/v1/evidence (Milestone 3)
Read-only API for evidence records associated with a road segment.
Frontend consumes this for display only; it does NOT reconstruct fusion logic.
"""
from __future__ import annotations

from typing import List, Optional
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.db.session import get_db
from backend.app.models.evidence import EvidenceModel

logger = logging.getLogger(__name__)
router = APIRouter()


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    event_id: Optional[str] = None
    observation_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    polarity: str
    bus_id: str
    camera_id: Optional[str] = None
    timestamp: datetime
    matched_road_segment_id: Optional[str] = None
    independence_class: str
    correlation_group_id: Optional[str] = None
    detector_confidence: Optional[float] = None
    observation_quality: Optional[float] = None
    gps_quality: Optional[float] = None
    evidence_weight: float
    fusion_strategy: str
    fusion_version: str
    lineage: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sensing_pass_id: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: Optional[datetime] = None


@router.get("/evidence", response_model=List[EvidenceResponse])
def list_evidence(
    road_segment_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/evidence
    Optional filter: ?road_segment_id=SEG-001
    Returns evidence records (append-only; never mutated).
    """
    q = db.query(EvidenceModel)
    if road_segment_id:
        q = q.filter_by(matched_road_segment_id=road_segment_id)
    results = q.order_by(EvidenceModel.created_at).all()
    return results

"""
UrbanSense AI — Maintenance Lifecycle API (Milestone 4)
=======================================================
Endpoints:
    POST   /api/v1/maintenance/dispatch            — Authority dispatches maintenance crew
    POST   /api/v1/maintenance/report-completion   — Contractor self-reports repair done
    POST   /api/v1/maintenance/negative-evidence   — Submit VALID pass with no detection
    GET    /api/v1/maintenance/{roadtwin_id}        — Read current maintenance status
    GET    /api/v1/maintenance/{roadtwin_id}/history — Read action history for a RoadTwin

OWNERSHIP RULES (DO NOT VIOLATE):
- RoadTwin state transitions: ONLY in backend/app/roadtwin/engine.py
- evidence_weight computation: ONLY in backend/app/fusion/engine.py
- This router only calls those engines — it never computes state directly.

REPAIR VERIFICATION RULE:
- POST /report-completion does NOT verify repair.
- It transitions to VERIFICATION_PENDING.
- VERIFIED_REPAIRED is only reached via negative sensing evidence
  submitted through POST /negative-evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.authority_action import AuthorityActionModel
from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.models.evidence import EvidenceModel
from backend.app.roadtwin.engine import apply_maintenance_action
from backend.app.fusion.engine import process_negative_evidence
from backend.app.schemas.maintenance import (
    MaintenanceDispatchRequest,
    ReportCompletionRequest,
    NegativeEvidenceRequest,
    AuthorityActionResponse,
    MaintenanceStatusResponse,
    AuthorityActionRecord,
    NegativeEvidenceResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/maintenance/dispatch", response_model=AuthorityActionResponse)
def dispatch_maintenance(payload: MaintenanceDispatchRequest, db: Session = Depends(get_db)):
    """
    POST /api/v1/maintenance/dispatch

    Dispatch a maintenance crew to address a confirmed road defect.

    Guard: RoadTwin must be in CONFIRMED or REAPPEARED state.
    Transition: CONFIRMED → MAINTENANCE_PENDING

    This does NOT verify repair. It only records the dispatch decision.
    """
    try:
        rt, action_id, prior_state, resulting_state = apply_maintenance_action(
            db=db,
            roadtwin_id=payload.roadtwin_id,
            action_type="MAINTENANCE_DISPATCHED",
            actor_role=payload.actor_role,
            actor_id=payload.actor_id,
            notes=payload.notes,
            work_order_id=payload.work_order_id,
            scheduled_at=payload.scheduled_at,
            claimed_completion_at=None,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    now = datetime.now(timezone.utc)
    action_record = AuthorityActionModel(
        action_id=action_id,
        road_segment_id=rt.road_segment_id,
        roadtwin_id=rt.roadtwin_id,
        action_type="MAINTENANCE_DISPATCHED",
        actor_role=payload.actor_role,
        actor_id=payload.actor_id,
        notes=payload.notes,
        work_order_id=payload.work_order_id,
        scheduled_at=payload.scheduled_at,
        claimed_completion_at=None,
        prior_roadtwin_state=prior_state,
        resulting_roadtwin_state=resulting_state,
        trace_id=payload.trace_id,
        created_at=now,
    )
    db.add(action_record)
    db.commit()

    logger.info(
        "Maintenance dispatched: roadtwin=%s action=%s %s->%s actor=%s(%s)",
        payload.roadtwin_id, action_id, prior_state, resulting_state,
        payload.actor_role, payload.actor_id,
    )

    return AuthorityActionResponse(
        status="accepted",
        action_id=action_id,
        roadtwin_id=rt.roadtwin_id,
        prior_state=prior_state,
        new_state=resulting_state,
        message=f"Maintenance dispatched. RoadTwin transitioned {prior_state} → {resulting_state}.",
        created_at=now,
    )


@router.post("/maintenance/report-completion", response_model=AuthorityActionResponse)
def report_completion(payload: ReportCompletionRequest, db: Session = Depends(get_db)):
    """
    POST /api/v1/maintenance/report-completion

    Contractor self-reports that repair work is complete.

    Guard: RoadTwin must be in MAINTENANCE_PENDING state.
    Transition: MAINTENANCE_PENDING → VERIFICATION_PENDING

    IMPORTANT: This does NOT verify repair. Repair is only VERIFIED_REPAIRED
    when subsequent independent negative sensing evidence supports it.
    The transition to VERIFICATION_PENDING signals that independent evidence
    collection should now be evaluated.
    """
    claimed_at = payload.claimed_completion_at or datetime.now(timezone.utc)

    try:
        rt, action_id, prior_state, resulting_state = apply_maintenance_action(
            db=db,
            roadtwin_id=payload.roadtwin_id,
            action_type="REPAIR_COMPLETION_REPORTED",
            actor_role=payload.actor_role,
            actor_id=payload.actor_id,
            notes=payload.notes,
            work_order_id=payload.work_order_id,
            scheduled_at=None,
            claimed_completion_at=claimed_at,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    now = datetime.now(timezone.utc)
    action_record = AuthorityActionModel(
        action_id=action_id,
        road_segment_id=rt.road_segment_id,
        roadtwin_id=rt.roadtwin_id,
        action_type="REPAIR_COMPLETION_REPORTED",
        actor_role=payload.actor_role,
        actor_id=payload.actor_id,
        notes=payload.notes,
        work_order_id=payload.work_order_id,
        scheduled_at=None,
        claimed_completion_at=claimed_at,
        prior_roadtwin_state=prior_state,
        resulting_roadtwin_state=resulting_state,
        trace_id=payload.trace_id,
        created_at=now,
    )
    db.add(action_record)
    db.commit()

    logger.info(
        "Repair completion reported: roadtwin=%s action=%s %s->%s actor=%s(%s)",
        payload.roadtwin_id, action_id, prior_state, resulting_state,
        payload.actor_role, payload.actor_id,
    )

    return AuthorityActionResponse(
        status="accepted",
        action_id=action_id,
        roadtwin_id=rt.roadtwin_id,
        prior_state=prior_state,
        new_state=resulting_state,
        message=(
            f"Completion reported. RoadTwin transitioned {prior_state} → {resulting_state}. "
            f"Awaiting independent verification evidence. "
            f"NOTE: This does not verify repair — independent sensing evidence is required."
        ),
        created_at=now,
    )


@router.post("/maintenance/negative-evidence", response_model=NegativeEvidenceResponse)
def submit_negative_evidence(payload: NegativeEvidenceRequest, db: Session = Depends(get_db)):
    """
    POST /api/v1/maintenance/negative-evidence

    Submit a VALID sensing pass that observed no road defect.

    M4 GATING RULES (enforced in FusionEngine):
        VALID + no detection → candidate negative evidence (recorded)
        INVALID + no detection → INCONCLUSIVE (rejected, not recorded)
        A poor-quality pass is NOT evidence of repair.
        A missing camera frame is NOT evidence of repair.
        A missing GPS fix is NOT evidence of repair.

    If the segment is in VERIFICATION_PENDING and the negative evidence
    strength is sufficient, the FusionEngine will transition it to
    VERIFIED_REPAIRED.
    """
    now = datetime.now(timezone.utc)
    try:
        evidence = process_negative_evidence(
            db=db,
            road_segment_id=payload.road_segment_id,
            opportunity_id=payload.opportunity_id,
            opportunity_score=payload.opportunity_score,
            gps_quality=payload.gps_quality,
            bus_id=payload.bus_id,
            device_id=payload.device_id,
            camera_id=payload.camera_id,
            timestamp=payload.timestamp,
            validity_status=payload.validity_status,
            trace_id=payload.trace_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    except Exception as exc:
        logger.error("Negative evidence processing error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Negative evidence processing failed: {exc}")

    # Read current RoadTwin state for response
    rt = db.query(RoadTwinStateModel).filter_by(road_segment_id=payload.road_segment_id).first()
    roadtwin_state = rt.current_state if rt else None

    if evidence is None:
        db.commit()
        return NegativeEvidenceResponse(
            status="gated_out",
            evidence_id=None,
            road_segment_id=payload.road_segment_id,
            opportunity_id=payload.opportunity_id,
            validity_status=payload.validity_status,
            negative_evidence_strength=None,
            roadtwin_state=roadtwin_state,
            message=(
                f"Negative evidence gated out (validity_status={payload.validity_status!r}). "
                "INCONCLUSIVE — not recorded. See M4 gating rules."
            ),
            created_at=now,
        )

    db.commit()
    return NegativeEvidenceResponse(
        status="accepted",
        evidence_id=evidence.evidence_id,
        road_segment_id=payload.road_segment_id,
        opportunity_id=payload.opportunity_id,
        validity_status=payload.validity_status,
        negative_evidence_strength=evidence.negative_evidence_strength,
        roadtwin_state=roadtwin_state,
        message=(
            f"Negative evidence recorded (strength={evidence.negative_evidence_strength:.4f}). "
            f"RoadTwin state={roadtwin_state!r}."
        ),
        created_at=now,
    )


@router.get("/maintenance/{roadtwin_id}", response_model=MaintenanceStatusResponse)
def get_maintenance_status(roadtwin_id: str, db: Session = Depends(get_db)):
    """
    GET /api/v1/maintenance/{roadtwin_id}

    Read the current maintenance lifecycle status of a RoadTwin.
    """
    rt = db.query(RoadTwinStateModel).filter_by(roadtwin_id=roadtwin_id).first()
    if rt is None:
        raise HTTPException(status_code=404, detail=f"RoadTwin {roadtwin_id} not found")

    return MaintenanceStatusResponse(
        roadtwin_id=rt.roadtwin_id,
        road_segment_id=rt.road_segment_id,
        current_state=rt.current_state,
        maintenance_status=rt.maintenance_status,
        verification_status=rt.verification_status,
        aggregate_confidence=rt.aggregate_confidence,
        positive_evidence_count=rt.positive_evidence_count,
        negative_evidence_count=rt.negative_evidence_count,
        active_episode_id=rt.active_episode_id,
        previous_episode_id=rt.previous_episode_id,
        last_validated_at=rt.last_validated_at,
        updated_at=rt.updated_at,
    )


@router.get("/maintenance/{roadtwin_id}/history", response_model=List[AuthorityActionRecord])
def get_maintenance_history(roadtwin_id: str, db: Session = Depends(get_db)):
    """
    GET /api/v1/maintenance/{roadtwin_id}/history

    Read the full authority action history for a RoadTwin, ordered newest first.
    """
    # Verify RoadTwin exists
    rt = db.query(RoadTwinStateModel).filter_by(roadtwin_id=roadtwin_id).first()
    if rt is None:
        raise HTTPException(status_code=404, detail=f"RoadTwin {roadtwin_id} not found")

    actions = (
        db.query(AuthorityActionModel)
        .filter_by(roadtwin_id=roadtwin_id)
        .order_by(AuthorityActionModel.created_at.desc())
        .all()
    )
    return [
        AuthorityActionRecord(
            action_id=a.action_id,
            roadtwin_id=a.roadtwin_id,
            road_segment_id=a.road_segment_id,
            action_type=a.action_type,
            actor_role=a.actor_role,
            actor_id=a.actor_id,
            notes=a.notes,
            work_order_id=a.work_order_id,
            scheduled_at=a.scheduled_at,
            claimed_completion_at=a.claimed_completion_at,
            prior_roadtwin_state=a.prior_roadtwin_state,
            resulting_roadtwin_state=a.resulting_roadtwin_state,
            trace_id=a.trace_id,
            created_at=a.created_at,
        )
        for a in actions
    ]

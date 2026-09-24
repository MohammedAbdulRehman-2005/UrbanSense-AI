"""
UrbanSense AI — THE ONE AND ONLY FusionEngine (Milestone 3)
===========================================================
Location: backend/app/fusion/engine.py

RULES (from R4):
- Do NOT create a second FusionEngine.
- Do NOT compute evidence_weight anywhere except here.
- Do NOT compute evidence_weight in: Edge, OpportunityEvaluator, EventBuilder,
  any API route, or the frontend.
- This engine is called from the events API after event persistence.

MVP Fusion Formula:
    evidence_weight_i = detector_confidence_i x observation_quality_i x gps_quality_i
    aggregate_confidence = 1 - prod(1 - evidence_weight_i)  [over INDEPENDENT evidence]

CRITICAL:
- detector_confidence is an UNCALIBRATED prototype heuristic signal.
  Do NOT treat it as a statistically calibrated probability. (DECISION-020)
- Confirmation thresholds are DECISION_REQUIRED. Do NOT invent:
  '2 buses = confirmed', 'confidence > 0.8 = confirmed', etc.
  Transitions require at least 2 INDEPENDENT contributions (PROTOTYPE M3 rule).
- DECISION_REQUIRED: production confirmation policy must be established via
  a validated calibration study and domain agreement.

State machine (M3 scope only): OBSERVED -> CANDIDATE -> CONFIRMED
M4 states (MAINTENANCE_PENDING, VERIFIED_REPAIRED, REAPPEARED) are NOT M3 scope.
"""
from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models.evidence import EvidenceModel
from backend.app.models.event import EventModel
from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.fusion.independence import (
    IndependenceInput,
    IndependenceClass,
    classify_independence,
)

logger = logging.getLogger(__name__)

# Fusion strategy
FUSION_STRATEGY = "MVP"
FUSION_VERSION = "1.0"


def _mvp_evidence_weight(
    detector_confidence: Optional[float],
    observation_quality: Optional[float],
    gps_quality: Optional[float],
) -> float:
    """
    MVP evidence weight formula (R4 section 18.2):
        evidence_weight = detector_confidence x observation_quality x gps_quality

    - Treats None quality signals as 0.0 (cannot certify quality -> zero weight).
    - PROTOTYPE: all input signals are uncalibrated prototype values (DECISION-020).
    """
    dc = detector_confidence if detector_confidence is not None else 0.0
    oq = observation_quality if observation_quality is not None else 0.0
    gq = gps_quality if gps_quality is not None else 0.0
    return round(dc * oq * gq, 6)


def _bayes_aggregate(weights: list) -> float:
    """
    Noisy-OR aggregate: aggregate_confidence = 1 - prod(1 - weight_i)
    Applied only to INDEPENDENT weights (CORRELATED/DUPLICATE are excluded).
    """
    result = 1.0
    for w in weights:
        result *= (1.0 - w)
    return round(1.0 - result, 6)


# M3 scope state transitions: OBSERVED -> CANDIDATE -> CONFIRMED only.
# DECISION_REQUIRED: production confirmation thresholds require calibration.
# PROTOTYPE M3 rule: >=2 INDEPENDENT evidence contributions -> CANDIDATE;
#                    >=2 INDEPENDENT evidence from different buses -> CONFIRMED.
_M3_CANDIDATE_MIN_INDEPENDENT = 2     # PROTOTYPE / DECISION_REQUIRED
_M3_CONFIRMED_MIN_INDEPENDENT_BUSES = 2  # PROTOTYPE / DECISION_REQUIRED


def _compute_new_state(
    current_state: str,
    independent_count: int,
    independent_bus_ids: set,
) -> tuple:
    """
    Returns (new_state, transition_reason).
    Only advances state, never regresses (M3 scope).
    """
    bus_count = len(independent_bus_ids)

    if (
        current_state in ("OBSERVED", "CANDIDATE")
        and bus_count >= _M3_CONFIRMED_MIN_INDEPENDENT_BUSES
        and independent_count >= _M3_CANDIDATE_MIN_INDEPENDENT
    ):
        return (
            "CONFIRMED",
            (
                f"CONFIRMED by Noisy-OR fusion: {independent_count} INDEPENDENT evidence "
                f"from {bus_count} independent bus(es). "
                "PROTOTYPE M3 rule (DECISION_REQUIRED for production thresholds)."
            ),
        )

    if (
        current_state == "OBSERVED"
        and independent_count >= _M3_CANDIDATE_MIN_INDEPENDENT
    ):
        return (
            "CANDIDATE",
            (
                f"Promoted OBSERVED->CANDIDATE: {independent_count} INDEPENDENT evidence. "
                "PROTOTYPE M3 rule (DECISION_REQUIRED for production thresholds)."
            ),
        )

    return current_state, "No threshold met - state unchanged"


def _load_existing_contributions(
    db: Session,
    road_segment_id: str,
) -> list:
    """
    Load all existing POSITIVE evidence for this road segment for independence
    classification. Returns IndependenceInput structs for classifier use.
    """
    existing_evidence = (
        db.query(EvidenceModel)
        .filter_by(matched_road_segment_id=road_segment_id)
        .filter(EvidenceModel.polarity == "POSITIVE")
        .all()
    )
    inputs = []
    for ev in existing_evidence:
        inputs.append(IndependenceInput(
            event_id=ev.event_id or f"_unk_{ev.evidence_id}",
            bus_id=ev.bus_id,
            device_id=ev.device_id or "",
            camera_id=ev.camera_id or "",
            sensing_pass_id=None,
            event_timestamp_iso=ev.timestamp.isoformat() if ev.timestamp else "",
            latitude=0.0,
            longitude=0.0,
            observation_id=ev.observation_id,
            opportunity_id=ev.opportunity_id,
        ))
    return inputs


def process_event_evidence(
    db: Session,
    event: EventModel,
    road_segment_id: str,
) -> Optional[EvidenceModel]:
    """
    THE ONLY place where evidence_weight is computed.

    1. Load existing evidence for this segment.
    2. Classify independence of this event contribution.
    3. Compute evidence_weight (MVP formula).
    4. Persist EvidenceModel (append-only).
    5. Update aggregate_confidence on RoadTwinStateModel (Noisy-OR, INDEPENDENT only).
    6. Apply state machine transitions (OBSERVED -> CANDIDATE -> CONFIRMED).
    7. Return created EvidenceModel.
    """
    now = datetime.now(timezone.utc)

    # Build IndependenceInput for this event
    candidate = IndependenceInput(
        event_id=event.event_id,
        bus_id=event.bus_id,
        device_id=event.device_id or "",
        camera_id=event.camera_id or "",
        sensing_pass_id=event.opportunity_id,
        event_timestamp_iso=event.event_timestamp.isoformat() if event.event_timestamp else "",
        latitude=event.latitude or 0.0,
        longitude=event.longitude or 0.0,
        observation_id=event.observation_id,
        opportunity_id=event.opportunity_id,
    )

    # Load existing evidence for classification
    existing = _load_existing_contributions(db, road_segment_id)

    # Independence classification
    result = classify_independence(candidate, existing, road_segment_id)
    independence_class = result.independence_class
    correlation_group_id = result.correlation_group_id

    logger.info(
        "Independence classification: event_id=%s bus_id=%s segment=%s -> %s [%s]",
        event.event_id, event.bus_id, road_segment_id,
        independence_class.value, result.reason,
    )

    # Compute evidence_weight (THE ONLY PLACE)
    evidence_weight = _mvp_evidence_weight(
        detector_confidence=event.detector_confidence,
        observation_quality=event.observation_quality,
        gps_quality=event.gps_quality,
    )

    logger.info(
        "Evidence weight computed: event_id=%s weight=%.6f (dc=%.4f x oq=%.4f x gq=%.4f) PROTOTYPE/UNCALIBRATED",
        event.event_id, evidence_weight,
        event.detector_confidence or 0.0,
        event.observation_quality or 0.0,
        event.gps_quality or 0.0,
    )

    # Build lineage record
    lineage = json.dumps({
        "event_id": event.event_id,
        "bus_id": event.bus_id,
        "device_id": event.device_id,
        "camera_id": event.camera_id,
        "independence_class": independence_class.value,
        "independence_reason": result.reason,
        "formula": "MVP: detector_confidence * observation_quality * gps_quality",
        "fusion_strategy": FUSION_STRATEGY,
        "fusion_version": FUSION_VERSION,
        "prototype_note": "Uncalibrated heuristic signals; DECISION-020",
    })

    # Persist EvidenceModel (append-only)
    evidence = EvidenceModel(
        evidence_id=str(uuid.uuid4()),
        event_id=event.event_id,
        observation_id=event.observation_id,
        opportunity_id=event.opportunity_id,
        polarity="POSITIVE",
        source_type="BUS_CAMERA",
        source_id=event.bus_id,
        bus_id=event.bus_id,
        device_id=event.device_id,
        camera_id=event.camera_id,
        timestamp=event.event_timestamp,
        ingestion_timestamp=now,
        matched_road_segment_id=road_segment_id,
        map_match_status=event.map_match_status,
        detector_confidence=event.detector_confidence,
        observation_quality=event.observation_quality,
        opportunity_score=None,
        gps_quality=event.gps_quality,
        sensor_health=None,
        independence_class=independence_class.value,
        correlation_group_id=correlation_group_id,
        evidence_weight=evidence_weight,
        fusion_strategy=FUSION_STRATEGY,
        fusion_version=FUSION_VERSION,
        negative_evidence_strength=None,
        lineage=lineage,
    )
    db.add(evidence)
    db.flush()

    # Update RoadTwin aggregate_confidence and state
    rt = (
        db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()
    )
    if rt is None:
        logger.warning(
            "FusionEngine: RoadTwin not found for segment=%s — evidence persisted but no state update",
            road_segment_id,
        )
        return evidence

    # Collect all POSITIVE evidence for Noisy-OR (including the new one)
    all_positive_evidence = (
        db.query(EvidenceModel)
        .filter_by(matched_road_segment_id=road_segment_id)
        .filter(EvidenceModel.polarity == "POSITIVE")
        .all()
    )

    independent_weights = [
        ev.evidence_weight
        for ev in all_positive_evidence
        if ev.independence_class == IndependenceClass.INDEPENDENT.value
    ]
    independent_bus_ids = {
        ev.bus_id
        for ev in all_positive_evidence
        if ev.independence_class == IndependenceClass.INDEPENDENT.value
    }
    independent_count = len(independent_weights)

    # Compute Noisy-OR aggregate
    new_aggregate = _bayes_aggregate(independent_weights) if independent_weights else 0.0

    # Update RoadTwin
    old_state = rt.current_state
    rt.positive_evidence_count = len(all_positive_evidence)
    rt.aggregate_confidence = new_aggregate
    rt.independent_bus_count = len(independent_bus_ids)
    rt.last_seen_at = event.event_timestamp
    rt.last_event_id = event.event_id
    rt.last_observation_id = event.observation_id
    rt.updated_at = now

    # Apply state transition
    new_state, transition_reason = _compute_new_state(
        current_state=old_state,
        independent_count=independent_count,
        independent_bus_ids=independent_bus_ids,
    )
    rt.current_state = new_state

    if new_state != old_state:
        logger.info(
            "RoadTwin state transition: segment=%s %s -> %s | reason: %s",
            road_segment_id, old_state, new_state, transition_reason,
        )
    else:
        logger.info(
            "RoadTwin state unchanged: segment=%s state=%s aggregate_confidence=%.4f independent_count=%d independent_buses=%d",
            road_segment_id, new_state, new_aggregate, independent_count, len(independent_bus_ids),
        )

    db.flush()
    return evidence

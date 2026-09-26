"""
UrbanSense AI — THE ONE AND ONLY FusionEngine (Milestone 3 + Milestone 4)
==========================================================================
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

NEGATIVE EVIDENCE FORMULA (M4):
    negative_evidence_strength = opportunity_score x gps_quality
    Gating rule: opportunity must be VALID (validity_status == 'VALID')
    VALID + no positive observation → candidate negative evidence
    INVALID + no observation → INCONCLUSIVE (not recorded)
    VALID + positive observation → positive evidence (not negative)

CRITICAL:
- detector_confidence is an UNCALIBRATED prototype heuristic signal.
  Do NOT treat it as a statistically calibrated probability. (DECISION-020)
- Confirmation thresholds are DECISION_REQUIRED. Do NOT invent:
  '2 buses = confirmed', 'confidence > 0.8 = confirmed', etc.
- DECISION_REQUIRED: production confirmation policy must be established via
  a validated calibration study and domain agreement.

State machine (M4 scope): OBSERVED -> CANDIDATE -> CONFIRMED (FusionEngine)
    FusionEngine also handles: VERIFICATION_PENDING -> VERIFIED_REPAIRED
    via apply_negative_evidence_transition() in roadtwin engine.
    Maintenance transitions (CONFIRMED -> MAINTENANCE_PENDING, etc.) are
    handled ONLY by the maintenance API via apply_maintenance_action().
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


def _mvp_negative_evidence_strength(
    opportunity_score: Optional[float],
    gps_quality: Optional[float],
) -> float:
    """
    MVP negative evidence strength formula (M4):
        negative_evidence_strength = opportunity_score x gps_quality

    Both signals must be present and the opportunity must be VALID (gating
    is enforced by the caller before calling this function).
    PROTOTYPE: uncalibrated signals. DECISION_REQUIRED for production.
    """
    opp = opportunity_score if opportunity_score is not None else 0.0
    gq = gps_quality if gps_quality is not None else 0.0
    return round(opp * gq, 6)


def _bayes_aggregate(weights: list) -> float:
    """
    Noisy-OR aggregate: aggregate_confidence = 1 - prod(1 - weight_i)
    Applied only to INDEPENDENT weights (CORRELATED/DUPLICATE are excluded).
    """
    result = 1.0
    for w in weights:
        result *= (1.0 - w)
    return round(1.0 - result, 6)


# M3/M4 scope state transitions for positive evidence:
# OBSERVED -> CANDIDATE -> CONFIRMED only.
# DECISION_REQUIRED: production confirmation thresholds require calibration.
# PROTOTYPE M3 rule: >=2 INDEPENDENT evidence contributions -> CANDIDATE;
#                    >=2 INDEPENDENT evidence from different buses -> CONFIRMED.
_M3_CANDIDATE_MIN_INDEPENDENT = 2     # PROTOTYPE / DECISION_REQUIRED
_M3_CONFIRMED_MIN_INDEPENDENT_BUSES = 2  # PROTOTYPE / DECISION_REQUIRED

_POSITIVE_EVIDENCE_ADVANCEABLE_STATES = {"OBSERVED", "CANDIDATE"}


def _compute_new_state(
    current_state: str,
    independent_count: int,
    independent_bus_ids: set,
) -> tuple:
    """
    Returns (new_state, transition_reason).
    Only advances state via positive evidence path.
    Maintenance-driven transitions are in roadtwin/engine.py.
    """
    bus_count = len(independent_bus_ids)

    if current_state == "REAPPEARED":
        # In new episode, requires multiple independent buses to re-confirm
        if (
            bus_count >= _M3_CONFIRMED_MIN_INDEPENDENT_BUSES
            and independent_count >= _M3_CANDIDATE_MIN_INDEPENDENT
        ):
            return (
                "CONFIRMED",
                (
                    f"Reappeared defect CONFIRMED by Noisy-OR fusion: {independent_count} INDEPENDENT evidence "
                    f"from {bus_count} independent bus(es) in new episode. "
                    "PROTOTYPE M3/M4 rule."
                ),
            )
        return "REAPPEARED", "Defect reappeared in new episode — state remains REAPPEARED"

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
                "PROTOTYPE M3/M4 rule (DECISION_REQUIRED for production thresholds)."
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
                "PROTOTYPE M3/M4 rule (DECISION_REQUIRED for production thresholds)."
            ),
        )

    return current_state, "No threshold met - state unchanged"


def _load_existing_contributions(
    db: Session,
    road_segment_id: str,
    since_timestamp: Optional[datetime] = None,
) -> list:
    """
    Load existing POSITIVE evidence for this road segment for independence
    classification. Returns IndependenceInput structs for classifier use.
    When since_timestamp is provided, only loads evidence from that time onwards.
    (Used for REAPPEARED recurrence to avoid counting prior-episode evidence.)
    """
    query = (
        db.query(EvidenceModel)
        .filter_by(matched_road_segment_id=road_segment_id)
        .filter(EvidenceModel.polarity == "POSITIVE")
    )
    if since_timestamp is not None:
        query = query.filter(EvidenceModel.timestamp >= since_timestamp)
    existing_evidence = query.all()
    inputs = []
    for ev in existing_evidence:
        inputs.append(IndependenceInput(
            event_id=ev.event_id or f"_unk_{ev.evidence_id}",
            bus_id=ev.bus_id,
            device_id=ev.device_id or "",
            camera_id=ev.camera_id or "",
            sensing_pass_id=ev.sensing_pass_id or ev.opportunity_id,
            event_timestamp_iso=ev.timestamp.isoformat() if ev.timestamp else "",
            latitude=ev.latitude,
            longitude=ev.longitude,
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
       For REAPPEARED state: re-runs OBSERVED->CANDIDATE->CONFIRMED for new episode.
       For maintenance-active states: increments counts without state transition.
    7. Return created EvidenceModel.
    """
    now = datetime.now(timezone.utc)

    # Check if RoadTwin exists and if an active episode cutoff applies
    rt_check = db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()
    since_ts = None
    if rt_check and rt_check.previous_episode_id is not None and rt_check.first_seen_at is not None:
        since_ts = rt_check.first_seen_at

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

    # Load existing evidence for classification (scoped to active episode if applicable)
    existing = _load_existing_contributions(db, road_segment_id, since_timestamp=since_ts)

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
        latitude=event.latitude,
        longitude=event.longitude,
        sensing_pass_id=event.opportunity_id,
        trace_id=event.trace_id,
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

    # Collect POSITIVE evidence for Noisy-OR (including the new one)
    # Scoped to active episode if a previous episode exists (recurrence)
    evidence_query = (
        db.query(EvidenceModel)
        .filter_by(matched_road_segment_id=road_segment_id)
        .filter(EvidenceModel.polarity == "POSITIVE")
    )
    if rt.previous_episode_id is not None and rt.first_seen_at is not None:
        evidence_query = evidence_query.filter(EvidenceModel.timestamp >= rt.first_seen_at)
    all_positive_evidence = evidence_query.all()

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

    # Apply state transition — only for advanceable states
    # Maintenance-active states are NOT advanced by positive evidence
    from backend.app.roadtwin.engine import (
        _POSITIVE_EVIDENCE_ADVANCEABLE_STATES,
        apply_positive_evidence_transition,
    )
    if old_state in _POSITIVE_EVIDENCE_ADVANCEABLE_STATES:
        new_state, transition_reason = _compute_new_state(
            current_state=old_state,
            independent_count=independent_count,
            independent_bus_ids=independent_bus_ids,
        )
        if new_state != old_state:
            apply_positive_evidence_transition(rt, new_state, transition_reason)
    else:
        logger.info(
            "RoadTwin state=%s is maintenance-active: positive evidence counted but no state transition. "
            "segment=%s event_id=%s",
            old_state, road_segment_id, event.event_id,
        )

    logger.info(
        "RoadTwin updated: segment=%s state=%s aggregate_confidence=%.4f "
        "independent_count=%d independent_buses=%d",
        road_segment_id, rt.current_state, new_aggregate,
        independent_count, len(independent_bus_ids),
    )

    db.flush()
    return evidence


def process_negative_evidence(
    db: Session,
    road_segment_id: str,
    opportunity_id: str,
    opportunity_score: float,
    gps_quality: float,
    bus_id: str,
    device_id: Optional[str],
    camera_id: Optional[str],
    timestamp: datetime,
    validity_status: str,
    trace_id: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Optional[EvidenceModel]:
    """
    Process a NEGATIVE evidence record.

    M4 NEGATIVE EVIDENCE GATING RULES:
        VALID opportunity + no positive observation → compute negative evidence
        INVALID opportunity → INCONCLUSIVE → do NOT record negative evidence
        A poor-quality pass is NOT evidence of repair.
        A missing camera frame is NOT evidence of repair.
        A missing GPS fix is NOT evidence of repair.

    ONLY called when:
        1. An opportunity was evaluated as VALID
        2. No positive defect event was generated for this opportunity
        3. The RoadTwin is in a state where negative evidence is meaningful
           (primarily VERIFICATION_PENDING)

    Returns the created EvidenceModel if negative evidence was recorded,
    None if gating rules prevented recording.
    """
    now = datetime.now(timezone.utc)

    # Gate 1: Opportunity must be VALID
    if validity_status != "VALID":
        logger.info(
            "Negative evidence gated out: opportunity_id=%s validity_status=%s "
            "(INCONCLUSIVE — not recording negative evidence)",
            opportunity_id, validity_status,
        )
        return None

    # Gate 2: RoadTwin must be in a state where negative evidence matters
    rt = db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()
    if rt is None:
        logger.info(
            "Negative evidence: no RoadTwin for segment=%s — not recording",
            road_segment_id,
        )
        return None

    current_state = rt.current_state
    # Negative evidence is meaningful in VERIFICATION_PENDING state.
    # In CONFIRMED / OBSERVED / CANDIDATE it is recorded but does not trigger transitions.
    meaningful_states = {"VERIFICATION_PENDING", "CONFIRMED", "CANDIDATE", "OBSERVED"}
    if current_state not in meaningful_states:
        logger.info(
            "Negative evidence for segment=%s: state=%s — not in meaningful states, skipping",
            road_segment_id, current_state,
        )
        return None

    # Resolve coordinates if not provided
    if latitude is None or longitude is None:
        try:
            from backend.app.models.road_segment import RoadSegment
            seg = db.query(RoadSegment).filter_by(segment_id=road_segment_id).first()
            if seg:
                latitude = latitude if latitude is not None else seg.centroid_lat
                longitude = longitude if longitude is not None else seg.centroid_lon
        except Exception:
            pass

    # Independence classification for negative evidence
    since_ts = None
    if rt.previous_episode_id is not None and rt.first_seen_at is not None:
        since_ts = rt.first_seen_at

    existing = _load_existing_contributions(db, road_segment_id, since_timestamp=since_ts)

    candidate = IndependenceInput(
        event_id=f"neg_{opportunity_id}",
        bus_id=bus_id,
        device_id=device_id or "",
        camera_id=camera_id or "",
        sensing_pass_id=opportunity_id,
        event_timestamp_iso=timestamp.isoformat() if timestamp else "",
        latitude=latitude,
        longitude=longitude,
        observation_id=None,
        opportunity_id=opportunity_id,
    )

    result = classify_independence(candidate, existing, road_segment_id)
    independence_class = result.independence_class
    correlation_group_id = result.correlation_group_id

    logger.info(
        "Negative evidence independence: opp=%s bus=%s segment=%s -> %s [%s]",
        opportunity_id, bus_id, road_segment_id, independence_class.value, result.reason,
    )

    # Compute negative_evidence_strength (THE ONLY PLACE — inside FusionEngine)
    neg_strength = _mvp_negative_evidence_strength(
        opportunity_score=opportunity_score,
        gps_quality=gps_quality,
    )

    lineage = json.dumps({
        "opportunity_id": opportunity_id,
        "bus_id": bus_id,
        "independence_class": independence_class.value,
        "independence_reason": result.reason,
        "formula": "MVP: opportunity_score * gps_quality",
        "validity_status": validity_status,
        "fusion_strategy": FUSION_STRATEGY,
        "fusion_version": FUSION_VERSION,
        "prototype_note": "Negative evidence strength is uncalibrated (DECISION-020)",
    })

    evidence = EvidenceModel(
        evidence_id=str(uuid.uuid4()),
        event_id=None,  # Negative evidence has no associated positive event
        observation_id=None,
        opportunity_id=opportunity_id,
        polarity="NEGATIVE",
        source_type="BUS_CAMERA",
        source_id=bus_id,
        bus_id=bus_id,
        device_id=device_id,
        camera_id=camera_id,
        timestamp=timestamp,
        ingestion_timestamp=now,
        latitude=latitude,
        longitude=longitude,
        sensing_pass_id=opportunity_id,
        trace_id=trace_id,
        matched_road_segment_id=road_segment_id,
        map_match_status="MATCHED",
        detector_confidence=None,    # Negative evidence has no detector confidence
        observation_quality=None,
        opportunity_score=opportunity_score,
        gps_quality=gps_quality,
        sensor_health=None,
        independence_class=independence_class.value,
        correlation_group_id=correlation_group_id,
        evidence_weight=0.0,  # Negative evidence weight is 0 for positive fusion
        fusion_strategy=FUSION_STRATEGY,
        fusion_version=FUSION_VERSION,
        negative_evidence_strength=neg_strength,
        lineage=lineage,
    )
    db.add(evidence)

    # Update negative_evidence_count on RoadTwin
    rt.negative_evidence_count = (rt.negative_evidence_count or 0) + 1
    rt.last_validated_at = timestamp
    rt.updated_at = now
    db.flush()

    logger.info(
        "Negative evidence recorded: segment=%s opportunity_id=%s "
        "neg_strength=%.4f state=%s independence=%s (PROTOTYPE/UNCALIBRATED)",
        road_segment_id, opportunity_id, neg_strength, current_state, independence_class.value,
    )

    # Apply VERIFIED_REPAIRED transition only if in VERIFICATION_PENDING and INDEPENDENT
    if current_state == "VERIFICATION_PENDING":
        if independence_class == IndependenceClass.INDEPENDENT:
            from backend.app.roadtwin.engine import apply_negative_evidence_transition
            transition_result = apply_negative_evidence_transition(
                db=db,
                road_segment_id=road_segment_id,
                negative_evidence_strength=neg_strength,
                trace_id=trace_id,
            )
            if transition_result:
                _rt, old_s, new_s = transition_result
                logger.info(
                    "RoadTwin transitioned by independent negative evidence: segment=%s %s->%s neg_strength=%.4f",
                    road_segment_id, old_s, new_s, neg_strength,
                )
        else:
            logger.info(
                "Negative evidence for segment=%s is %s (not INDEPENDENT): will not trigger VERIFIED_REPAIRED transition",
                road_segment_id, independence_class.value,
            )

    return evidence

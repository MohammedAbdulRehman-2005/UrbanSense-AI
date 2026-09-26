"""
UrbanSense AI — RoadTwin Engine (THE ONLY RoadTwin implementation)
==================================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

This is the ONLY RoadTwin state implementation.
Location: backend/app/roadtwin/engine.py
Do NOT create RoadTwin logic anywhere else.
Do NOT implement RoadTwin transitions in the frontend.

M4 LIFECYCLE STATES (full set):
    OBSERVED            — first positive detection
    CANDIDATE           — ≥2 independent evidence pieces
    CONFIRMED           — ≥2 independent buses confirmed
    MAINTENANCE_PENDING — authority has dispatched maintenance crew
    REPAIR_REPORTED     — contractor self-reports completion (NOT verified)
    VERIFICATION_PENDING — awaiting independent negative evidence
    VERIFIED_REPAIRED   — independent negative sensing evidence confirms repair
    REAPPEARED          — defect redetected after VERIFIED_REPAIRED

TRANSITION GUARDS (explicit, authoritative):
    CONFIRMED            → MAINTENANCE_PENDING  : MAINTENANCE_DISPATCHED action
    MAINTENANCE_PENDING  → REPAIR_REPORTED      : REPAIR_COMPLETION_REPORTED action
    REPAIR_REPORTED      → VERIFICATION_PENDING : auto (on report-completion)
    VERIFICATION_PENDING → VERIFIED_REPAIRED    : sufficient NEGATIVE evidence (FusionEngine)
    VERIFIED_REPAIRED    → REAPPEARED           : new POSITIVE evidence on same segment
    REAPPEARED           → MAINTENANCE_PENDING  : new dispatch

OWNERSHIP INVARIANTS:
- Only this module may call rt.current_state = ...
- FusionEngine calls apply_negative_evidence_transition() for negative evidence path
- Maintenance API calls apply_maintenance_action() for authority actions
- upsert_roadtwin() handles OBSERVED/CANDIDATE/CONFIRMED (positive detection path)

REPAIR VERIFICATION RULE:
- A contractor self-report is NOT proof of repair.
- Repair is only VERIFIED_REPAIRED by subsequent independent negative sensing evidence.
- A poor-quality opportunity is not negative evidence.
- A missing camera frame is not negative evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.models.event import EventModel

import logging
logger = logging.getLogger(__name__)


# ── M4 state vocabulary ──────────────────────────────────────────────────────
# Ordered from earliest to most advanced lifecycle stage.
# REAPPEARED is a re-entry state and does not have a simple ordinal.
ACTIVE_DEFECT_STATES = {
    "OBSERVED", "CANDIDATE", "CONFIRMED",
    "MAINTENANCE_PENDING", "REPAIR_REPORTED", "VERIFICATION_PENDING",
}
POST_REPAIR_STATES = {"VERIFIED_REPAIRED"}
REAPPEAR_TRIGGER_STATES = {"VERIFIED_REPAIRED"}

# States in which new positive defect evidence should NOT advance OBSERVED→CANDIDATE→CONFIRMED
# (maintenance is already in progress or complete)
MAINTENANCE_ACTIVE_STATES = {
    "MAINTENANCE_PENDING", "REPAIR_REPORTED", "VERIFICATION_PENDING",
}
POSITIVE_EVIDENCE_ADVANCEABLE_STATES = {"OBSERVED", "CANDIDATE"}
_POSITIVE_EVIDENCE_ADVANCEABLE_STATES = POSITIVE_EVIDENCE_ADVANCEABLE_STATES


def upsert_roadtwin(
    db: Session,
    road_segment_id: str,
    event: EventModel,
) -> RoadTwinStateModel:
    """
    Create or update the RoadTwin state for a road segment.

    Handles:
      - First observation: creates OBSERVED record
      - VERIFIED_REPAIRED + new positive detection: transitions to REAPPEARED
      - MAINTENANCE_ACTIVE states: increments counts but does NOT advance state
        (state is managed by maintenance workflow)
      - All other states: increments positive_evidence_count + last_seen_at

    NOTE: OBSERVED→CANDIDATE→CONFIRMED transitions are driven by
    FusionEngine via process_event_evidence(), not by this function.
    This function only creates the initial OBSERVED record and handles
    REAPPEARED detection. The FusionEngine updates state for evidence-driven
    transitions.
    """
    now = datetime.now(timezone.utc)
    existing = db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()

    if existing is None:
        # First observation on this segment
        rt = RoadTwinStateModel(
            roadtwin_id=str(uuid.uuid4()),
            road_segment_id=road_segment_id,
            current_state="OBSERVED",
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
        db.flush()
        return rt

    # --- REAPPEARANCE detection ---
    # If the defect was VERIFIED_REPAIRED and we see new positive evidence,
    # transition to REAPPEARED and start a new episode.
    if existing.current_state == "VERIFIED_REPAIRED":
        old_episode = existing.active_episode_id
        new_episode = str(uuid.uuid4())
        logger.info(
            "RoadTwin REAPPEARANCE detected: segment=%s roadtwin=%s "
            "prev_episode=%s new_episode=%s event_id=%s",
            road_segment_id, existing.roadtwin_id, old_episode, new_episode, event.event_id,
        )
        existing.current_state = "REAPPEARED"
        existing.previous_episode_id = old_episode
        existing.active_episode_id = new_episode
        existing.first_seen_at = event.event_timestamp
        existing.positive_evidence_count = 1
        existing.negative_evidence_count = 0  # reset for new episode
        existing.independent_bus_count = 1
        existing.maintenance_status = "NONE"
        existing.verification_status = "UNVERIFIED"
        existing.last_seen_at = event.event_timestamp
        existing.last_event_id = event.event_id
        existing.last_observation_id = event.observation_id
        existing.aggregate_confidence = round(event.detector_confidence or 0.0, 4)
        existing.updated_at = now
        db.flush()
        return existing

    # --- Standard update for all other states ---
    existing.positive_evidence_count += 1
    existing.last_seen_at = event.event_timestamp
    existing.last_event_id = event.event_id
    existing.last_observation_id = event.observation_id
    existing.updated_at = now
    db.flush()
    return existing


def apply_maintenance_action(
    db: Session,
    roadtwin_id: str,
    action_type: str,
    actor_role: str,
    actor_id: str,
    notes: Optional[str] = None,
    work_order_id: Optional[str] = None,
    scheduled_at: Optional[datetime] = None,
    claimed_completion_at: Optional[datetime] = None,
    trace_id: str = "",
) -> tuple[RoadTwinStateModel, str]:
    """
    Apply a maintenance lifecycle action to a RoadTwin.

    Valid action_type values:
        MAINTENANCE_DISPATCHED         — authority schedules a crew
        REPAIR_COMPLETION_REPORTED     — contractor self-reports completion

    Returns (updated RoadTwinStateModel, action_id).
    Raises ValueError on invalid transition guard.

    GUARD RULES:
        MAINTENANCE_DISPATCHED:
            Allowed from: CONFIRMED, REAPPEARED
            → MAINTENANCE_PENDING
            Sets maintenance_status = 'DISPATCHED'

        REPAIR_COMPLETION_REPORTED:
            Allowed from: MAINTENANCE_PENDING
            → REPAIR_REPORTED → VERIFICATION_PENDING
            Sets maintenance_status = 'COMPLETION_REPORTED'
            verification_status = 'PENDING'
            NOTE: This does NOT verify repair. Repair verification requires
            subsequent independent negative sensing evidence.
    """
    import uuid as _uuid
    now = datetime.now(timezone.utc)

    rt = db.query(RoadTwinStateModel).filter_by(roadtwin_id=roadtwin_id).first()
    if rt is None:
        raise ValueError(f"RoadTwin {roadtwin_id} not found")

    prior_state = rt.current_state
    action_id = str(_uuid.uuid4())

    if action_type == "MAINTENANCE_DISPATCHED":
        _guard_state(
            allowed={"CONFIRMED", "REAPPEARED"},
            actual=prior_state,
            action=action_type,
        )
        rt.current_state = "MAINTENANCE_PENDING"
        rt.maintenance_status = "DISPATCHED"
        if not rt.active_episode_id:
            rt.active_episode_id = str(_uuid.uuid4())
        rt.updated_at = now

    elif action_type == "REPAIR_COMPLETION_REPORTED":
        _guard_state(
            allowed={"MAINTENANCE_PENDING", "REPAIR_REPORTED"},
            actual=prior_state,
            action=action_type,
        )
        # Master Plan lifecycle: MAINTENANCE_PENDING -> REPAIR_REPORTED -> VERIFICATION_PENDING
        # Contractor report triggers REPAIR_REPORTED which automatically enters VERIFICATION_PENDING.
        rt.current_state = "VERIFICATION_PENDING"
        rt.maintenance_status = "COMPLETION_REPORTED"
        rt.verification_status = "PENDING"
        rt.last_validated_at = claimed_completion_at or now
        rt.updated_at = now

    elif action_type == "START_VERIFICATION":
        _guard_state(
            allowed={"REPAIR_REPORTED"},
            actual=prior_state,
            action=action_type,
        )
        rt.current_state = "VERIFICATION_PENDING"
        rt.verification_status = "PENDING"
        rt.updated_at = now

    else:
        raise ValueError(f"Unknown action_type: {action_type!r}")

    resulting_state = rt.current_state
    db.flush()

    logger.info(
        "RoadTwin maintenance action: roadtwin=%s action=%s %s→%s actor=%s(%s) trace=%s",
        roadtwin_id, action_type, prior_state, resulting_state,
        actor_role, actor_id, trace_id,
    )

    return rt, action_id, prior_state, resulting_state


def apply_negative_evidence_transition(
    db: Session,
    road_segment_id: str,
    negative_evidence_strength: float,
    trace_id: str = "",
) -> Optional[tuple]:
    """
    Called ONLY by FusionEngine after processing a NEGATIVE evidence record.

    Transition guard:
        VERIFICATION_PENDING + sufficient negative evidence → VERIFIED_REPAIRED

    The threshold for 'sufficient' is PROTOTYPE / DECISION_REQUIRED.
    PROTOTYPE M4 rule: negative_evidence_strength >= 0.5 → VERIFIED_REPAIRED
    (This threshold is uncalibrated; DECISION_REQUIRED for production.)

    Returns (rt, old_state, new_state) if a transition occurred, else None.
    """
    # PROTOTYPE threshold — DECISION_REQUIRED
    _NEG_VERIFICATION_THRESHOLD = 0.5  # PROTOTYPE / DECISION_REQUIRED

    now = datetime.now(timezone.utc)
    rt = db.query(RoadTwinStateModel).filter_by(road_segment_id=road_segment_id).first()
    if rt is None:
        logger.warning(
            "apply_negative_evidence_transition: RoadTwin not found for segment=%s",
            road_segment_id,
        )
        return None

    old_state = rt.current_state

    if old_state != "VERIFICATION_PENDING":
        logger.info(
            "Negative evidence for segment=%s: state=%s is not VERIFICATION_PENDING — no M4 transition",
            road_segment_id, old_state,
        )
        return None

    if negative_evidence_strength >= _NEG_VERIFICATION_THRESHOLD:
        rt.current_state = "VERIFIED_REPAIRED"
        rt.verification_status = "VERIFIED"
        rt.maintenance_status = "COMPLETED"
        rt.last_validated_at = now
        rt.updated_at = now
        db.flush()
        logger.info(
            "RoadTwin VERIFIED_REPAIRED: segment=%s roadtwin=%s neg_strength=%.4f threshold=%.4f trace=%s "
            "(PROTOTYPE threshold — DECISION_REQUIRED)",
            road_segment_id, rt.roadtwin_id,
            negative_evidence_strength, _NEG_VERIFICATION_THRESHOLD, trace_id,
        )
        return rt, old_state, "VERIFIED_REPAIRED"
    else:
        logger.info(
            "Negative evidence for segment=%s: strength=%.4f < threshold=%.4f — state remains VERIFICATION_PENDING "
            "(PROTOTYPE threshold — DECISION_REQUIRED)",
            road_segment_id, negative_evidence_strength, _NEG_VERIFICATION_THRESHOLD,
        )
        return None


def apply_positive_evidence_transition(
    rt: RoadTwinStateModel,
    new_state: str,
    reason: str = "",
) -> None:
    """
    Apply an evidence-driven state transition to a RoadTwin instance.
    Enforces RoadTwin module ownership of state mutation.
    """
    old_state = rt.current_state
    rt.current_state = new_state
    rt.updated_at = datetime.now(timezone.utc)
    if new_state != old_state:
        logger.info(
            "RoadTwin positive evidence state transition: segment=%s %s -> %s | reason: %s",
            rt.road_segment_id, old_state, new_state, reason,
        )


def _guard_state(allowed: set, actual: str, action: str) -> None:
    """Raise ValueError if actual state is not in allowed."""
    if actual not in allowed:
        raise ValueError(
            f"Invalid state transition for action {action!r}: "
            f"current state is {actual!r}, allowed states are {sorted(allowed)}"
        )

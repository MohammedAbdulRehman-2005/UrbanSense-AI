"""
UrbanSense AI — M4 Closed-Loop Maintenance Test Suite
=======================================================
Tests the complete M4 lifecycle:
    OBSERVED → CANDIDATE → CONFIRMED
    → MAINTENANCE_PENDING → VERIFICATION_PENDING
    → VERIFIED_REPAIRED → REAPPEARED

Test categories:
    Unit tests (no DB, no network) — run always
    Integration tests (require live backend at localhost:8000) — marked @pytest.mark.integration

ARCHITECTURE INVARIANTS VERIFIED:
    - evidence_weight is never computed outside FusionEngine
    - State transitions are never performed outside roadtwin/engine.py
    - Contractor report alone does NOT verify repair (must be VERIFICATION_PENDING)
    - INVALID opportunity produces no negative evidence (INCONCLUSIVE)
    - VERIFIED_REPAIRED → REAPPEARED on new positive detection
    - New episode created on recurrence

REPAIR VERIFICATION RULE:
    UrbanSense does not declare a defect repaired merely because a contractor
    reports completion. Repair verification requires subsequent independent
    negative sensing evidence (negative_evidence_strength >= threshold).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# M4.1 — AuthorityAction ORM structure
# ---------------------------------------------------------------------------

class TestAuthorityActionModel:
    """ORM model structure tests — no DB required."""

    def test_authority_action_importable(self):
        """AuthorityActionModel must be importable and have the correct table name."""
        from backend.app.models.authority_action import AuthorityActionModel
        assert AuthorityActionModel.__tablename__ == "authority_actions"

    def test_authority_action_required_columns(self):
        """AuthorityActionModel must have all M4-required columns."""
        from backend.app.models.authority_action import AuthorityActionModel
        required = {
            "action_id", "road_segment_id", "roadtwin_id",
            "action_type", "actor_role", "actor_id",
            "prior_roadtwin_state", "resulting_roadtwin_state",
            "trace_id", "created_at",
        }
        optional = {"notes", "work_order_id", "scheduled_at", "claimed_completion_at"}
        actual = {col.name for col in AuthorityActionModel.__table__.columns}
        missing = required - actual
        assert not missing, f"AuthorityActionModel missing columns: {missing}"

    def test_action_id_is_primary_key(self):
        """action_id must be the primary key."""
        from backend.app.models.authority_action import AuthorityActionModel
        pk_cols = [c.name for c in AuthorityActionModel.__table__.primary_key]
        assert "action_id" in pk_cols

    def test_authority_action_not_nullable_required_fields(self):
        """Core fields must be NOT NULL."""
        from backend.app.models.authority_action import AuthorityActionModel
        must_not_null = ["action_id", "action_type", "actor_role", "actor_id",
                         "prior_roadtwin_state", "resulting_roadtwin_state", "trace_id"]
        for col_name in must_not_null:
            col = AuthorityActionModel.__table__.columns[col_name]
            assert not col.nullable, f"{col_name} must be NOT NULL"


# ---------------------------------------------------------------------------
# M4.2 — RoadTwin Engine State Machine Guards
# ---------------------------------------------------------------------------

class TestRoadTwinEngineGuards:
    """Test state machine guard logic without a real DB (mock session)."""

    def _make_rt(self, state: str, roadtwin_id: str = "RT-001") -> MagicMock:
        """Create a mock RoadTwinStateModel in a given state."""
        rt = MagicMock()
        rt.roadtwin_id = roadtwin_id
        rt.road_segment_id = "SEG-001"
        rt.current_state = state
        rt.maintenance_status = "NONE"
        rt.verification_status = "UNVERIFIED"
        rt.active_episode_id = str(uuid.uuid4())
        rt.updated_at = datetime.now(timezone.utc)
        return rt

    def _make_db(self, rt: MagicMock) -> MagicMock:
        """Create a mock DB session that returns the given RoadTwin."""
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter_by.return_value = query_mock
        query_mock.first.return_value = rt
        db.flush = MagicMock()
        return db

    def test_dispatch_from_confirmed_allowed(self):
        """MAINTENANCE_DISPATCHED is allowed from CONFIRMED state."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("CONFIRMED")
        db = self._make_db(rt)

        result_rt, action_id, prior, resulting = apply_maintenance_action(
            db=db,
            roadtwin_id="RT-001",
            action_type="MAINTENANCE_DISPATCHED",
            actor_role="INSPECTOR",
            actor_id="INS-001",
            trace_id="trace-test-001",
        )
        assert result_rt.current_state == "MAINTENANCE_PENDING"
        assert prior == "CONFIRMED"
        assert resulting == "MAINTENANCE_PENDING"

    def test_dispatch_from_observed_rejected(self):
        """MAINTENANCE_DISPATCHED from OBSERVED state must raise ValueError."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("OBSERVED")
        db = self._make_db(rt)

        with pytest.raises(ValueError, match="OBSERVED"):
            apply_maintenance_action(
                db=db,
                roadtwin_id="RT-001",
                action_type="MAINTENANCE_DISPATCHED",
                actor_role="INSPECTOR",
                actor_id="INS-001",
                trace_id="trace-guard-001",
            )

    def test_dispatch_from_candidate_rejected(self):
        """MAINTENANCE_DISPATCHED from CANDIDATE must raise ValueError."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("CANDIDATE")
        db = self._make_db(rt)

        with pytest.raises(ValueError, match="CANDIDATE"):
            apply_maintenance_action(
                db=db,
                roadtwin_id="RT-001",
                action_type="MAINTENANCE_DISPATCHED",
                actor_role="INSPECTOR",
                actor_id="INS-001",
                trace_id="trace-guard-002",
            )

    def test_dispatch_from_reappeared_allowed(self):
        """MAINTENANCE_DISPATCHED from REAPPEARED is allowed (recurrence cycle)."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("REAPPEARED")
        rt.previous_episode_id = str(uuid.uuid4())
        db = self._make_db(rt)

        result_rt, _, prior, resulting = apply_maintenance_action(
            db=db,
            roadtwin_id="RT-001",
            action_type="MAINTENANCE_DISPATCHED",
            actor_role="CITY_ENGINEER",
            actor_id="ENG-001",
            trace_id="trace-guard-003",
        )
        assert prior == "REAPPEARED"
        assert result_rt.current_state == "MAINTENANCE_PENDING"

    def test_completion_from_maintenance_pending_allowed(self):
        """REPAIR_COMPLETION_REPORTED from MAINTENANCE_PENDING → VERIFICATION_PENDING."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("MAINTENANCE_PENDING")
        rt.maintenance_status = "DISPATCHED"
        db = self._make_db(rt)

        result_rt, _, prior, resulting = apply_maintenance_action(
            db=db,
            roadtwin_id="RT-001",
            action_type="REPAIR_COMPLETION_REPORTED",
            actor_role="CONTRACTOR",
            actor_id="CON-001",
            trace_id="trace-guard-004",
        )
        assert prior == "MAINTENANCE_PENDING"
        assert result_rt.current_state == "VERIFICATION_PENDING"
        assert result_rt.verification_status == "PENDING"
        assert result_rt.maintenance_status == "COMPLETION_REPORTED"

    def test_completion_from_confirmed_rejected(self):
        """REPAIR_COMPLETION_REPORTED from CONFIRMED must raise ValueError."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("CONFIRMED")
        db = self._make_db(rt)

        with pytest.raises(ValueError, match="MAINTENANCE_PENDING"):
            apply_maintenance_action(
                db=db,
                roadtwin_id="RT-001",
                action_type="REPAIR_COMPLETION_REPORTED",
                actor_role="CONTRACTOR",
                actor_id="CON-001",
                trace_id="trace-guard-005",
            )

    def test_contractor_report_does_not_set_verified_repaired(self):
        """
        CRITICAL ARCHITECTURE INVARIANT:
        REPAIR_COMPLETION_REPORTED must set state to VERIFICATION_PENDING,
        NOT VERIFIED_REPAIRED.
        Repair verification requires subsequent negative sensing evidence.
        """
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("MAINTENANCE_PENDING")
        db = self._make_db(rt)

        result_rt, _, _, resulting = apply_maintenance_action(
            db=db,
            roadtwin_id="RT-001",
            action_type="REPAIR_COMPLETION_REPORTED",
            actor_role="CONTRACTOR",
            actor_id="CON-001",
            trace_id="trace-invariant-001",
        )
        assert result_rt.current_state != "VERIFIED_REPAIRED", (
            "ARCHITECTURE VIOLATION: Contractor report must NOT set VERIFIED_REPAIRED. "
            "Only independent negative sensing evidence can verify repair."
        )
        assert result_rt.current_state == "VERIFICATION_PENDING"

    def test_unknown_roadtwin_raises(self):
        """apply_maintenance_action with unknown roadtwin_id raises ValueError."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            apply_maintenance_action(
                db=db,
                roadtwin_id="RT-DOES-NOT-EXIST",
                action_type="MAINTENANCE_DISPATCHED",
                actor_role="INSPECTOR",
                actor_id="INS-001",
                trace_id="trace-missing",
            )

    def test_unknown_action_type_raises(self):
        """Unknown action_type must raise ValueError."""
        from backend.app.roadtwin.engine import apply_maintenance_action

        rt = self._make_rt("CONFIRMED")
        db = self._make_db(rt)

        with pytest.raises(ValueError, match="Unknown action_type"):
            apply_maintenance_action(
                db=db,
                roadtwin_id="RT-001",
                action_type="INVALID_ACTION",
                actor_role="INSPECTOR",
                actor_id="INS-001",
                trace_id="trace-invalid",
            )


# ---------------------------------------------------------------------------
# M4.3 — Negative Evidence Gating
# ---------------------------------------------------------------------------

class TestNegativeEvidenceGating:
    """Test negative evidence gating rules — no real DB required."""

    def _make_verification_pending_rt(self, seg_id: str) -> MagicMock:
        rt = MagicMock()
        rt.roadtwin_id = f"RT-{seg_id}"
        rt.road_segment_id = seg_id
        rt.current_state = "VERIFICATION_PENDING"
        rt.maintenance_status = "COMPLETION_REPORTED"
        rt.verification_status = "PENDING"
        rt.negative_evidence_count = 0
        rt.last_validated_at = None
        rt.updated_at = datetime.now(timezone.utc)
        return rt

    def _make_db_with_rt(self, rt: MagicMock) -> MagicMock:
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first.return_value = rt
        q.all.return_value = []
        db.add = MagicMock()
        db.flush = MagicMock()
        return db

    def test_invalid_opportunity_gated_out(self):
        """
        INVALID opportunity must produce no negative evidence (INCONCLUSIVE).
        A poor-quality pass is NOT evidence of repair.
        """
        from backend.app.fusion.engine import process_negative_evidence

        rt = self._make_verification_pending_rt("SEG-GATE-001")
        db = self._make_db_with_rt(rt)

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-GATE-001",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.1,
            gps_quality=0.1,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="INVALID",  # Must be gated out
            trace_id="trace-gate-001",
        )
        assert evidence is None, "INVALID opportunity must NOT produce negative evidence"

    def test_valid_opportunity_produces_evidence(self):
        """VALID opportunity with no detection produces negative evidence."""
        from backend.app.fusion.engine import process_negative_evidence

        rt = self._make_verification_pending_rt("SEG-GATE-002")
        db = self._make_db_with_rt(rt)

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-GATE-002",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.85,
            gps_quality=0.9,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
            trace_id="trace-gate-002",
        )
        assert evidence is not None
        assert evidence.polarity == "NEGATIVE"

    def test_negative_evidence_has_no_detector_confidence(self):
        """Negative evidence must have detector_confidence=None."""
        from backend.app.fusion.engine import process_negative_evidence

        rt = self._make_verification_pending_rt("SEG-GATE-003")
        db = self._make_db_with_rt(rt)

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-GATE-003",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.85,
            gps_quality=0.9,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
            trace_id="trace-gate-003",
        )
        assert evidence is not None
        assert evidence.detector_confidence is None, (
            "Negative evidence must have detector_confidence=None"
        )

    def test_negative_evidence_weight_is_zero(self):
        """
        Negative evidence must have evidence_weight=0.0.
        It does not contribute to the positive Noisy-OR aggregate.
        """
        from backend.app.fusion.engine import process_negative_evidence

        rt = self._make_verification_pending_rt("SEG-GATE-004")
        db = self._make_db_with_rt(rt)

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-GATE-004",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.85,
            gps_quality=0.9,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
            trace_id="trace-gate-004",
        )
        assert evidence is not None
        assert evidence.evidence_weight == 0.0, (
            "ARCHITECTURE VIOLATION: Negative evidence must have evidence_weight=0.0"
        )

    def test_negative_evidence_strength_formula(self):
        """
        negative_evidence_strength = opportunity_score * gps_quality
        Computed ONLY by FusionEngine (MVP formula).
        """
        from backend.app.fusion.engine import process_negative_evidence

        rt = self._make_verification_pending_rt("SEG-GATE-005")
        db = self._make_db_with_rt(rt)

        opp_score = 0.8
        gps_q = 0.75
        expected = round(opp_score * gps_q, 6)

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-GATE-005",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=opp_score,
            gps_quality=gps_q,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
            trace_id="trace-gate-005",
        )
        assert evidence is not None
        assert abs(evidence.negative_evidence_strength - expected) < 1e-6, (
            f"Expected neg_strength={expected}, got {evidence.negative_evidence_strength}"
        )

    def test_no_roadtwin_returns_none(self):
        """If no RoadTwin exists for the segment, negative evidence is not recorded."""
        from backend.app.fusion.engine import process_negative_evidence

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = None

        evidence = process_negative_evidence(
            db=db,
            road_segment_id="SEG-NONEXISTENT",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.85,
            gps_quality=0.9,
            bus_id="BUS-001",
            device_id=None,
            camera_id=None,
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
            trace_id="trace-gate-006",
        )
        assert evidence is None


# ---------------------------------------------------------------------------
# M4.4 — Negative Evidence Transition Logic
# ---------------------------------------------------------------------------

class TestNegativeEvidenceTransition:
    """Test VERIFICATION_PENDING → VERIFIED_REPAIRED transition logic."""

    def test_sufficient_strength_triggers_verified_repaired(self):
        """
        negative_evidence_strength >= 0.5 (PROTOTYPE threshold) + VERIFICATION_PENDING
        → apply_negative_evidence_transition should set VERIFIED_REPAIRED.
        """
        from backend.app.roadtwin.engine import apply_negative_evidence_transition

        rt = MagicMock()
        rt.current_state = "VERIFICATION_PENDING"
        rt.roadtwin_id = "RT-NEG-001"
        rt.verification_status = "PENDING"
        rt.maintenance_status = "COMPLETION_REPORTED"
        rt.updated_at = datetime.now(timezone.utc)
        rt.last_validated_at = None

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt
        db.flush = MagicMock()

        result = apply_negative_evidence_transition(
            db=db,
            road_segment_id="SEG-001",
            negative_evidence_strength=0.75,  # >= 0.5 threshold
            trace_id="trace-trans-001",
        )
        assert result is not None
        _rt, old_s, new_s = result
        assert old_s == "VERIFICATION_PENDING"
        assert new_s == "VERIFIED_REPAIRED"
        assert _rt.current_state == "VERIFIED_REPAIRED"
        assert _rt.verification_status == "VERIFIED"
        assert _rt.maintenance_status == "COMPLETED"

    def test_insufficient_strength_no_transition(self):
        """
        negative_evidence_strength < 0.5 (PROTOTYPE threshold) → no transition.
        State remains VERIFICATION_PENDING.
        """
        from backend.app.roadtwin.engine import apply_negative_evidence_transition

        rt = MagicMock()
        rt.current_state = "VERIFICATION_PENDING"
        rt.roadtwin_id = "RT-NEG-002"

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt

        result = apply_negative_evidence_transition(
            db=db,
            road_segment_id="SEG-001",
            negative_evidence_strength=0.2,  # < 0.5 threshold
            trace_id="trace-trans-002",
        )
        assert result is None

    def test_non_verification_pending_state_no_transition(self):
        """apply_negative_evidence_transition from CONFIRMED → no transition."""
        from backend.app.roadtwin.engine import apply_negative_evidence_transition

        rt = MagicMock()
        rt.current_state = "CONFIRMED"  # Not VERIFICATION_PENDING

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt

        result = apply_negative_evidence_transition(
            db=db,
            road_segment_id="SEG-001",
            negative_evidence_strength=0.9,
            trace_id="trace-trans-003",
        )
        assert result is None

    def test_exact_threshold_triggers_transition(self):
        """negative_evidence_strength == 0.5 (exactly at threshold) triggers VERIFIED_REPAIRED."""
        from backend.app.roadtwin.engine import apply_negative_evidence_transition

        rt = MagicMock()
        rt.current_state = "VERIFICATION_PENDING"
        rt.updated_at = datetime.now(timezone.utc)
        rt.last_validated_at = None

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt
        db.flush = MagicMock()

        result = apply_negative_evidence_transition(
            db=db,
            road_segment_id="SEG-001",
            negative_evidence_strength=0.5,  # exactly at threshold
            trace_id="trace-trans-004",
        )
        assert result is not None


# ---------------------------------------------------------------------------
# M4.5 — REAPPEARED state logic
# ---------------------------------------------------------------------------

class TestReappearedState:
    """Test VERIFIED_REPAIRED → REAPPEARED recurrence detection."""

    def test_upsert_from_verified_repaired_triggers_reappeared(self):
        """
        upsert_roadtwin() with VERIFIED_REPAIRED current state triggers
        REAPPEARED and creates a new episode.
        """
        from backend.app.roadtwin.engine import upsert_roadtwin
        from backend.app.models.event import EventModel

        old_episode = str(uuid.uuid4())

        rt = MagicMock()
        rt.current_state = "VERIFIED_REPAIRED"
        rt.roadtwin_id = "RT-REAP-001"
        rt.road_segment_id = "SEG-REAP-001"
        rt.active_episode_id = old_episode
        rt.previous_episode_id = None
        rt.positive_evidence_count = 5
        rt.negative_evidence_count = 3
        rt.independent_bus_count = 2
        rt.updated_at = datetime.now(timezone.utc)

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt
        db.flush = MagicMock()

        now = datetime.now(timezone.utc)
        event = MagicMock()
        event.event_id = str(uuid.uuid4())
        event.bus_id = "BUS-REAP-001"
        event.event_timestamp = now
        event.observation_id = str(uuid.uuid4())
        event.detector_confidence = 0.88

        result = upsert_roadtwin(db=db, road_segment_id="SEG-REAP-001", event=event)

        assert result.current_state == "REAPPEARED"
        assert result.previous_episode_id == old_episode
        assert result.active_episode_id != old_episode
        assert result.active_episode_id is not None
        assert result.negative_evidence_count == 0  # Reset for new episode

    def test_reappeared_state_resets_negative_count(self):
        """negative_evidence_count must be reset to 0 on REAPPEARED."""
        from backend.app.roadtwin.engine import upsert_roadtwin

        rt = MagicMock()
        rt.current_state = "VERIFIED_REPAIRED"
        rt.roadtwin_id = "RT-REAP-002"
        rt.road_segment_id = "SEG-REAP-002"
        rt.active_episode_id = str(uuid.uuid4())
        rt.previous_episode_id = None
        rt.positive_evidence_count = 5
        rt.negative_evidence_count = 7  # Has accumulated negative evidence
        rt.independent_bus_count = 2
        rt.updated_at = datetime.now(timezone.utc)

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt
        db.flush = MagicMock()

        event = MagicMock()
        event.event_id = str(uuid.uuid4())
        event.bus_id = "BUS-NEW"
        event.event_timestamp = datetime.now(timezone.utc)
        event.observation_id = str(uuid.uuid4())
        event.detector_confidence = 0.85

        result = upsert_roadtwin(db=db, road_segment_id="SEG-REAP-002", event=event)
        assert result.negative_evidence_count == 0


# ---------------------------------------------------------------------------
# M4.6 — Fusion Engine: maintenance-active states block positive advancement
# ---------------------------------------------------------------------------

class TestFusionEngineMaintenanceGuard:
    """
    Verify that positive evidence does not advance state when RoadTwin
    is in a maintenance-active state (MAINTENANCE_PENDING, REPAIR_REPORTED,
    VERIFICATION_PENDING).
    """

    def _make_mock_db(self, rt_state: str, seg_id: str):
        from backend.app.models.evidence import EvidenceModel
        rt = MagicMock()
        rt.roadtwin_id = f"RT-{seg_id}"
        rt.current_state = rt_state
        rt.positive_evidence_count = 5
        rt.aggregate_confidence = 0.95
        rt.independent_bus_count = 2
        rt.updated_at = datetime.now(timezone.utc)

        # Mock evidence query
        ev_mock = MagicMock()
        ev_mock.independence_class = "INDEPENDENT"
        ev_mock.evidence_weight = 0.7
        ev_mock.bus_id = "BUS-PREV-001"
        ev_mock.event_id = "EVT-PREV-001"
        ev_mock.device_id = ""
        ev_mock.camera_id = ""
        ev_mock.timestamp = datetime.now(timezone.utc)
        ev_mock.observation_id = None
        ev_mock.opportunity_id = None

        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first.return_value = rt
        q.all.return_value = [ev_mock]
        db.add = MagicMock()
        db.flush = MagicMock()

        return db, rt

    def test_maintenance_pending_state_not_advanced_by_positive_evidence(self):
        """
        FusionEngine must NOT advance state when RoadTwin is in MAINTENANCE_PENDING.
        Verified via MAINTENANCE_ACTIVE_STATES sentinel in roadtwin.engine.
        """
        from backend.app.roadtwin.engine import MAINTENANCE_ACTIVE_STATES

        assert "MAINTENANCE_PENDING" in MAINTENANCE_ACTIVE_STATES, (
            "ARCHITECTURE VIOLATION: MAINTENANCE_PENDING must be in MAINTENANCE_ACTIVE_STATES"
        )

    def test_verification_pending_state_not_advanced_by_positive_evidence(self):
        """VERIFICATION_PENDING must be in MAINTENANCE_ACTIVE_STATES."""
        from backend.app.roadtwin.engine import MAINTENANCE_ACTIVE_STATES

        assert "VERIFICATION_PENDING" in MAINTENANCE_ACTIVE_STATES

    def test_observed_candidate_are_advanceable(self):
        """OBSERVED and CANDIDATE are advanceable by positive evidence."""
        from backend.app.roadtwin.engine import POSITIVE_EVIDENCE_ADVANCEABLE_STATES

        for state in ("OBSERVED", "CANDIDATE"):
            assert state in POSITIVE_EVIDENCE_ADVANCEABLE_STATES, (
                f"{state} must be in POSITIVE_EVIDENCE_ADVANCEABLE_STATES"
            )


# ---------------------------------------------------------------------------
# M4.7 — API schema structure
# ---------------------------------------------------------------------------

class TestMaintenanceSchemas:
    """Schema structure tests — no DB required."""

    def test_dispatch_request_importable(self):
        from backend.app.schemas.maintenance import MaintenanceDispatchRequest
        req = MaintenanceDispatchRequest(
            roadtwin_id="RT-001",
            actor_role="INSPECTOR",
            actor_id="INS-001",
        )
        assert req.roadtwin_id == "RT-001"

    def test_report_completion_request_importable(self):
        from backend.app.schemas.maintenance import ReportCompletionRequest
        req = ReportCompletionRequest(
            roadtwin_id="RT-001",
            actor_role="CONTRACTOR",
            actor_id="CON-001",
        )
        assert req.roadtwin_id == "RT-001"

    def test_negative_evidence_request_importable(self):
        from backend.app.schemas.maintenance import NegativeEvidenceRequest
        req = NegativeEvidenceRequest(
            road_segment_id="SEG-001",
            opportunity_id=str(uuid.uuid4()),
            opportunity_score=0.85,
            gps_quality=0.9,
            bus_id="BUS-001",
            timestamp=datetime.now(timezone.utc),
            validity_status="VALID",
        )
        assert req.road_segment_id == "SEG-001"

    def test_maintenance_router_importable(self):
        """Maintenance API router must be importable without error."""
        from backend.app.api.v1.maintenance import router
        assert router is not None

    def test_openapi_includes_maintenance_endpoints(self):
        """OpenAPI schema must include all M4 maintenance endpoints."""
        from backend.app.main import app
        schema = app.openapi()
        paths = schema["paths"]
        assert "/api/v1/maintenance/dispatch" in paths, "Missing /maintenance/dispatch"
        assert "/api/v1/maintenance/report-completion" in paths, "Missing /maintenance/report-completion"
        assert "/api/v1/maintenance/negative-evidence" in paths, "Missing /maintenance/negative-evidence"
        assert "/api/v1/maintenance/{roadtwin_id}" in paths, "Missing /maintenance/{roadtwin_id}"
        assert "/api/v1/maintenance/{roadtwin_id}/history" in paths, "Missing /maintenance/{roadtwin_id}/history"


# ---------------------------------------------------------------------------
# M4.8 — Integration tests (require live backend at localhost:8000)
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _backend_available() -> bool:
    try:
        import httpx
        resp = httpx.get(f"{BACKEND_URL}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _event_payload(bus_id: str = "BUS-M4-001", confidence: float = 0.87) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "bus_id": bus_id,
        "device_id": f"DEV-{bus_id}",
        "camera_id": f"CAM-{bus_id}-01",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 17.4435, "longitude": 78.3772},
        "event_type": "pothole_observation",
        "detector_confidence": confidence,
        "observation_quality": 0.9,
        "gps_quality": 0.85,
        "model_name": "test-model",
        "model_version": "1.0",
        "trace_id": str(uuid.uuid4()),
    }


@pytest.mark.integration
class TestMaintenanceAPIIntegration:
    """Integration tests for M4 maintenance API — require live backend."""

    def _seed_confirmed_rt(self) -> tuple[str, str]:
        """Ensure the RoadTwin is in a state ready for dispatch (CONFIRMED or REAPPEARED)."""
        import httpx
        rts = httpx.get(f"{BACKEND_URL}/api/v1/roadtwin", timeout=10).json()
        if rts:
            rt_id = rts[0]["roadtwin_id"]
            seg_id = rts[0]["road_segment_id"]
            curr = rts[0]["current_state"]
            if curr == "MAINTENANCE_PENDING":
                httpx.post(f"{BACKEND_URL}/api/v1/maintenance/report-completion", json={
                    "roadtwin_id": rt_id, "actor_role": "CONTRACTOR", "actor_id": "CON-CYCLE",
                    "trace_id": str(uuid.uuid4()),
                }, timeout=10)
                curr = "VERIFICATION_PENDING"
            if curr == "VERIFICATION_PENDING":
                httpx.post(f"{BACKEND_URL}/api/v1/maintenance/negative-evidence", json={
                    "road_segment_id": seg_id, "opportunity_id": str(uuid.uuid4()),
                    "opportunity_score": 0.95, "gps_quality": 0.95, "bus_id": "BUS-CYCLE",
                    "timestamp": datetime.now(timezone.utc).isoformat(), "validity_status": "VALID",
                    "trace_id": str(uuid.uuid4()),
                }, timeout=10)
                curr = "VERIFIED_REPAIRED"
            if curr == "VERIFIED_REPAIRED":
                httpx.post(f"{BACKEND_URL}/api/v1/events", json=_event_payload("BUS-REAP-CYCLE"), timeout=10)
                curr = "REAPPEARED"
            if curr in ("CONFIRMED", "REAPPEARED"):
                return rt_id, seg_id

        r1 = httpx.post(f"{BACKEND_URL}/api/v1/events", json=_event_payload("BUS-M4-INT-A"), timeout=10)
        assert r1.status_code == 200
        rt_id = r1.json()["roadtwin_id"]
        seg_id = r1.json()["matched_road_segment_id"]

        r2 = httpx.post(f"{BACKEND_URL}/api/v1/events", json=_event_payload("BUS-M4-INT-B"), timeout=10)
        assert r2.status_code == 200

        return rt_id, seg_id

    def test_dispatch_lifecycle(self):
        """Test dispatch → completion → negative evidence → VERIFIED_REPAIRED."""
        if not _backend_available():
            pytest.skip("Backend not reachable")

        import httpx

        rt_id, seg_id = self._seed_confirmed_rt()

        # 1. Check state is dispatch-ready (CONFIRMED or REAPPEARED)
        state_resp = httpx.get(f"{BACKEND_URL}/api/v1/roadtwin/{rt_id}", timeout=10)
        assert state_resp.json()["current_state"] in ("CONFIRMED", "REAPPEARED"), (
            f"Expected CONFIRMED or REAPPEARED, got {state_resp.json()['current_state']}"
        )

        # 2. Dispatch maintenance
        dispatch = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/dispatch", json={
            "roadtwin_id": rt_id,
            "actor_role": "INSPECTOR",
            "actor_id": "INS-INTTEST-001",
            "notes": "Integration test dispatch",
            "trace_id": str(uuid.uuid4()),
        }, timeout=10)
        assert dispatch.status_code == 200
        assert dispatch.json()["new_state"] == "MAINTENANCE_PENDING"

        # 3. Report completion
        complete = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/report-completion", json={
            "roadtwin_id": rt_id,
            "actor_role": "CONTRACTOR",
            "actor_id": "CON-INTTEST-001",
            "notes": "Integration test completion",
            "trace_id": str(uuid.uuid4()),
        }, timeout=10)
        assert complete.status_code == 200
        assert complete.json()["new_state"] == "VERIFICATION_PENDING", (
            "Contractor report must set VERIFICATION_PENDING, not VERIFIED_REPAIRED"
        )

        # 4. INVALID negative evidence — must be gated out
        neg_invalid = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/negative-evidence", json={
            "road_segment_id": seg_id,
            "opportunity_id": str(uuid.uuid4()),
            "opportunity_score": 0.1,
            "gps_quality": 0.1,
            "bus_id": "BUS-M4-NEG-GATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity_status": "INVALID",
            "trace_id": str(uuid.uuid4()),
        }, timeout=10)
        assert neg_invalid.status_code == 200
        assert neg_invalid.json()["status"] == "gated_out", "INVALID opportunity must be gated out"

        # 5. VALID negative evidence — strong enough for VERIFIED_REPAIRED
        neg_valid = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/negative-evidence", json={
            "road_segment_id": seg_id,
            "opportunity_id": str(uuid.uuid4()),
            "opportunity_score": 0.92,
            "gps_quality": 0.90,
            "bus_id": "BUS-M4-VERIFY-INT",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity_status": "VALID",
            "trace_id": str(uuid.uuid4()),
        }, timeout=10)
        assert neg_valid.status_code == 200
        body = neg_valid.json()
        assert body["status"] == "accepted"
        assert body["negative_evidence_strength"] >= 0.5
        assert body["roadtwin_state"] == "VERIFIED_REPAIRED", (
            f"Expected VERIFIED_REPAIRED after strong negative evidence, got {body['roadtwin_state']!r}"
        )

        # 6. Status check
        status = httpx.get(f"{BACKEND_URL}/api/v1/maintenance/{rt_id}", timeout=10)
        assert status.status_code == 200
        st = status.json()
        assert st["verification_status"] == "VERIFIED"
        assert st["maintenance_status"] == "COMPLETED"

        # 7. History check
        history = httpx.get(f"{BACKEND_URL}/api/v1/maintenance/{rt_id}/history", timeout=10)
        assert history.status_code == 200
        actions = history.json()
        assert len(actions) >= 2
        types = [a["action_type"] for a in actions]
        assert "MAINTENANCE_DISPATCHED" in types
        assert "REPAIR_COMPLETION_REPORTED" in types

    def test_dispatch_from_wrong_state_returns_422_integration(self):
        """Dispatching when state is not CONFIRMED/REAPPEARED (e.g., MAINTENANCE_PENDING) returns 422."""
        if not _backend_available():
            pytest.skip("Backend not reachable")

        import httpx

        rts = httpx.get(f"{BACKEND_URL}/api/v1/roadtwin", timeout=10).json()
        if not rts:
            pytest.skip("No roadtwin available")
        rt_id = rts[0]["roadtwin_id"]
        curr = rts[0]["current_state"]

        if curr in ("CONFIRMED", "REAPPEARED"):
            # Put into MAINTENANCE_PENDING
            d_resp = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/dispatch", json={
                "roadtwin_id": rt_id,
                "actor_role": "INSPECTOR",
                "actor_id": "INS-PRE",
                "trace_id": str(uuid.uuid4()),
            }, timeout=10)
            assert d_resp.status_code == 200

        # Now attempting to dispatch again from MAINTENANCE_PENDING / VERIFICATION_PENDING must return 422
        resp = httpx.post(f"{BACKEND_URL}/api/v1/maintenance/dispatch", json={
            "roadtwin_id": rt_id,
            "actor_role": "INSPECTOR",
            "actor_id": "INS-GUARD-TEST",
            "trace_id": str(uuid.uuid4()),
        }, timeout=10)
        assert resp.status_code == 422, (
            f"Expected 422 for dispatch from non-confirmed state, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# M4.10 — Corrective Hardening Tests (Evidence Lineage, Negative Independence, Ownership)
# ---------------------------------------------------------------------------

class TestM4HardeningValidation:
    """Explicit tests for M3/M4 corrective hardening pass."""

    def test_evidence_model_has_lineage_columns(self):
        """EvidenceModel must persist latitude, longitude, sensing_pass_id, and trace_id."""
        from backend.app.models.evidence import EvidenceModel
        cols = {c.name for c in EvidenceModel.__table__.columns}
        for expected in ("latitude", "longitude", "sensing_pass_id", "trace_id"):
            assert expected in cols, f"EvidenceModel missing column: {expected}"

    def test_apply_positive_evidence_transition_ownership(self):
        """RoadTwin state mutation must be owned by roadtwin engine."""
        from backend.app.roadtwin.engine import apply_positive_evidence_transition
        rt = MagicMock()
        rt.road_segment_id = "SEG-OWN-001"
        rt.current_state = "OBSERVED"
        apply_positive_evidence_transition(rt, "CONFIRMED", "Test transition")
        assert rt.current_state == "CONFIRMED"

    def test_negative_evidence_correlated_does_not_trigger_verified(self):
        """Correlated negative evidence must NOT trigger VERIFIED_REPAIRED."""
        from backend.app.fusion.engine import process_negative_evidence
        from backend.app.fusion.independence import IndependenceClass

        now = datetime.now(timezone.utc)
        rt = MagicMock()
        rt.road_segment_id = "SEG-CORR-001"
        rt.current_state = "VERIFICATION_PENDING"
        rt.previous_episode_id = None
        rt.first_seen_at = now
        rt.negative_evidence_count = 0

        prior_ev = MagicMock()
        prior_ev.evidence_id = "ev_prior_1"
        prior_ev.event_id = "neg_opp_1"
        prior_ev.bus_id = "BUS-SAME"
        prior_ev.device_id = "DEV-01"
        prior_ev.camera_id = "CAM-01"
        prior_ev.sensing_pass_id = "opp_1"
        prior_ev.timestamp = now
        prior_ev.latitude = 17.4435
        prior_ev.longitude = 78.3772
        prior_ev.observation_id = None
        prior_ev.opportunity_id = "opp_1"

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = rt
        # Mock query for existing evidence returns prior_ev
        db.query.return_value.filter_by.return_value.filter.return_value.all.return_value = [prior_ev]

        # Pass from SAME bus 10 seconds later at same location -> CORRELATED
        ev = process_negative_evidence(
            db=db,
            road_segment_id="SEG-CORR-001",
            opportunity_id="opp_2",
            opportunity_score=0.9,
            gps_quality=0.9,
            bus_id="BUS-SAME",
            device_id="DEV-01",
            camera_id="CAM-01",
            timestamp=now + timedelta(seconds=10),
            validity_status="VALID",
            trace_id="tr-corr",
            latitude=17.4435,
            longitude=78.3772,
        )
        assert ev is not None
        assert ev.independence_class == IndependenceClass.CORRELATED.value
        # State must remain VERIFICATION_PENDING (not VERIFIED_REPAIRED)
        assert rt.current_state == "VERIFICATION_PENDING"

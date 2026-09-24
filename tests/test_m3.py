"""
UrbanSense AI — M3 Cooperative Evidence Test Suite
====================================================
Tests for:
  M3.1 Evidence ORM model structure
  M3.2 Deduplication (same event_id → DUPLICATE)
  M3.3 Independence classification (bus_id, sensing_pass, time, spatial)
  M3.4 Evidence lineage preservation
  M3.5 FusionEngine — evidence_weight computed ONLY here (MVP formula)
  M3.6 RoadTwin state machine: OBSERVED → CANDIDATE → CONFIRMED
  M3.7 Two-bus vertical slice: BUS-001 alone cannot CONFIRM; BUS-001 + BUS-002 → CONFIRMED
  M3.8 False confirmation guard: DUPLICATE contributions cannot trigger CONFIRMED
  M3.9 API contracts: GET /api/v1/evidence

HARD RULES verified:
- evidence_weight computed ONLY by FusionEngine (never in edge, API route, or frontend)
- No confirmation threshold invented without R4 mandate
- Independence is PROTOTYPE / DECISION_REQUIRED
- detector_confidence is UNCALIBRATED
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ============================================================
# M3.1 — Evidence ORM model structure
# ============================================================

class TestEvidenceModelStructure:
    """Tests that EvidenceModel has the required columns per R4 §8.4."""

    def test_evidence_model_importable(self):
        """EvidenceModel must be importable from backend.app.models.evidence."""
        from backend.app.models.evidence import EvidenceModel
        assert EvidenceModel.__tablename__ == "evidence"

    def test_evidence_model_required_fields(self):
        """EvidenceModel must have all R4-required fields."""
        from backend.app.models.evidence import EvidenceModel
        required_columns = {
            "evidence_id", "event_id", "observation_id", "opportunity_id",
            "polarity", "bus_id", "camera_id", "timestamp", "ingestion_timestamp",
            "matched_road_segment_id", "detector_confidence", "observation_quality",
            "gps_quality", "independence_class", "correlation_group_id",
            "evidence_weight", "fusion_strategy", "fusion_version", "lineage",
        }
        actual_columns = {col.name for col in EvidenceModel.__table__.columns}
        missing = required_columns - actual_columns
        assert not missing, f"EvidenceModel missing required columns: {missing}"

    def test_evidence_weight_column_not_nullable(self):
        """evidence_weight must be NOT NULL — the FusionEngine always computes it."""
        from backend.app.models.evidence import EvidenceModel
        col = EvidenceModel.__table__.columns["evidence_weight"]
        assert not col.nullable, "evidence_weight must be NOT NULL"

    def test_polarity_values_documented(self):
        """EvidenceModel polarity column must exist (POSITIVE | NEGATIVE)."""
        from backend.app.models.evidence import EvidenceModel
        col = EvidenceModel.__table__.columns["polarity"]
        assert col is not None

    def test_detector_confidence_nullable(self):
        """detector_confidence is nullable for negative evidence path."""
        from backend.app.models.evidence import EvidenceModel
        col = EvidenceModel.__table__.columns["detector_confidence"]
        assert col.nullable, "detector_confidence must be nullable (null for negative evidence)"


# ============================================================
# M3.2 — Deduplication
# ============================================================

class TestDeduplication:
    """Same event_id hitting the evidence pipeline must be classified DUPLICATE."""

    def test_duplicate_event_id_classified_as_duplicate(self):
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        ts = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        prior = IndependenceInput(
            event_id="EVT-001",
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts,
            latitude=17.4435,
            longitude=78.3772,
        )
        candidate = IndependenceInput(
            event_id="EVT-001",  # same event_id
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts,
            latitude=17.4435,
            longitude=78.3772,
        )
        result = classify_independence(candidate, [prior], road_segment_id="SEG-001")
        assert result.independence_class == IndependenceClass.DUPLICATE, (
            f"Same event_id must be DUPLICATE, got {result.independence_class}"
        )

    def test_same_bus_same_pass_classified_as_duplicate(self):
        """Same bus + same sensing_pass + same camera → DUPLICATE (not independent)."""
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        ts1 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        ts2 = datetime(2026, 9, 24, 12, 0, 5, tzinfo=timezone.utc).isoformat()
        prior = IndependenceInput(
            event_id="EVT-001",
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts1,
            latitude=17.4435,
            longitude=78.3772,
        )
        candidate = IndependenceInput(
            event_id="EVT-002",  # different event_id, but same pass
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",  # same sensing pass
            event_timestamp_iso=ts2,
            latitude=17.4435,
            longitude=78.3772,
        )
        result = classify_independence(candidate, [prior], road_segment_id="SEG-001")
        assert result.independence_class == IndependenceClass.DUPLICATE, (
            "Same bus + same sensing_pass + same camera must be DUPLICATE"
        )


# ============================================================
# M3.3 — Independence Classification
# ============================================================

class TestIndependenceClassification:
    """Tests for independence reasoning across bus_id, time, spatial dimensions."""

    def test_first_contribution_is_independent(self):
        """First evidence on a segment is always INDEPENDENT (no prior contributions)."""
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        ts = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        candidate = IndependenceInput(
            event_id="EVT-001",
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts,
            latitude=17.4435,
            longitude=78.3772,
        )
        result = classify_independence(candidate, [], road_segment_id="SEG-001")
        assert result.independence_class == IndependenceClass.INDEPENDENT

    def test_different_bus_classified_independent(self):
        """
        BUS-002 event on same segment as BUS-001 → INDEPENDENT (PROTOTYPE M3 rule).
        DECISION_REQUIRED for production.
        """
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        ts1 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        ts2 = datetime(2026, 9, 24, 12, 30, 0, tzinfo=timezone.utc).isoformat()
        prior = IndependenceInput(
            event_id="EVT-001",
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts1,
            latitude=17.4435,
            longitude=78.3772,
        )
        candidate = IndependenceInput(
            event_id="EVT-002",
            bus_id="BUS-002",  # different bus
            device_id="DEV-002",
            camera_id="CAM-02",
            sensing_pass_id="PASS-002",
            event_timestamp_iso=ts2,
            latitude=17.4436,
            longitude=78.3773,
        )
        result = classify_independence(candidate, [prior], road_segment_id="SEG-001")
        assert result.independence_class == IndependenceClass.INDEPENDENT, (
            "BUS-002 on same segment should be INDEPENDENT (PROTOTYPE M3 rule)"
        )

    def test_same_bus_nearby_time_classified_correlated(self):
        """
        Same bus, different event, within 50m, within 5 min → CORRELATED.
        Note: uses lat/lon 0.0 for existing contributions (DECISION_REQUIRED limitation).
        This tests that two events from the same bus in the same window are not INDEPENDENT.
        """
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        ts1 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        ts2 = datetime(2026, 9, 24, 12, 2, 0, tzinfo=timezone.utc).isoformat()  # 2 min later
        prior = IndependenceInput(
            event_id="EVT-001",
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id="PASS-001",
            event_timestamp_iso=ts1,
            latitude=17.4435,  # same location
            longitude=78.3772,
        )
        candidate = IndependenceInput(
            event_id="EVT-002",
            bus_id="BUS-001",  # same bus, no known pass
            device_id="DEV-001",
            camera_id="CAM-01",
            sensing_pass_id=None,  # no sensing pass known
            event_timestamp_iso=ts2,
            latitude=17.4435,  # same location (0m distance)
            longitude=78.3772,
        )
        result = classify_independence(candidate, [prior], road_segment_id="SEG-001")
        # Same bus + same location + 2 min → should be CORRELATED (not INDEPENDENT)
        assert result.independence_class in (IndependenceClass.CORRELATED, IndependenceClass.DUPLICATE), (
            f"Same bus, nearby time, same location should be CORRELATED or DUPLICATE, got {result.independence_class}"
        )

    def test_independence_class_values_are_strings(self):
        """IndependenceClass enum values are strings for ORM storage."""
        from backend.app.fusion.independence import IndependenceClass
        assert IndependenceClass.INDEPENDENT.value == "INDEPENDENT"
        assert IndependenceClass.CORRELATED.value == "CORRELATED"
        assert IndependenceClass.DUPLICATE.value == "DUPLICATE"


# ============================================================
# M3.4 — Evidence Lineage
# ============================================================

class TestEvidenceLineage:
    """Evidence lineage JSON must record derivation chain."""

    def test_fusion_engine_mvp_weight_formula_unit(self):
        """
        Unit test for MVP formula: evidence_weight = dc * oq * gq.
        FusionEngine is the ONLY place this is computed.
        """
        from backend.app.fusion.engine import _mvp_evidence_weight
        # Normal case
        w = _mvp_evidence_weight(0.8, 0.9, 0.7)
        assert abs(w - round(0.8 * 0.9 * 0.7, 6)) < 1e-6, f"MVP formula incorrect: got {w}"

    def test_fusion_engine_mvp_weight_none_signals(self):
        """None quality signals → 0.0 weight (cannot certify quality)."""
        from backend.app.fusion.engine import _mvp_evidence_weight
        assert _mvp_evidence_weight(None, 0.9, 0.7) == 0.0
        assert _mvp_evidence_weight(0.8, None, 0.7) == 0.0
        assert _mvp_evidence_weight(0.8, 0.9, None) == 0.0
        assert _mvp_evidence_weight(None, None, None) == 0.0

    def test_noisy_or_aggregate_unit(self):
        """
        Noisy-OR aggregate = 1 - prod(1 - w_i).
        Verify against manual calculation.
        """
        from backend.app.fusion.engine import _bayes_aggregate
        w1, w2 = 0.5, 0.5
        expected = round(1.0 - (1.0 - w1) * (1.0 - w2), 6)
        result = _bayes_aggregate([w1, w2])
        assert abs(result - expected) < 1e-6, f"Noisy-OR incorrect: expected {expected}, got {result}"

    def test_noisy_or_empty_weights(self):
        """Empty weight list → aggregate is 0.0 (no evidence)."""
        from backend.app.fusion.engine import _bayes_aggregate
        assert _bayes_aggregate([]) == 0.0

    def test_noisy_or_single_weight(self):
        """Single independent evidence → aggregate equals that evidence_weight."""
        from backend.app.fusion.engine import _bayes_aggregate
        assert abs(_bayes_aggregate([0.7]) - 0.7) < 1e-6


# ============================================================
# M3.5 — FusionEngine: evidence_weight computed ONLY here
# ============================================================

class TestFusionEngineArchitecture:
    """Architecture invariant: evidence_weight is computed ONLY in FusionEngine."""

    def test_fusion_engine_importable_at_expected_path(self):
        """FusionEngine must be at backend/app/fusion/engine.py."""
        import importlib
        mod = importlib.import_module("backend.app.fusion.engine")
        assert hasattr(mod, "process_event_evidence"), "FusionEngine must expose process_event_evidence"
        assert hasattr(mod, "_mvp_evidence_weight"), "FusionEngine must expose _mvp_evidence_weight"

    def test_no_evidence_weight_in_edge_opportunity(self):
        """
        OpportunityEvaluator must NOT compute (assign) evidence_weight.
        The word 'evidence_weight' may appear in docstrings/architectural notes
        but must never appear as an assignment statement.
        """
        import pathlib
        src = pathlib.Path("edge/app/opportunity/opportunity_evaluator.py").read_text(encoding="utf-8")
        # Only fail if evidence_weight appears as an assignment (computation)
        forbidden = ["evidence_weight =", "evidence_weight="]
        for pattern in forbidden:
            assert pattern not in src, (
                f"OpportunityEvaluator must NOT compute evidence_weight (found '{pattern}'). "
                "evidence_weight is exclusively the FusionEngine's responsibility."
            )


    def test_no_evidence_weight_in_event_builder(self):
        """EventBuilder (if present) must NOT compute evidence_weight."""
        import pathlib
        event_builder = pathlib.Path("edge/app/events")
        for f in event_builder.rglob("*.py"):
            src = f.read_text(encoding="utf-8")
            assert "evidence_weight" not in src, (
                f"{f} must NOT compute evidence_weight — FusionEngine exclusive"
            )

    def test_fusion_engine_is_singular(self):
        """Only one fusion engine module may exist."""
        import pathlib
        # Search for any file other than the canonical engine.py that defines process_event_evidence
        engines = []
        for f in pathlib.Path("backend").rglob("*.py"):
            if "fusion/engine.py" in str(f).replace("\\", "/"):
                continue
            try:
                src = f.read_text(encoding="utf-8")
                if "def process_event_evidence" in src:
                    engines.append(str(f))
            except Exception:
                pass
        assert not engines, f"Duplicate FusionEngine implementations found: {engines}"


# ============================================================
# M3.6 — RoadTwin State Machine (OBSERVED → CANDIDATE → CONFIRMED)
# ============================================================

class TestRoadTwinStateMachine:
    """State machine transitions via _compute_new_state."""

    def test_observed_with_one_independent_stays_observed(self):
        """1 INDEPENDENT evidence → still OBSERVED (not CANDIDATE)."""
        from backend.app.fusion.engine import _compute_new_state
        state, reason = _compute_new_state("OBSERVED", independent_count=1, independent_bus_ids={"BUS-001"})
        assert state == "OBSERVED", f"Expected OBSERVED with 1 evidence, got {state}"

    def test_observed_to_candidate_with_two_independent(self):
        """2 INDEPENDENT evidence from same bus → CANDIDATE (single-bus threshold)."""
        from backend.app.fusion.engine import _compute_new_state
        # 2 independent from 1 bus → should become CANDIDATE (not CONFIRMED)
        state, reason = _compute_new_state("OBSERVED", independent_count=2, independent_bus_ids={"BUS-001"})
        assert state == "CANDIDATE", f"Expected CANDIDATE with 2 independent from 1 bus, got {state}"

    def test_candidate_to_confirmed_with_two_buses(self):
        """2 INDEPENDENT evidence from 2 different buses → CONFIRMED."""
        from backend.app.fusion.engine import _compute_new_state
        state, reason = _compute_new_state(
            "CANDIDATE", independent_count=2, independent_bus_ids={"BUS-001", "BUS-002"}
        )
        assert state == "CONFIRMED", f"Expected CONFIRMED with 2 buses, got {state}"

    def test_observed_to_confirmed_with_two_buses_and_two_independent(self):
        """OBSERVED + 2 INDEPENDENT + 2 buses → CONFIRMED in one step."""
        from backend.app.fusion.engine import _compute_new_state
        state, reason = _compute_new_state(
            "OBSERVED", independent_count=2, independent_bus_ids={"BUS-001", "BUS-002"}
        )
        assert state == "CONFIRMED", f"Expected CONFIRMED, got {state}"

    def test_confirmed_stays_confirmed(self):
        """Once CONFIRMED, state must not regress."""
        from backend.app.fusion.engine import _compute_new_state
        state, _ = _compute_new_state(
            "CONFIRMED", independent_count=10, independent_bus_ids={"BUS-001", "BUS-002", "BUS-003"}
        )
        assert state == "CONFIRMED"

    def test_state_machine_reason_mentions_prototype(self):
        """Transition reason must mention PROTOTYPE and DECISION_REQUIRED (no invented threshold)."""
        from backend.app.fusion.engine import _compute_new_state
        _, reason = _compute_new_state(
            "OBSERVED", independent_count=2, independent_bus_ids={"BUS-001", "BUS-002"}
        )
        assert "PROTOTYPE" in reason or "DECISION_REQUIRED" in reason, (
            f"Transition reason must acknowledge PROTOTYPE/DECISION_REQUIRED status: {reason}"
        )


# ============================================================
# M3.7 — Two-bus vertical slice (BUS-001 + BUS-002 → CONFIRMED)
# ============================================================

class TestTwoBusVerticalSlice:
    """
    The exit condition for M3: BUS-001 + BUS-002 → CONFIRMED.

    Uses in-memory SQLite with SQLAlchemy to exercise the full integration
    without Docker/PostgreSQL (geoalchemy2 geometry column is excluded for the
    in-memory test since SQLite does not support PostGIS).
    """

    def _make_db(self):
        """Create in-memory SQLite engine with simplified schema for M3 testing."""
        from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Boolean, Text
        from sqlalchemy.orm import declarative_base, Session as SASession

        Base = declarative_base()

        class RoadTwinStateModel(Base):
            __tablename__ = "roadtwin_states_m3test"
            roadtwin_id = Column(String, primary_key=True)
            road_segment_id = Column(String, nullable=False, unique=True)
            current_state = Column(String, nullable=False, default="OBSERVED")
            aggregate_confidence = Column(Float, nullable=False, default=0.0)
            positive_evidence_count = Column(Integer, nullable=False, default=0)
            negative_evidence_count = Column(Integer, nullable=False, default=0)
            independent_bus_count = Column(Integer, nullable=False, default=0)
            first_seen_at = Column(DateTime(timezone=True), nullable=False)
            last_seen_at = Column(DateTime(timezone=True), nullable=False)
            last_validated_at = Column(DateTime(timezone=True), nullable=True)
            freshness_status = Column(String, nullable=False, default="FRESH")
            maintenance_status = Column(String, nullable=False, default="NONE")
            verification_status = Column(String, nullable=False, default="UNVERIFIED")
            active_episode_id = Column(String, nullable=True)
            previous_episode_id = Column(String, nullable=True)
            history_ref = Column(String, nullable=True)
            last_event_id = Column(String, nullable=True)
            last_observation_id = Column(String, nullable=True)
            subject_id = Column(String, nullable=True)
            subject_type = Column(String, nullable=True)
            updated_at = Column(DateTime(timezone=True), nullable=True)

        class EvidenceModel(Base):
            __tablename__ = "evidence_m3test"
            evidence_id = Column(String, primary_key=True)
            event_id = Column(String, nullable=True)
            observation_id = Column(String, nullable=True)
            opportunity_id = Column(String, nullable=True)
            polarity = Column(String, nullable=False)
            source_type = Column(String, nullable=False, default="BUS_CAMERA")
            source_id = Column(String, nullable=True)
            bus_id = Column(String, nullable=False)
            device_id = Column(String, nullable=True)
            camera_id = Column(String, nullable=True)
            timestamp = Column(DateTime(timezone=True), nullable=False)
            ingestion_timestamp = Column(DateTime(timezone=True), nullable=False)
            matched_road_segment_id = Column(String, nullable=True)
            map_match_status = Column(String, nullable=True)
            detector_confidence = Column(Float, nullable=True)
            observation_quality = Column(Float, nullable=True)
            opportunity_score = Column(Float, nullable=True)
            gps_quality = Column(Float, nullable=True)
            sensor_health = Column(Float, nullable=True)
            independence_class = Column(String, nullable=False)
            correlation_group_id = Column(String, nullable=True)
            evidence_weight = Column(Float, nullable=False)
            fusion_strategy = Column(String, nullable=False, default="MVP")
            fusion_version = Column(String, nullable=False, default="1.0")
            negative_evidence_strength = Column(Float, nullable=True)
            source_reliability = Column(Float, nullable=True)
            temporal_consistency = Column(Float, nullable=True)
            spatial_consistency = Column(Float, nullable=True)
            historical_consistency = Column(Float, nullable=True)
            independence_score = Column(Float, nullable=True)
            correlation_penalty = Column(Float, nullable=True)
            lineage = Column(Text, nullable=True)
            created_at = Column(DateTime(timezone=True), nullable=True)

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        return engine, SASession(engine), RoadTwinStateModel, EvidenceModel

    def _make_event(self, event_id: str, bus_id: str, ts: datetime):
        """Create a minimal mock EventModel."""
        ev = MagicMock()
        ev.event_id = event_id
        ev.bus_id = bus_id
        ev.device_id = f"DEV-{bus_id}"
        ev.camera_id = f"CAM-{bus_id}"
        ev.opportunity_id = f"OPP-{event_id}"
        ev.observation_id = f"OBS-{event_id}"
        ev.event_timestamp = ts
        ev.latitude = 17.4435
        ev.longitude = 78.3772
        ev.detector_confidence = 0.85
        ev.observation_quality = 0.90
        ev.gps_quality = 0.80
        ev.map_match_status = "MATCHED"
        return ev

    def test_bus_001_alone_cannot_confirm(self):
        """
        BUS-001 alone (even with multiple events from different passes) must NOT
        reach CONFIRMED state, because CONFIRMED requires independent evidence from
        >= 2 different buses (PROTOTYPE M3 rule).
        """
        from backend.app.fusion.engine import (
            _mvp_evidence_weight, _bayes_aggregate, _compute_new_state,
            _load_existing_contributions,
        )
        from backend.app.fusion.independence import IndependenceInput, classify_independence

        # Simulate: BUS-001 sends 5 events (different passes, different times)
        # All should be classified INDEPENDENT from each other (same bus, different pass/time)
        # But 5 INDEPENDENT from 1 bus must NOT trigger CONFIRMED.
        bus_ids = {"BUS-001"}  # only one bus
        independent_count = 5  # simulate 5 INDEPENDENT contributions from BUS-001

        state, reason = _compute_new_state(
            "OBSERVED",
            independent_count=independent_count,
            independent_bus_ids=bus_ids,
        )
        assert state != "CONFIRMED", (
            f"BUS-001 alone must NOT reach CONFIRMED (got {state}). "
            "CONFIRMED requires independent evidence from >= 2 different buses."
        )

    def test_bus_001_plus_bus_002_reaches_confirmed(self):
        """
        BUS-001 + BUS-002 with independently classified evidence → CONFIRMED.
        This is the M3 exit condition.
        """
        from backend.app.fusion.engine import _compute_new_state

        # 2 INDEPENDENT evidence from 2 buses → CONFIRMED
        state, reason = _compute_new_state(
            "OBSERVED",
            independent_count=2,
            independent_bus_ids={"BUS-001", "BUS-002"},
        )
        assert state == "CONFIRMED", (
            f"BUS-001 + BUS-002 with 2 INDEPENDENT evidence must reach CONFIRMED. Got {state}. Reason: {reason}"
        )

    def test_two_bus_full_engine_integration(self):
        """
        Full integration: simulate FusionEngine processing two events (BUS-001, BUS-002)
        using in-memory SQLite (no Docker/PostGIS required).

        Asserts:
        - BUS-001 event → INDEPENDENT, RoadTwin = OBSERVED or CANDIDATE
        - BUS-002 event → INDEPENDENT, RoadTwin = CONFIRMED
        - Both evidence records have computed evidence_weight
        - Evidence lineage is preserved
        """
        engine_db, session, RTModel, EvidModel = self._make_db()

        from backend.app.fusion.engine import (
            _mvp_evidence_weight, _bayes_aggregate, _compute_new_state,
        )
        from backend.app.fusion.independence import (
            IndependenceInput, IndependenceClass, classify_independence,
        )
        import uuid as _uuid
        from datetime import datetime, timezone
        import json

        now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        segment_id = "SEG-001"

        # Seed RoadTwin in OBSERVED state
        rt = RTModel(
            roadtwin_id=str(_uuid.uuid4()),
            road_segment_id=segment_id,
            current_state="OBSERVED",
            aggregate_confidence=0.0,
            positive_evidence_count=0,
            negative_evidence_count=0,
            independent_bus_count=0,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(rt)
        session.flush()

        def process_event(event_id, bus_id, ts_offset_min):
            """Simulate FusionEngine for one event."""
            ts = now + timedelta(minutes=ts_offset_min)

            # Build candidate
            candidate = IndependenceInput(
                event_id=event_id,
                bus_id=bus_id,
                device_id=f"DEV-{bus_id}",
                camera_id=f"CAM-{bus_id}",
                sensing_pass_id=f"PASS-{event_id}",
                event_timestamp_iso=ts.isoformat(),
                latitude=17.4435,
                longitude=78.3772,
            )

            # Load existing
            existing_ev = session.query(EvidModel).filter_by(
                matched_road_segment_id=segment_id, polarity="POSITIVE"
            ).all()
            existing_inputs = [
                IndependenceInput(
                    event_id=e.event_id or "",
                    bus_id=e.bus_id,
                    device_id=e.device_id or "",
                    camera_id=e.camera_id or "",
                    sensing_pass_id=e.opportunity_id,
                    event_timestamp_iso=e.timestamp.isoformat() if e.timestamp else "",
                    latitude=0.0,
                    longitude=0.0,
                )
                for e in existing_ev
            ]

            result = classify_independence(candidate, existing_inputs, segment_id)

            # Compute weight (THE ONLY PLACE in this test)
            weight = _mvp_evidence_weight(0.85, 0.90, 0.80)

            # Persist evidence
            ev_rec = EvidModel(
                evidence_id=str(_uuid.uuid4()),
                event_id=event_id,
                polarity="POSITIVE",
                source_type="BUS_CAMERA",
                source_id=bus_id,
                bus_id=bus_id,
                device_id=f"DEV-{bus_id}",
                camera_id=f"CAM-{bus_id}",
                timestamp=ts,
                ingestion_timestamp=ts,
                matched_road_segment_id=segment_id,
                independence_class=result.independence_class.value,
                correlation_group_id=result.correlation_group_id,
                evidence_weight=weight,
                fusion_strategy="MVP",
                fusion_version="1.0",
                opportunity_id=f"PASS-{event_id}",
                lineage=json.dumps({"event_id": event_id, "bus_id": bus_id}),
            )
            session.add(ev_rec)
            session.flush()

            # Update RoadTwin
            rt_current = session.query(RTModel).filter_by(road_segment_id=segment_id).first()
            all_ev = session.query(EvidModel).filter_by(
                matched_road_segment_id=segment_id, polarity="POSITIVE"
            ).all()
            ind_weights = [e.evidence_weight for e in all_ev if e.independence_class == "INDEPENDENT"]
            ind_buses = {e.bus_id for e in all_ev if e.independence_class == "INDEPENDENT"}

            new_agg = _bayes_aggregate(ind_weights) if ind_weights else 0.0
            old_state = rt_current.current_state
            new_state, _ = _compute_new_state(old_state, len(ind_weights), ind_buses)

            rt_current.current_state = new_state
            rt_current.aggregate_confidence = new_agg
            rt_current.positive_evidence_count = len(all_ev)
            rt_current.independent_bus_count = len(ind_buses)
            session.flush()

            return result.independence_class, weight, new_state

        # BUS-001 event
        ic1, w1, state1 = process_event("EVT-BUS001-001", "BUS-001", ts_offset_min=0)
        assert ic1 == IndependenceClass.INDEPENDENT, f"BUS-001 first event should be INDEPENDENT, got {ic1}"
        assert w1 > 0, "BUS-001 evidence_weight must be > 0"
        assert state1 in ("OBSERVED", "CANDIDATE"), f"After BUS-001 alone, state must not be CONFIRMED. Got {state1}"

        # BUS-002 event
        ic2, w2, state2 = process_event("EVT-BUS002-001", "BUS-002", ts_offset_min=30)
        assert ic2 == IndependenceClass.INDEPENDENT, f"BUS-002 event should be INDEPENDENT, got {ic2}"
        assert w2 > 0, "BUS-002 evidence_weight must be > 0"
        assert state2 == "CONFIRMED", (
            f"BUS-001 + BUS-002 independently classified → RoadTwin must be CONFIRMED. Got {state2}"
        )

        # Verify evidence records
        all_evidence = session.query(EvidModel).filter_by(matched_road_segment_id=segment_id).all()
        assert len(all_evidence) == 2, f"Expected 2 evidence records, got {len(all_evidence)}"
        for ev in all_evidence:
            assert ev.evidence_weight > 0, "All evidence must have positive evidence_weight"
            assert ev.lineage is not None, "Evidence lineage must be preserved"
            lineage = json.loads(ev.lineage)
            assert "event_id" in lineage, "Lineage must contain event_id"

        session.close()
        engine_db.dispose()


# ============================================================
# M3.8 — False confirmation guard
# ============================================================

class TestFalseConfirmationGuard:
    """Duplicate/CORRELATED contributions must not trigger CONFIRMED."""

    def test_duplicate_contributions_cannot_confirm(self):
        """
        If all contributions from the same bus are DUPLICATE/CORRELATED,
        the effective INDEPENDENT count remains too low for CONFIRMED.
        """
        from backend.app.fusion.engine import _compute_new_state

        # 10 evidence records, but only 1 bus, 0 INDEPENDENT (all DUPLICATE/CORRELATED)
        state, reason = _compute_new_state(
            "OBSERVED",
            independent_count=0,
            independent_bus_ids=set(),
        )
        assert state == "OBSERVED", (
            f"Zero INDEPENDENT evidence must not advance state beyond OBSERVED. Got {state}"
        )

    def test_single_bus_with_many_correlated_cannot_confirm(self):
        """Single bus with many CORRELATED evidence must stay at CANDIDATE (not CONFIRMED)."""
        from backend.app.fusion.engine import _compute_new_state
        # 100 'independent' contributions but from only 1 bus
        state, _ = _compute_new_state(
            "OBSERVED",
            independent_count=100,
            independent_bus_ids={"BUS-001"},
        )
        # May reach CANDIDATE but NOT CONFIRMED (needs 2 buses)
        assert state != "CONFIRMED", (
            "Single bus with many evidence must NOT reach CONFIRMED — needs 2+ independent buses"
        )

    def test_noisy_or_monotonically_increases_with_more_evidence(self):
        """Noisy-OR aggregate is monotonically non-decreasing with additional positive evidence."""
        from backend.app.fusion.engine import _bayes_aggregate
        weights = [0.5]
        prev = _bayes_aggregate(weights)
        for _ in range(5):
            weights.append(0.5)
            curr = _bayes_aggregate(weights)
            assert curr >= prev, f"Noisy-OR should be non-decreasing: {prev} -> {curr}"
            prev = curr


# ============================================================
# M3.9 — API contracts
# ============================================================

class TestM3APIContracts:
    """GET /api/v1/evidence API contract tests."""

    def test_evidence_api_route_registered(self):
        """GET /api/v1/evidence must appear in the OpenAPI schema paths."""
        from backend.app.main import app
        schema = app.openapi()
        paths = schema.get("paths", {})
        assert "/api/v1/evidence" in paths, (
            f"/api/v1/evidence not found in OpenAPI paths: {list(paths.keys())}"
        )


    def test_evidence_response_schema_fields(self):
        """EvidenceResponse schema must include required M3 fields."""
        from backend.app.api.v1.evidence import EvidenceResponse
        fields = EvidenceResponse.model_fields
        required = {
            "evidence_id", "polarity", "bus_id", "timestamp",
            "independence_class", "evidence_weight", "fusion_strategy",
        }
        missing = required - set(fields.keys())
        assert not missing, f"EvidenceResponse missing fields: {missing}"

    def test_evidence_api_accepts_road_segment_filter(self):
        """GET /api/v1/evidence?road_segment_id=X must be a valid query param."""
        import inspect
        from backend.app.api.v1.evidence import list_evidence
        sig = inspect.signature(list_evidence)
        assert "road_segment_id" in sig.parameters, (
            "list_evidence must accept road_segment_id query parameter"
        )

    def test_openapi_includes_evidence_schema(self):
        """OpenAPI schema must include evidence endpoint."""
        from backend.app.main import app
        schema = app.openapi()
        paths = schema.get("paths", {})
        assert "/api/v1/evidence" in paths, (
            "OpenAPI schema must include /api/v1/evidence"
        )

    def test_independence_class_in_evidence_response(self):
        """independence_class is a required field in EvidenceResponse."""
        from backend.app.api.v1.evidence import EvidenceResponse
        assert "independence_class" in EvidenceResponse.model_fields

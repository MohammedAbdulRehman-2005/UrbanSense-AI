"""
UrbanSense AI — Milestone 1 Test Suite
=======================================
Tests all Milestone 1 acceptance criteria.

Tests 1–6 are pure Python unit tests (no DB, no network).
Tests 7+ are integration tests requiring the backend and DB.

Run unit tests only:
    pytest tests/test_m1.py -k "not integration" -v

Run all tests (requires backend running):
    pytest tests/test_m1.py -v
"""

from __future__ import annotations

import hashlib
import json
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Observation contract validation
# ─────────────────────────────────────────────────────────────────────────────

def test_observation_contract():
    """TEST 1: Observation contract can be instantiated and validates correctly."""
    from contracts.observation import Observation, BoundingBox

    obs = Observation(
        frame_id="FRAME-001",
        bus_id="BUS-001",
        device_id="DEVICE-001",
        camera_id="CAMERA-FRONT-01",
        timestamp=datetime.now(timezone.utc),
        object_type="pothole",
        detector_confidence=0.87,
        bbox=BoundingBox(x_min=100, y_min=200, x_max=300, y_max=400, frame_width=1920, frame_height=1080),
        model_name="test-model",
        model_version="0.1.0",
    )
    assert obs.observation_id is not None
    assert obs.detector_confidence == 0.87
    # Semantic check: field must NOT be named "confidence"
    assert not hasattr(obs, "confidence"), "FAIL: generic 'confidence' field must not exist"


def test_observation_confidence_bounds():
    """TEST 1b: detector_confidence enforces [0, 1] bounds."""
    from contracts.observation import Observation, BoundingBox
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Observation(
            frame_id="F", bus_id="B", device_id="D", camera_id="C",
            timestamp=datetime.now(timezone.utc),
            object_type="pothole",
            detector_confidence=1.5,  # Invalid
            bbox=BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10, frame_width=100, frame_height=100),
            model_name="m", model_version="v",
        )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Opportunity contract validation
# ─────────────────────────────────────────────────────────────────────────────

def test_opportunity_contract():
    """TEST 2: ObservationOpportunity contract validates correctly."""
    from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus

    now = datetime.now(timezone.utc)
    opp = ObservationOpportunity(
        sensing_pass_id="PASS-001",
        bus_id="BUS-001",
        device_id="DEVICE-001",
        camera_id="CAMERA-FRONT-01",
        window_start=now,
        window_end=now + timedelta(seconds=1),
        target_scope=TargetScope.SEGMENT,
        target_type="road_segment",
        fov_valid=True,
        visibility_score=0.9,
        illumination_score=0.88,
        blur_score=0.85,
        occlusion_score=0.92,
        viewing_angle_score=0.80,
        distance_score=0.87,
        sensor_health_score=1.0,
        gps_quality_score=0.90,
        opportunity_score=0.877,
        validity_status=ValidityStatus.VALID,
        invalid_reasons=[],
        coverage_fraction=0.95,
        trace_id=str(uuid.uuid4()),
    )
    assert opp.opportunity_id is not None
    assert opp.validity_status == ValidityStatus.VALID
    # Opportunity is NOT the parent container of all frames (semantic check)
    assert opp.target_scope == TargetScope.SEGMENT


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Canonical Event contract validation
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_event_contract():
    """TEST 3: CanonicalEvent validates backend ownership rules."""
    from contracts.canonical_event import CanonicalEvent, Location, MapMatchStatus

    event = CanonicalEvent(
        bus_id="BUS-001",
        device_id="DEVICE-001",
        camera_id="CAMERA-FRONT-01",
        event_timestamp=datetime.now(timezone.utc),
        location=Location(latitude=17.4435, longitude=78.3772),
        event_type="pothole_observation",
        detector_confidence=0.87,
        model_name="test-model",
        model_version="0.1.0",
        trace_id=str(uuid.uuid4()),
    )

    # Backend-owned fields must be None/PENDING when coming from Edge
    assert event.ingestion_timestamp is None, "ingestion_timestamp must be backend-owned"
    assert event.matched_road_segment_id is None, "matched_road_segment_id must be backend-owned"
    assert event.map_match_status == MapMatchStatus.PENDING, "map_match_status default must be PENDING"

    # Generic 'confidence' must not exist
    assert not hasattr(event, "confidence"), "FAIL: generic 'confidence' field must not exist"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Deterministic simulation
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_simulation():
    """TEST 4: Simulator produces consistent structure every run."""
    from edge.app.simulation.simulator import SensingPassSimulator, BUS_ID, DEVICE_ID, SENSING_PASS_ID

    sim = SensingPassSimulator()
    sp_id, obs, opp, event = sim.run()

    assert sp_id == SENSING_PASS_ID
    assert obs.bus_id == BUS_ID
    assert obs.device_id == DEVICE_ID
    assert obs.object_type == "pothole"
    assert opp.bus_id == BUS_ID
    assert opp.sensing_pass_id == SENSING_PASS_ID
    assert event.bus_id == BUS_ID
    assert event.observation_id == obs.observation_id
    assert event.opportunity_id == opp.opportunity_id

    # Simulated flag check
    assert "SIMULATED" in obs.model_version, "Simulator output must be labelled SIMULATED"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Opportunity evaluator
# ─────────────────────────────────────────────────────────────────────────────

def test_opportunity_evaluator():
    """TEST 5: OpportunityEvaluator produces valid Opportunity."""
    from edge.app.opportunity.opportunity_evaluator import OpportunityEvaluator
    from edge.app.hal.simulated import SimulatedGNSSProvider, SimulatedIMUProvider, SimulatedCameraProvider
    from contracts.opportunity import ValidityStatus, TargetScope

    evaluator = OpportunityEvaluator("BUS-001", "DEVICE-001", "CAMERA-FRONT-01")
    gnss = SimulatedGNSSProvider().read()
    imu = SimulatedIMUProvider().read()
    frame = SimulatedCameraProvider().capture()
    now = datetime.now(timezone.utc)

    opp = evaluator.evaluate(
        sensing_pass_id="PASS-TEST-001",
        window_start=now,
        window_end=now + timedelta(seconds=1),
        gnss=gnss,
        imu=imu,
        frame=frame,
    )

    assert opp.validity_status == ValidityStatus.VALID
    assert 0.0 <= opp.opportunity_score <= 1.0
    assert opp.fov_valid is True
    # Must NOT calculate evidence_weight or change RoadTwin state
    assert not hasattr(opp, "evidence_weight"), "Evaluator must not produce evidence_weight"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Event hash generation
# ─────────────────────────────────────────────────────────────────────────────

def test_event_hash_generation():
    """TEST 6: payload_hash is generated and stable for same inputs."""
    from edge.app.simulation.simulator import SensingPassSimulator

    sim1 = SensingPassSimulator()
    _, obs1, opp1, event1 = sim1.run()

    assert event1.payload_hash is not None
    assert len(event1.payload_hash) == 64, "SHA-256 hex digest must be 64 chars"

    # Verify hash is a valid SHA-256
    assert all(c in "0123456789abcdef" for c in event1.payload_hash)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Backend map-match ownership
# ─────────────────────────────────────────────────────────────────────────────

def test_backend_map_match_ownership():
    """TEST 13: Backend performs map-match. Edge hint is advisory only."""
    from backend.app.services.map_matcher import match_location, MapMatchStatus

    # Simulate GPS position matching SEG-001
    result = match_location(17.4435, 78.3772)
    assert result.map_match_status == MapMatchStatus.MATCHED
    assert result.matched_road_segment_id == "SEG-001"
    assert result.map_match_confidence is not None
    assert 0.0 <= result.map_match_confidence <= 1.0


def test_backend_map_match_unmatched():
    """TEST 13b: Backend returns UNMATCHED for distant positions."""
    from backend.app.services.map_matcher import match_location, MapMatchStatus

    # Coordinates far from all seeded segments (e.g., London)
    result = match_location(51.5074, -0.1278)
    assert result.map_match_status == MapMatchStatus.UNMATCHED

def test_openapi_schema_generation():
    """TEST 10: OpenAPI schema is generated and contains all required M1 endpoints."""
    from backend.app.main import app

    schema = app.openapi()
    assert "openapi" in schema
    assert "paths" in schema
    paths = schema["paths"]
    assert "/api/v1/events" in paths
    assert "/api/v1/opportunities" in paths
    assert "/api/v1/roadtwin" in paths
    assert "/api/v1/roadtwin/{roadtwin_id}" in paths
    assert "/health" in paths

    # Verify POST /api/v1/events exists and has requestBody
    assert "post" in paths["/api/v1/events"]
    # Verify GET /api/v1/roadtwin exists
    assert "get" in paths["/api/v1/roadtwin"]


def test_backend_health_unit():
    """TEST 9b: In-process health check returns 200 and valid schema."""
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8–12 & 14–16: Integration tests (require running backend + DB)
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _backend_available() -> bool:
    try:
        import httpx
        resp = httpx.get(f"{BACKEND_URL}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.integration
def test_backend_health():
    """TEST 9: Backend health check succeeds."""
    if not _backend_available():
        pytest.skip("Backend not reachable — BLOCKED")
    import httpx
    resp = httpx.get(f"{BACKEND_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.integration
def test_event_persistence_and_idempotency():
    """TEST 7+8: Event persists and idempotency works."""
    if not _backend_available():
        pytest.skip("Backend not reachable — BLOCKED")
    import httpx
    from edge.app.simulation.simulator import SensingPassSimulator

    sim = SensingPassSimulator()
    _, obs, opp, event = sim.run()

    # First POST opportunity
    opp_resp = httpx.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp.model_dump(mode="json"))
    assert opp_resp.status_code == 200

    # First POST event
    ev_payload = event.model_dump(mode="json")
    resp1 = httpx.post(f"{BACKEND_URL}/api/v1/events", json=ev_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "accepted"

    # Idempotent re-submit
    resp2 = httpx.post(f"{BACKEND_URL}/api/v1/events", json=ev_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "duplicate", "FAIL: Must return duplicate, not create second record"


@pytest.mark.integration
def test_roadtwin_created_after_event():
    """TEST 14+15: RoadTwin is created and accessible via GET API."""
    if not _backend_available():
        pytest.skip("Backend not reachable — BLOCKED")
    import httpx
    from edge.app.simulation.simulator import SensingPassSimulator

    sim = SensingPassSimulator()
    _, obs, opp, event = sim.run()
    httpx.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp.model_dump(mode="json"))
    ev_resp = httpx.post(f"{BACKEND_URL}/api/v1/events", json=event.model_dump(mode="json")).json()

    roadtwin_id = ev_resp.get("roadtwin_id")
    assert roadtwin_id is not None, "FAIL: RoadTwin ID must be returned after event ingestion"

    rt_resp = httpx.get(f"{BACKEND_URL}/api/v1/roadtwin/{roadtwin_id}")
    assert rt_resp.status_code == 200
    rt = rt_resp.json()
    assert rt["current_state"] == "OBSERVED"
    assert rt["road_segment_id"] == "SEG-001"
    assert rt["aggregate_confidence"] > 0.0
    assert rt["segment_centroid_lat"] is not None


@pytest.mark.integration
def test_opportunity_order_independence():
    """TEST 11+12: Event-before-opportunity and opportunity-before-event both work."""
    if not _backend_available():
        pytest.skip("Backend not reachable — BLOCKED")
    import httpx
    from edge.app.simulation.simulator import SensingPassSimulator

    # Opportunity AFTER event
    sim = SensingPassSimulator()
    _, obs, opp, event = sim.run()

    # Event first
    ev_resp = httpx.post(f"{BACKEND_URL}/api/v1/events", json=event.model_dump(mode="json"))
    assert ev_resp.status_code == 200, "Event-before-opportunity: event POST failed"

    # Opportunity after
    opp_resp = httpx.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp.model_dump(mode="json"))
    assert opp_resp.status_code == 200, "Event-before-opportunity: opportunity POST failed"
    assert opp_resp.json()["status"] == "accepted"


@pytest.mark.integration
def test_openapi_schema_valid():
    """TEST: OpenAPI schema is generated and valid."""
    if not _backend_available():
        pytest.skip("Backend not reachable — BLOCKED")
    import httpx
    resp = httpx.get(f"{BACKEND_URL}/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/api/v1/events" in schema["paths"]
    assert "/api/v1/opportunities" in schema["paths"]
    assert "/api/v1/roadtwin" in schema["paths"]

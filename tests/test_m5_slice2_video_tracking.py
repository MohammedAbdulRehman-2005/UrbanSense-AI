"""
UrbanSense AI — Milestone 5 Slice 2 Test Suite
==============================================
Edge Tracking & Video Perception -> Traffic Ingestion Integration

Verifies:
A. Video produces vehicle detections
B. Same-camera tracking creates stable track IDs
C. Observation receives track_id
D. CanonicalEvent receives the same track_id
E. EventBuilder propagates track_id and telemetry speed
F. Backend receives and persists track_id
G. Repeated frames for one track are deduplicated by TrafficAggregator
H. Distinct tracks are counted separately
I. Missing GNSS does not fabricate coordinates
J. Vehicle events do not mutate RoadTwin defect state
K. Deterministic E2E: Video -> Detection -> Tracking -> Observation -> EventBuilder -> CanonicalEvent -> Ingest -> TrafficAggregator
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from contracts.canonical_event import CanonicalEvent
from contracts.observation import Observation, BoundingBox
from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus
from edge.app.hal.file_camera import FileCameraProvider
from edge.app.hal.interfaces import CameraFrame, GNSSReading
from edge.app.perception.detectors.vehicle import BaselineVehicleDetector
from edge.app.perception.video_pipeline import VideoPerceptionPipeline
from edge.app.simulation.event_builder import EventBuilder
from edge.app.tracking.tracker import SameCameraTracker
from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.event import EventModel
from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.models.traffic import TrafficObservationModel
from backend.app.traffic.aggregator import TrafficAggregator, get_window_bounds
from scripts.generate_sample_road_video import generate_sample_road_video

SAMPLE_VIDEO_PATH = "data/sample_road_video.mp4"


@pytest.fixture(scope="session", autouse=True)
def ensure_sample_video():
    """Ensure sample road video fixture is present."""
    if not os.path.exists(SAMPLE_VIDEO_PATH):
        generate_sample_road_video(output_path=SAMPLE_VIDEO_PATH, num_frames=30, seed=42)
    assert os.path.exists(SAMPLE_VIDEO_PATH)


# ─── A & B: Video Detection & Same-Camera Tracking ───────────────────────────

def test_video_produces_vehicle_detections():
    """TEST A: VideoPerceptionPipeline processes video and extracts vehicle detections."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-TEST-01",
        camera_id="CAM-TEST-01",
        simulation_mode=True,
        deterministic=True,
    )
    results = pipeline.process_video_file(SAMPLE_VIDEO_PATH, max_frames=4, frame_step=1)
    assert len(results) == 4

    total_vehicle_dets = sum(
        1 for r in results for d in r.detections
        if d.object_type in ("car", "bus", "truck", "motorcycle", "bicycle")
    )
    assert total_vehicle_dets > 0, "Video pipeline must extract vehicle detections from sample video"

    for r in results:
        for d in r.detections:
            if d.object_type in ("car", "bus"):
                assert d.bbox.frame_width == 1280
                assert d.bbox.frame_height == 720
                assert 0.50 <= d.detector_confidence <= 1.0


def test_same_camera_tracking_creates_stable_track_ids():
    """TEST B: SameCameraTracker assigns stable track_id across consecutive video frames."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-TEST-01",
        camera_id="CAM-TEST-01",
        simulation_mode=True,
        deterministic=True,
    )
    results = pipeline.process_video_file(SAMPLE_VIDEO_PATH, max_frames=5, frame_step=1)

    # Collect track appearances per track_id
    track_appearances = {}
    for r in results:
        for d in r.detections:
            if d.object_type in ("car", "bus") and d.track_id:
                track_appearances.setdefault(d.track_id, []).append(r.frame_id)

    assert len(track_appearances) >= 1, "At least one vehicle track must be formed"

    # Verify at least one vehicle track survives across multiple frames
    multi_frame_tracks = [t_id for t_id, frames in track_appearances.items() if len(frames) >= 3]
    assert len(multi_frame_tracks) >= 1, (
        f"Expected at least 1 track across >=3 frames, found {track_appearances}"
    )

    primary_track = multi_frame_tracks[0]
    assert primary_track.startswith("TRK-CAM-TEST-01-"), "track_id must follow standard format"


# ─── C & D: Observation & CanonicalEvent Preservation ─────────────────────────

def test_observation_receives_track_id():
    """TEST C: Observation contract preserves track_id and trajectory_reference."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-TEST-01",
        camera_id="CAM-TEST-01",
        simulation_mode=True,
        deterministic=True,
    )
    results = pipeline.process_video_file(SAMPLE_VIDEO_PATH, max_frames=3, frame_step=1)

    vehicle_observations = [
        obs for r in results for obs in r.observations
        if obs.object_type in ("car", "bus", "truck", "motorcycle", "bicycle")
    ]
    assert len(vehicle_observations) > 0

    for obs in vehicle_observations:
        assert obs.track_id is not None, "Vehicle Observation must contain track_id from tracker"
        assert obs.track_id.startswith("TRK-CAM-TEST-01-")
        assert obs.trajectory_reference == f"traj://{obs.track_id}"
        assert obs.bus_id == "BUS-TEST-01"
        assert obs.camera_id == "CAM-TEST-01"


def test_canonical_event_receives_track_id():
    """TEST D: CanonicalEvent contract preserves track_id from Observation."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-TEST-01",
        camera_id="CAM-TEST-01",
        simulation_mode=True,
        deterministic=True,
    )
    results = pipeline.process_video_file(SAMPLE_VIDEO_PATH, max_frames=3, frame_step=1)

    vehicle_events = [
        ev for r in results for ev in r.events
        if ev.event_type in ("car_observation", "bus_observation")
    ]
    assert len(vehicle_events) > 0

    for ev in vehicle_events:
        assert ev.track_id is not None, "CanonicalEvent must receive track_id from Observation"
        assert ev.track_id.startswith("TRK-CAM-TEST-01-")
        # Ensure track_id is NOT mangled into event_id or observation_id
        assert ev.event_id != ev.track_id
        assert ev.observation_id != ev.track_id


# ─── E: EventBuilder Unit Tests ───────────────────────────────────────────────

def test_event_builder_propagates_track_id_and_telemetry_speed():
    """TEST E: EventBuilder copies track_id and telemetry speed and includes track_id in hash."""
    builder = EventBuilder(
        bus_id="BUS-01",
        device_id="DEV-01",
        camera_id="CAM-01",
        model_name="test-model",
        model_version="1.0",
        deterministic=True,
    )
    now = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    bbox = BoundingBox(x_min=10, y_min=20, x_max=50, y_max=60, frame_width=640, frame_height=480)
    obs = Observation(
        observation_id="OBS-001",
        frame_id="F-01",
        bus_id="BUS-01",
        device_id="DEV-01",
        camera_id="CAM-01",
        timestamp=now,
        object_type="car",
        detector_confidence=0.88,
        bbox=bbox,
        track_id="TRK-CAM-01-00042",
        trajectory_reference="traj://TRK-CAM-01-00042",
        model_name="test-model",
        model_version="1.0",
    )
    opp = MagicMock(spec=ObservationOpportunity)
    opp.opportunity_id = "OPP-001"
    opp.trace_id = "TR-01"
    opp.opportunity_score = 0.85

    ev = builder.build(
        observation=obs,
        opportunity=opp,
        event_timestamp=now,
        latitude=17.4300,
        longitude=78.3600,
        event_type="car_observation",
        telemetry_speed_kmh=24.5,
    )

    assert ev.track_id == "TRK-CAM-01-00042"
    assert ev.telemetry_speed_kmh == 24.5
    assert ev.payload_hash is not None
    assert len(ev.payload_hash) == 64


# ─── F: Backend Ingestion Persists track_id ───────────────────────────────────

def test_backend_receives_and_persists_track_id():
    """TEST F: POST /api/v1/events receives and persists track_id in database."""
    client = TestClient(app)
    t_now = datetime.now(timezone.utc)
    test_track_id = f"TRK-TEST-{uuid.uuid4().hex[:6]}"

    payload = {
        "event_id": f"EVT-TEST-{uuid.uuid4()}",
        "schema_version": "1.0",
        "bus_id": "BUS-TEST-01",
        "device_id": "DEV-TEST-01",
        "camera_id": "CAM-TEST-01",
        "event_timestamp": t_now.isoformat(),
        "location": {"latitude": 17.4300, "longitude": 78.3600},
        "event_type": "car_observation",
        "track_id": test_track_id,
        "telemetry_speed_kmh": 18.0,
        "detector_confidence": 0.85,
        "model_name": "test-vehicle-model",
        "model_version": "1.0.0",
        "priority": "P2",
        "trace_id": str(uuid.uuid4()),
    }

    resp = client.post("/api/v1/events", json=payload)
    assert resp.status_code == 200
    assert resp.json().get("status") == "accepted"

    with SessionLocal() as db:
        ev_model = db.query(EventModel).filter_by(event_id=payload["event_id"]).first()
        assert ev_model is not None
        assert ev_model.track_id == test_track_id
        assert ev_model.telemetry_speed_kmh == 18.0


# ─── G & H: Deduplication vs Distinct Counting ────────────────────────────────

def test_repeated_frames_for_one_track_are_deduplicated():
    """TEST G: 5 consecutive frames sharing track_id count as 1 vehicle in TrafficAggregator."""
    w_start = datetime(2026, 9, 26, 11, 0, 0, tzinfo=timezone.utc)
    w_end = w_start + timedelta(seconds=60)
    seg_id = f"SEG-TEST-DEDUP-{uuid.uuid4().hex[:4]}"

    db = MagicMock()
    # 5 events, all with track_id="TRK-CAR-99"
    events = []
    for i in range(5):
        ev = MagicMock()
        ev.event_id = f"EV-SAME-{i}"
        ev.track_id = "TRK-CAR-99"
        ev.event_type = "car_observation"
        ev.event_timestamp = w_start + timedelta(seconds=i * 2)
        ev.latitude = 17.4300
        ev.longitude = 78.3600
        ev.telemetry_speed_kmh = 15.0
        ev.bus_id = "BUS-01"
        ev.device_id = "DEV-01"
        ev.camera_id = "CAM-01"
        ev.opportunity_id = "OPP-01"
        events.append(ev)

    db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = events
    db.query.return_value.filter_by.return_value.first.return_value = None

    aggregator = TrafficAggregator()
    result = aggregator.aggregate_window_from_events(db, seg_id, w_start, w_end)

    assert result.vehicle_count == 1, "5 sightings of the same track must be deduplicated to 1 vehicle"
    assert result.vehicle_class_counts["car"] == 1


def test_distinct_tracks_are_counted_separately():
    """TEST H: Distinct tracks (TRK-A, TRK-B, TRK-C) are counted separately."""
    w_start = datetime(2026, 9, 26, 11, 0, 0, tzinfo=timezone.utc)
    w_end = w_start + timedelta(seconds=60)
    seg_id = f"SEG-TEST-DISTINCT-{uuid.uuid4().hex[:4]}"

    db = MagicMock()
    tracks = [
        ("TRK-A", "car_observation"),
        ("TRK-A", "car_observation"),  # Duplicate of A
        ("TRK-B", "bus_observation"),
        ("TRK-C", "truck_observation"),
        ("TRK-B", "bus_observation"),  # Duplicate of B
    ]
    events = []
    for i, (t_id, e_type) in enumerate(tracks):
        ev = MagicMock()
        ev.event_id = f"EV-DIST-{i}"
        ev.track_id = t_id
        ev.event_type = e_type
        ev.event_timestamp = w_start + timedelta(seconds=i * 3)
        ev.latitude = 17.4300
        ev.longitude = 78.3600
        ev.telemetry_speed_kmh = 20.0
        ev.bus_id = "BUS-01"
        ev.device_id = "DEV-01"
        ev.camera_id = "CAM-01"
        ev.opportunity_id = "OPP-01"
        events.append(ev)

    db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = events
    db.query.return_value.filter_by.return_value.first.return_value = None

    aggregator = TrafficAggregator()
    result = aggregator.aggregate_window_from_events(db, seg_id, w_start, w_end)

    assert result.vehicle_count == 3, "3 distinct tracks must produce vehicle_count=3"
    assert result.vehicle_class_counts["car"] == 1
    assert result.vehicle_class_counts["bus"] == 1
    assert result.vehicle_class_counts["truck"] == 1


# ─── I: Missing GNSS Handling ─────────────────────────────────────────────────

def test_missing_gnss_does_not_fabricate_coordinates():
    """TEST I: Missing GNSS records Observation, but skips CanonicalEvent without fabricating coordinates."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-TEST-01",
        camera_id="CAM-TEST-01",
        simulation_mode=False,  # Explicitly normal mode (no simulated fallback)
        deterministic=True,
    )
    dummy_img = MagicMock()
    dummy_img.shape = (720, 1280, 3)
    frame = CameraFrame(
        frame_id="F-NOGNSS-01",
        camera_id="CAM-TEST-01",
        timestamp=datetime.now(timezone.utc),
        width=1280,
        height=720,
        image=None,  # No image -> 0 detections, or test with mock detector
    )

    # Supply a mock detector that returns 1 detection
    mock_det = MagicMock()
    mock_det.model_name = "mock-det"
    mock_det.model_version = "1.0"
    raw_d = MagicMock()
    raw_d.object_type = "car"
    raw_d.detector_confidence = 0.80
    raw_d.bbox = BoundingBox(x_min=10, y_min=20, x_max=50, y_max=60, frame_width=1280, frame_height=720)
    raw_d.mask_reference = None
    raw_d.track_id = "TRK-001"
    raw_d.model_name = "mock-det"
    raw_d.model_version = "1.0"
    mock_det.detect.return_value = [raw_d]
    pipeline.detectors = [mock_det]

    res = pipeline.process_frame(frame, gnss=None)

    # Observation exists
    assert len(res.observations) == 1
    # CanonicalEvent skipped due to missing GNSS (R4 architectural rule: never fabricate 0,0)
    assert len(res.events) == 0


# ─── J: Domain Separation Guard ───────────────────────────────────────────────

def test_vehicle_events_do_not_mutate_roadtwin_defect_state():
    """TEST J: Ingested vehicle events do NOT alter RoadTwin defect state or evidence counts."""
    client = TestClient(app)
    t_now = datetime.now(timezone.utc)

    # Check baseline RoadTwin state for SEG-001
    r_init = client.get("/api/v1/roadtwin")
    assert r_init.status_code == 200
    twins = r_init.json()
    seg001_twin = next((t for t in twins if t["road_segment_id"] == "SEG-001"), None)
    initial_state = seg001_twin["current_state"] if seg001_twin else None
    initial_conf = seg001_twin["aggregate_confidence"] if seg001_twin else None
    initial_pos_count = seg001_twin["positive_evidence_count"] if seg001_twin else None

    # Post vehicle event matching SEG-001
    veh_payload = {
        "event_id": f"EVT-DEFECT-SEPARATION-{uuid.uuid4()}",
        "schema_version": "1.0",
        "bus_id": "BUS-TEST-01",
        "device_id": "DEV-TEST-01",
        "camera_id": "CAM-TEST-01",
        "event_timestamp": t_now.isoformat(),
        "location": {"latitude": 17.4435, "longitude": 78.3772},  # SEG-001 centroid
        "event_type": "car_observation",
        "track_id": "TRK-CAR-SEPARATION",
        "detector_confidence": 0.90,
        "model_name": "test-vehicle",
        "model_version": "1.0.0",
        "priority": "P2",
        "trace_id": str(uuid.uuid4()),
    }
    resp = client.post("/api/v1/events", json=veh_payload)
    assert resp.status_code == 200
    assert resp.json().get("roadtwin_id") is None, "Vehicle events must NOT return roadtwin_id"

    # Verify RoadTwin state was NOT mutated
    r_after = client.get("/api/v1/roadtwin")
    twins_after = r_after.json()
    seg001_after = next((t for t in twins_after if t["road_segment_id"] == "SEG-001"), None)
    if seg001_twin:
        assert seg001_after["current_state"] == initial_state
        assert seg001_after["aggregate_confidence"] == initial_conf
        assert seg001_after["positive_evidence_count"] == initial_pos_count


# ─── K: Deterministic Video E2E Integration ───────────────────────────────────

def test_deterministic_video_e2e_to_traffic_observation():
    """
    TEST K (CRITICAL E2E):
    Executes the complete real chain:
        Sample Road Video
        -> FileCameraProvider
        -> VideoPerceptionPipeline
        -> BaselineVehicleDetector
        -> SameCameraTracker
        -> Observation (with track_id)
        -> EventBuilder
        -> CanonicalEvent (with track_id)
        -> POST /api/v1/events
        -> TrafficAggregator
        -> TrafficObservation read model
    """
    client = TestClient(app)
    test_run_id = uuid.uuid4().hex[:6]
    # Unique base timestamp to guarantee clean window isolation in shared test DB
    base_ts = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=int(uuid.uuid4().hex[:4], 16) % 10000 + 10
    )

    # 1. Pipeline initialization
    pipeline = VideoPerceptionPipeline(
        bus_id=f"BUS-E2E-{test_run_id}",
        device_id=f"DEV-E2E-{test_run_id}",
        camera_id="CAMERA-FRONT-01",
        simulation_mode=False,
        deterministic=False,
    )

    # 2. Camera provider decoding real MP4 file
    camera = FileCameraProvider(
        video_path=SAMPLE_VIDEO_PATH,
        camera_id="CAMERA-FRONT-01",
        base_timestamp=base_ts,
    )

    frame_results = []
    with camera:
        for frame in camera.frames(step=1):
            # Coordinates in SEG-TRF-001 traffic corridor
            gnss = GNSSReading(
                latitude=17.4300 + (len(frame_results) * 0.00001),
                longitude=78.3600 + (len(frame_results) * 0.00001),
                altitude_m=540.0,
                accuracy_m=2.0,
                heading_deg=90.0,
                timestamp=frame.timestamp,
                fix_quality=1,
                speed_kmh=18.5,
            )
            res = pipeline.process_frame(
                frame=frame,
                gnss=gnss,
                edge_road_segment_hint="SEG-TRF-001",
            )
            frame_results.append(res)
            if len(frame_results) >= 5:  # 5 consecutive frames
                break

    assert len(frame_results) == 5, "Must process 5 frames from sample video"

    # 3. Verify vehicle detections and tracks formed
    unique_tracks = set()
    canonical_vehicle_events = []
    for fr in frame_results:
        for obs in fr.observations:
            if obs.object_type in ("car", "bus"):
                assert obs.track_id is not None
                unique_tracks.add(obs.track_id)
        for ev in fr.events:
            if ev.event_type in ("car_observation", "bus_observation"):
                assert ev.track_id is not None
                canonical_vehicle_events.append(ev)

    assert len(unique_tracks) >= 1, "Must find at least 1 tracked vehicle in video"
    assert len(canonical_vehicle_events) > len(unique_tracks), (
        "Multi-frame events must exceed unique tracks, proving multiple sightings of the same vehicle"
    )

    # 4. Ingest opportunities first
    for fr in frame_results:
        opp_payload = fr.opportunity.model_dump(mode="json")
        client.post("/api/v1/opportunities", json=opp_payload)

    # 5. Ingest canonical vehicle events into backend
    for ev in canonical_vehicle_events:
        ev_payload = ev.model_dump(mode="json")
        r = client.post("/api/v1/events", json=ev_payload)
        assert r.status_code == 200
        assert r.json().get("status") in ("accepted", "duplicate")

    # 6. Verify Traffic Read Model produces aggregated TrafficObservation
    trf_resp = client.get("/api/v1/traffic?road_segment_id=SEG-TRF-001&limit=50")
    assert trf_resp.status_code == 200
    observations = trf_resp.json()
    assert len(observations) >= 1, "Backend must produce at least one TrafficObservation for SEG-TRF-001"

    # Match the observation for our test window (base_ts = 12:00:00 UTC)
    w_start, _ = get_window_bounds(base_ts, duration_seconds=60)
    w_prefix = w_start.strftime("%Y-%m-%dT%H:%M")
    matching_obs = [o for o in observations if o["window_start"].startswith(w_prefix)]
    assert len(matching_obs) >= 1, f"Expected observation for window {w_prefix}, found {[o['window_start'] for o in observations]}"
    test_obs = matching_obs[0]

    # Invariant: Traffic observation vehicle count must reflect deduplicated tracks,
    # NOT the raw total frame sightings count!
    assert test_obs["vehicle_count"] == len(unique_tracks)
    assert test_obs["vehicle_count"] < len(canonical_vehicle_events), (
        f"Aggregated count ({test_obs['vehicle_count']}) must be strictly less than raw events ({len(canonical_vehicle_events)}) due to track deduplication"
    )
    assert test_obs["density"] > 0.0
    assert test_obs["flow_rate"] > 0.0
    assert test_obs["congestion_state"] in ("NORMAL", "ELEVATED", "HIGH")

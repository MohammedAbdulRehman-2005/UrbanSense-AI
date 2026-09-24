"""
UrbanSense AI — Milestone 2.1 Regression Test Suite
=====================================================
Validates all 14 architectural and semantic corrections:
1. Deterministic synthetic-video generation
2. Deterministic simulation IDs
3. Opportunity window grouping (multiple frames per opportunity)
4. Multiple observations sharing an opportunity
5. Missing GNSS behavior (no silent fabrication)
6. Missing IMU behavior
7. Detector exception handling (pipeline does not crash)
8. Detector failure observability (DETECTOR FAILURE != NO DETECTION)
9. Performance metric consistency (E2E ms vs FPS mathematical identity)
10. Event routing by type (pothole routes to RoadTwin, vehicle does not)
11. Vehicle event does not update defect RoadTwin
12. Heuristic detector confidence documentation and semantics
13. Evidence lineage (Observation -> Event -> Disk artifact)
14. Synthetic-video terminology and configuration
15. M1 demo validation behavior (no bare assert, explicit timeouts)
16. M2 demo failure behavior (no false PASS on failure)
17. Frontend build verification
"""
from __future__ import annotations

import os
import sys
import tempfile
import inspect
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.observation import Observation, BoundingBox
from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus
from contracts.canonical_event import CanonicalEvent, Location
from edge.app.hal.interfaces import CameraFrame, GNSSReading, IMUReading
from edge.app.hal.file_camera import FileCameraProvider
from edge.app.perception.detectors.base import BaseDetector, RawDetection
from edge.app.perception.detectors.pothole import BaselinePotholeDetector
from edge.app.perception.detectors.vehicle import BaselineVehicleDetector
from edge.app.perception.video_pipeline import (
    VideoPerceptionPipeline,
    DetectorExecutionResult,
)
from edge.app.simulation.simulator import SensingPassSimulator
from scripts.generate_sample_road_video import generate_sample_road_video


# ─────────────────────────────────────────────────────────────────────────────
# 1. Deterministic Synthetic-Video Generation
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_synthetic_video_generation():
    """TEST 1: Same seed produces identical frame data in synthetic video fixture."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path1 = os.path.join(tmpdir, "vid1.mp4")
        path2 = os.path.join(tmpdir, "vid2.mp4")

        generate_sample_road_video(output_path=path1, num_frames=5, seed=42)
        generate_sample_road_video(output_path=path2, num_frames=5, seed=42)

        with FileCameraProvider(path1) as cam1, FileCameraProvider(path2) as cam2:
            for _ in range(5):
                f1 = cam1.capture()
                f2 = cam2.capture()
                assert np.array_equal(f1.image, f2.image), "Frames from identical seeds must be pixel-identical"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Deterministic Simulation IDs
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_simulation_ids():
    """TEST 2: Deterministic mode produces reproducible IDs across simulator and pipeline."""
    sim1 = SensingPassSimulator(deterministic=True)
    sp_id1, obs1, opp1, evt1 = sim1.run()

    sim2 = SensingPassSimulator(deterministic=True)
    sp_id2, obs2, opp2, evt2 = sim2.run()

    assert sp_id1 == sp_id2 == "SIMPASS-M1-001"
    assert obs1.observation_id == obs2.observation_id == "OBS-000001"
    assert opp1.opportunity_id == opp2.opportunity_id
    assert evt1.event_id == evt2.event_id == "EVT-000001"
    assert evt1.trace_id == evt2.trace_id == "TRACE-BUS001-000001"
    assert evt1.payload_hash == evt2.payload_hash

    # Pipeline deterministic mode
    pipe = VideoPerceptionPipeline(bus_id="BUS-001", simulation_mode=True, deterministic=True)
    assert pipe.sensing_pass_id == "VIDPASS-BUS-001-001"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Opportunity Window Grouping
# ─────────────────────────────────────────────────────────────────────────────

def test_opportunity_window_grouping():
    """TEST 3: 10 frames within a 1.0s window produce 1 opportunity, not 10 independent ones."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        simulation_mode=True,
        opportunity_window_duration_s=1.0,
    )
    base_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)

    results = []
    for i in range(10):
        # 10 frames spaced 33ms apart = 330ms span <= 1.0s opportunity window
        frame = CameraFrame(
            frame_id=f"FRAME-{i:04d}",
            camera_id="CAMERA-FRONT-01",
            timestamp=base_time + timedelta(milliseconds=i * 33),
            width=640,
            height=480,
            image=dummy_img,
            frame_index=i + 1,
        )
        res = pipeline.process_frame(frame)
        results.append(res)

    unique_opp_ids = set(r.opportunity.opportunity_id for r in results)
    assert len(unique_opp_ids) == 1, (
        f"Expected all 10 frames within 1.0s window to share 1 opportunity, got {len(unique_opp_ids)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multiple Observations Sharing an Opportunity
# ─────────────────────────────────────────────────────────────────────────────

def test_multiple_observations_sharing_an_opportunity():
    """TEST 4: Multiple observations within the sensing window reference the same opportunity_id."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        simulation_mode=True,
        opportunity_window_duration_s=1.0,
    )
    base_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    dummy_img = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Process 3 frames in window
    all_events = []
    opp_id = None
    for i in range(3):
        frame = CameraFrame(
            frame_id=f"FRAME-MULTI-{i:04d}",
            camera_id="CAMERA-FRONT-01",
            timestamp=base_time + timedelta(milliseconds=i * 33),
            width=1280,
            height=720,
            image=dummy_img,
            frame_index=i + 1,
        )
        res = pipeline.process_frame(frame)
        opp_id = res.opportunity.opportunity_id
        all_events.extend(res.events)

    for ev in all_events:
        assert ev.opportunity_id == opp_id, "Every event in window must reference the shared opportunity_id"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Missing GNSS Behavior (No Silent Fabrication)
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_gnss_behavior():
    """TEST 5: Missing GNSS in normal mode is detectable, marks opportunity INVALID, does not fake coords."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        simulation_mode=False,  # Strict mode: no silent fabrication
        gnss_provider=None,
    )
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame(
        frame_id="F-NOGPS",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=640,
        height=480,
        image=dummy_img,
    )

    res = pipeline.process_frame(frame, gnss=None)

    assert res.opportunity.validity_status == ValidityStatus.INVALID
    assert res.opportunity.gps_quality_score == 0.0
    assert "Missing GNSS sensor data" in res.opportunity.invalid_reasons
    # Because GNSS is missing, events cannot be geolocated and are not assembled
    assert len(res.events) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Missing IMU Behavior
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_imu_behavior():
    """TEST 6: Missing IMU in normal mode degrades sensor health and records invalid reason."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        simulation_mode=False,
        imu_provider=None,
    )
    gnss = GNSSReading(17.44, 78.37, 500.0, 2.0, 45.0, datetime.now(timezone.utc), fix_quality=1)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame(
        frame_id="F-NOIMU",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=640,
        height=480,
        image=dummy_img,
    )

    res = pipeline.process_frame(frame, gnss=gnss, imu=None)
    assert res.opportunity.sensor_health_score <= 0.5
    assert "Missing IMU sensor data" in res.opportunity.invalid_reasons


# ─────────────────────────────────────────────────────────────────────────────
# 7. Detector Exception Handling
# ─────────────────────────────────────────────────────────────────────────────

class FaultyDetector(BaseDetector):
    def detect(self, frame: CameraFrame):
        raise RuntimeError("Simulated detector hardware failure")

    @property
    def model_name(self) -> str:
        return "faulty-pothole-detector"

    @property
    def model_version(self) -> str:
        return "1.0.0-FAULTY"


def test_detector_exception_handling():
    """TEST 7: Pipeline survives detector exception, does not crash, continues processing."""
    faulty = FaultyDetector()
    working = BaselineVehicleDetector()

    pipeline = VideoPerceptionPipeline(
        detectors=[faulty, working],
        simulation_mode=True,
    )
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame(
        frame_id="F-ERR-01",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=640,
        height=480,
        image=dummy_img,
    )

    res = pipeline.process_frame(frame)
    assert res is not None
    assert isinstance(res.detections, list)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Detector Failure Observability
# ─────────────────────────────────────────────────────────────────────────────

def test_detector_failure_observability():
    """TEST 8: DETECTOR FAILURE != NO DETECTION. Failure is recorded with error details."""
    faulty = FaultyDetector()
    pipeline = VideoPerceptionPipeline(
        detectors=[faulty],
        simulation_mode=True,
    )
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame(
        frame_id="F-OBS-01",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=640,
        height=480,
        image=dummy_img,
    )

    res = pipeline.process_frame(frame)

    assert pipeline.metrics.detector_failures == 1
    assert len(res.detector_results) == 1
    det_res = res.detector_results[0]
    assert det_res.success is False
    assert det_res.error_code == "RuntimeError"
    assert "Simulated detector hardware failure" in (det_res.error_message or "")

    assert len(res.detector_errors) == 1
    err_dict = res.detector_errors[0]
    assert err_dict["frame_id"] == "F-OBS-01"
    assert err_dict["model_name"] == "faulty-pothole-detector"
    assert err_dict["error_code"] == "RuntimeError"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Performance Metric Consistency
# ─────────────────────────────────────────────────────────────────────────────

def test_performance_metric_consistency():
    """TEST 9: Mathematical consistency between total time, end-to-end ms/frame, and processed FPS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "perf_test.mp4")
        generate_sample_road_video(output_path=video_path, num_frames=6, seed=42)

        pipeline = VideoPerceptionPipeline(simulation_mode=True, deterministic=True)
        results = pipeline.process_video_file(video_path, max_frames=5)

        m = pipeline.metrics
        assert m.frames_processed == 5
        assert m.total_time_seconds > 0.0
        assert m.avg_end_to_end_ms_per_frame > 0.0

        # Mathematical identity: FPS = 1000 / avg_ms
        expected_fps = round(1000.0 / m.avg_end_to_end_ms_per_frame, 2)
        assert m.average_processed_fps == expected_fps

        # Sum of accounted components + residual overhead == total measured time
        sum_accounted_ms = (
            m.acquisition_time_ms +
            m.quality_eval_time_ms +
            m.opportunity_eval_time_ms +
            m.inference_time_ms +
            m.tracking_time_ms +
            m.evidence_and_event_time_ms
        )
        assert m.overhead_time_ms >= 0.0
        assert (sum_accounted_ms + m.overhead_time_ms) == pytest.approx(m.total_time_seconds * 1000.0, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Event Routing By Type
# ─────────────────────────────────────────────────────────────────────────────

def test_event_routing_by_type():
    """TEST 10: Event routing classifies road defects separately from vehicle events."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.api.v1.events import ROAD_DEFECT_EVENT_TYPES
    import uuid

    # Static contract check
    assert "pothole_observation" in ROAD_DEFECT_EVENT_TYPES
    assert "road_defect" in ROAD_DEFECT_EVENT_TYPES
    assert "surface_distress" in ROAD_DEFECT_EVENT_TYPES
    assert "pothole" in ROAD_DEFECT_EVENT_TYPES
    assert "car_observation" not in ROAD_DEFECT_EVENT_TYPES
    assert "bus_observation" not in ROAD_DEFECT_EVENT_TYPES

    # Behavioral check via TestClient
    client = TestClient(app)

    # 1. Defect event -> triggers RoadTwin upsert and returns roadtwin_id
    defect_payload = {
        "event_id": f"TEST-ROUTING-DEFECT-{uuid.uuid4()}",
        "schema_version": "1.0",
        "bus_id": "BUS-001",
        "device_id": "DEV-001",
        "camera_id": "CAM-001",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 17.4435, "longitude": 78.3772},
        "event_type": "pothole_observation",
        "detector_confidence": 0.85,
        "model_name": "baseline-pothole",
        "model_version": "1.0.0",
        "priority": "P2",
        "trace_id": str(uuid.uuid4()),
    }
    r_defect = client.post("/api/v1/events", json=defect_payload)
    assert r_defect.status_code == 200
    data_defect = r_defect.json()
    assert data_defect["status"] == "accepted"
    assert data_defect["roadtwin_id"] is not None
    assert data_defect["matched_road_segment_id"] == "SEG-001"

    # 2. Vehicle event -> does NOT trigger RoadTwin upsert (roadtwin_id is None)
    vehicle_payload = {
        "event_id": f"TEST-ROUTING-VEHICLE-{uuid.uuid4()}",
        "schema_version": "1.0",
        "bus_id": "BUS-001",
        "device_id": "DEV-001",
        "camera_id": "CAM-001",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 17.4435, "longitude": 78.3772},
        "event_type": "car_observation",
        "detector_confidence": 0.85,
        "model_name": "baseline-vehicle",
        "model_version": "1.0.0",
        "priority": "P2",
        "trace_id": str(uuid.uuid4()),
    }
    r_vehicle = client.post("/api/v1/events", json=vehicle_payload)
    assert r_vehicle.status_code == 200
    data_vehicle = r_vehicle.json()
    assert data_vehicle["status"] == "accepted"
    assert data_vehicle["roadtwin_id"] is None
    assert data_vehicle["matched_road_segment_id"] == "SEG-001"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Vehicle Event Does Not Update Defect RoadTwin
# ─────────────────────────────────────────────────────────────────────────────

def test_vehicle_event_does_not_update_defect_roadtwin():
    """TEST 11: Ingesting a vehicle observation event does not mutate defect RoadTwin state."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    import uuid

    client = TestClient(app)

    # Fetch initial RoadTwin state
    r_init = client.get("/api/v1/roadtwin")
    assert r_init.status_code == 200
    init_twins = r_init.json()
    seg1_twin = next((t for t in init_twins if t.get("road_segment_id") == "SEG-001"), None)
    initial_count = seg1_twin["positive_evidence_count"] if seg1_twin else 0
    initial_conf = seg1_twin["aggregate_confidence"] if seg1_twin else 0.0

    # Ingest multiple vehicle events
    for v_type in ["car_observation", "bus_observation", "truck_observation", "motorcycle_observation"]:
        v_payload = {
            "event_id": f"TEST-VNOUPDATE-{uuid.uuid4()}",
            "schema_version": "1.0",
            "bus_id": "BUS-001",
            "device_id": "DEV-001",
            "camera_id": "CAM-001",
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"latitude": 17.4435, "longitude": 78.3772},
            "event_type": v_type,
            "detector_confidence": 0.90,
            "model_name": "baseline-vehicle",
            "model_version": "1.0.0",
            "priority": "P2",
            "trace_id": str(uuid.uuid4()),
        }
        res = client.post("/api/v1/events", json=v_payload)
        assert res.status_code == 200
        assert res.json().get("roadtwin_id") is None

    # Fetch RoadTwin state after vehicle events
    r_after = client.get("/api/v1/roadtwin")
    assert r_after.status_code == 200
    after_twins = r_after.json()
    seg1_after = next((t for t in after_twins if t.get("road_segment_id") == "SEG-001"), None)
    if seg1_twin:
        assert seg1_after["positive_evidence_count"] == initial_count, "Vehicle events must NOT increment positive_evidence_count"
        assert seg1_after["aggregate_confidence"] == initial_conf, "Vehicle events must NOT mutate aggregate_confidence"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Heuristic Detector Confidence Documentation / Semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_heuristic_detector_confidence_semantics():
    """TEST 12: Baseline detectors produce bounded [0.0, 1.0] heuristic scores documented in DECISION-013."""
    p_detector = BaselinePotholeDetector()
    v_detector = BaselineVehicleDetector()

    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame(
        frame_id="F-CONF-01",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=640,
        height=480,
        image=dummy_img,
    )

    p_dets = p_detector.detect(frame)
    for d in p_dets:
        assert 0.0 <= d.detector_confidence <= 1.0

    v_dets = v_detector.detect(frame)
    for d in v_dets:
        assert 0.0 <= d.detector_confidence <= 1.0

    # Verify documentation in docs/decision-log.md
    with open("docs/decision-log.md", "r", encoding="utf-8") as f:
        log_content = f.read()
    assert "DECISION-013" in log_content
    assert "uncalibrated prototype detector score" in log_content


# ─────────────────────────────────────────────────────────────────────────────
# 13. Evidence Lineage
# ─────────────────────────────────────────────────────────────────────────────

def test_evidence_lineage():
    """TEST 13: Evidence reference is consistently traceable from Observation to Event to disk."""
    pipeline = VideoPerceptionPipeline(simulation_mode=True, deterministic=True)
    img = np.full((720, 1280, 3), 120, dtype=np.uint8)
    cv2.ellipse(img, (640, 550), (60, 30), 0, 0, 360, (20, 20, 20), -1)

    frame = CameraFrame(
        frame_id="FRAME-EV-01",
        camera_id="CAMERA-FRONT-01",
        timestamp=datetime.now(timezone.utc),
        width=1280,
        height=720,
        image=img,
        frame_index=1,
    )

    res = pipeline.process_frame(frame)
    assert len(res.observations) > 0, "Expected at least one observation from synthetic ellipse"
    assert len(res.events) > 0, "Expected at least one event assembled from observation"

    ev = res.events[0]
    obs = res.observations[0]
    assert ev.evidence_ref == obs.evidence_hint, "Event evidence_ref must match observation evidence_hint"
    assert ev.evidence_ref.startswith("evidence://local/"), "Prototype evidence URI must use evidence://local/ scheme"

    # Check local file path exists on disk and is a valid image
    local_rel_path = os.path.join("data", "evidence", ev.evidence_ref.replace("evidence://local/", ""))
    assert os.path.exists(local_rel_path), f"Evidence crop file not found: {local_rel_path}"
    crop_img = cv2.imread(local_rel_path)
    assert crop_img is not None, "Evidence file must be a readable image"
    assert crop_img.shape[0] > 0 and crop_img.shape[1] > 0, "Evidence crop must have non-zero dimensions"


# ─────────────────────────────────────────────────────────────────────────────
# 14. Synthetic-Video Terminology / Config
# ─────────────────────────────────────────────────────────────────────────────

def test_synthetic_video_terminology_config():
    """TEST 14: Video generator explicitly documents synthetic fixture status and accepts seed."""
    sig = inspect.signature(generate_sample_road_video)
    assert "seed" in sig.parameters
    assert sig.parameters["seed"].default == 42
    assert "SYNTHETIC" in (generate_sample_road_video.__doc__ or "").upper()


# ─────────────────────────────────────────────────────────────────────────────
# 15. M1 Demo Validation Behavior
# ─────────────────────────────────────────────────────────────────────────────

def test_m1_demo_validation_behavior():
    """TEST 15: run_m1_demo.py exits non-zero on transport failure, HTTP 500, or non-JSON."""
    from scripts.run_m1_demo import main as m1_main
    import httpx

    # 1. Transport failure on health check
    with patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.side_effect = httpx.ConnectError("backend down")
        with pytest.raises(SystemExit) as exc_info:
            m1_main()
        assert exc_info.value.code == 1

    # 2. HTTP 500 on Opportunity POST
    with patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        client_mock.post.return_value = MagicMock(status_code=500, text="Internal Server Error", json=lambda: {})
        with pytest.raises(SystemExit) as exc_info:
            m1_main()
        assert exc_info.value.code == 1

    # 3. Non-JSON response on Event POST
    with patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        opp_resp = MagicMock(status_code=200, json=lambda: {"status": "accepted"})
        def side_effect_post(url, **kwargs):
            if "/opportunities" in url:
                return opp_resp
            bad_resp = MagicMock(status_code=200)
            bad_resp.json.side_effect = ValueError("Invalid JSON")
            return bad_resp
        client_mock.post.side_effect = side_effect_post
        with pytest.raises(SystemExit) as exc_info:
            m1_main()
        assert exc_info.value.code == 1


# ─────────────────────────────────────────────────────────────────────────────
# 16. M2 Demo Failure Behavior
# ─────────────────────────────────────────────────────────────────────────────

def test_m2_demo_failure_behavior():
    """TEST 16: run_video_demo.py exits non-zero on backend failure or non-JSON response."""
    from scripts.run_video_demo import main as m2_main
    import httpx

    # 1. Transport failure connecting to backend
    with patch("sys.argv", ["run_video_demo.py", "--max-frames", "2", "--frame-step", "1"]), \
         patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.side_effect = httpx.ConnectError("backend down")
        with pytest.raises(SystemExit) as exc_info:
            m2_main()
        assert exc_info.value.code == 1

    # 2. HTTP 500 on Opportunity POST
    with patch("sys.argv", ["run_video_demo.py", "--max-frames", "2", "--frame-step", "1"]), \
         patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        client_mock.post.return_value = MagicMock(status_code=500, text="Opp Fail", json=lambda: {})
        with pytest.raises(SystemExit) as exc_info:
            m2_main()
        assert exc_info.value.code == 1

    # 3. Non-JSON response on Event POST
    with patch("sys.argv", ["run_video_demo.py", "--max-frames", "2", "--frame-step", "1"]), \
         patch("httpx.Client") as mock_cls:
        client_mock = MagicMock()
        mock_cls.return_value.__enter__.return_value = client_mock
        client_mock.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        opp_resp = MagicMock(status_code=200, json=lambda: {"status": "accepted"})
        def side_effect_post(url, **kwargs):
            if "/opportunities" in url:
                return opp_resp
            bad_resp = MagicMock(status_code=200)
            bad_resp.json.side_effect = ValueError("Invalid JSON")
            return bad_resp
        client_mock.post.side_effect = side_effect_post
        with pytest.raises(SystemExit) as exc_info:
            m2_main()
        assert exc_info.value.code == 1


# ─────────────────────────────────────────────────────────────────────────────
# 17. Frontend Build Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_frontend_build():
    """TEST 17: Frontend production build output exists, contains JS/CSS assets and valid index.html."""
    dist_dir = os.path.join("frontend", "dist")
    assert os.path.exists(dist_dir), "frontend/dist must exist from successful npm run build"
    index_html = os.path.join(dist_dir, "index.html")
    assert os.path.exists(index_html), "frontend/dist/index.html must exist"
    with open(index_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    assert len(html_content) > 100, "frontend/dist/index.html must not be empty"
    assert "<script" in html_content, "index.html must reference JavaScript bundles"

    assets_dir = os.path.join(dist_dir, "assets")
    assert os.path.exists(assets_dir), "frontend/dist/assets must exist"
    asset_files = os.listdir(assets_dir)
    js_files = [f for f in asset_files if f.endswith(".js")]
    css_files = [f for f in asset_files if f.endswith(".css")]
    assert len(js_files) > 0, "frontend/dist/assets must contain compiled JS files"
    assert len(css_files) > 0, "frontend/dist/assets must contain compiled CSS files"
    for jf in js_files:
        assert os.path.getsize(os.path.join(assets_dir, jf)) > 1000


# ─────────────────────────────────────────────────────────────────────────────
# 18. Option-A Window-Start Snapshot Semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_opportunity_window_start_snapshot_semantics():
    """TEST 18: Option-A snapshot semantics — window-start frame sets opportunity scores; subsequent frames share them."""
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        simulation_mode=True,
        opportunity_window_duration_s=1.0,
    )
    base_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    # Frame 0: High quality, normal lighting
    bright_img = np.full((480, 640, 3), 180, dtype=np.uint8)
    frame0 = CameraFrame(
        frame_id="FRAME-W0",
        camera_id="C1",
        timestamp=base_time,
        width=640,
        height=480,
        image=bright_img,
        frame_index=1,
    )
    res0 = pipeline.process_frame(frame0)
    opp0 = res0.opportunity
    init_opp_id = opp0.opportunity_id
    init_illum_score = opp0.illumination_score
    init_opp_score = opp0.opportunity_score

    # Frame 1: Low quality / dark image 200ms later (within 1.0s window)
    dark_img = np.full((480, 640, 3), 20, dtype=np.uint8)
    frame1 = CameraFrame(
        frame_id="FRAME-W1",
        camera_id="C1",
        timestamp=base_time + timedelta(milliseconds=200),
        width=640,
        height=480,
        image=dark_img,
        frame_index=2,
    )
    res1 = pipeline.process_frame(frame1)

    # Frame 1 must share the SAME opportunity
    assert res1.opportunity.opportunity_id == init_opp_id
    # Option-A snapshot semantics: opportunity scores do not mutate mid-window
    assert res1.opportunity.illumination_score == init_illum_score
    assert res1.opportunity.opportunity_score == init_opp_score
    # Per-frame quality signals DO capture Frame 1's actual degraded conditions
    assert res1.quality_signals.illumination_score < res0.quality_signals.illumination_score

    # Frame 2: 1.5s later (past 1.0s window) -> opens a NEW opportunity window
    frame2 = CameraFrame(
        frame_id="FRAME-W2",
        camera_id="C1",
        timestamp=base_time + timedelta(milliseconds=1500),
        width=640,
        height=480,
        image=dark_img,
        frame_index=3,
    )
    res2 = pipeline.process_frame(frame2)
    assert res2.opportunity.opportunity_id != init_opp_id, "Past window expiration, new opportunity must be created"
    assert res2.opportunity.window_start == frame2.timestamp


# ─────────────────────────────────────────────────────────────────────────────
# 19. Pipeline Output Determinism
# ─────────────────────────────────────────────────────────────────────────────

def test_pipeline_output_determinism():
    """TEST 19: Identical seed and base_timestamp produce identical pipeline outputs across independent runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "det_test.mp4")
        generate_sample_road_video(output_path=video_path, num_frames=6, seed=42)

        base_ts = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

        pipe1 = VideoPerceptionPipeline(bus_id="BUS-001", simulation_mode=True, deterministic=True)
        results1 = pipe1.process_video_file(video_path, max_frames=4, base_timestamp=base_ts)

        pipe2 = VideoPerceptionPipeline(bus_id="BUS-001", simulation_mode=True, deterministic=True)
        results2 = pipe2.process_video_file(video_path, max_frames=4, base_timestamp=base_ts)

        assert len(results1) == len(results2) == 4
        for r1, r2 in zip(results1, results2):
            assert r1.frame_id == r2.frame_id
            assert r1.timestamp == r2.timestamp
            assert r1.opportunity.opportunity_id == r2.opportunity.opportunity_id
            assert len(r1.detections) == len(r2.detections)
            assert len(r1.events) == len(r2.events)
            for ev1, ev2 in zip(r1.events, r2.events):
                assert ev1.event_id == ev2.event_id
                assert ev1.trace_id == ev2.trace_id
                assert ev1.payload_hash == ev2.payload_hash


# ─────────────────────────────────────────────────────────────────────────────
# 20. GNSS Accuracy Semantic Guard
# ─────────────────────────────────────────────────────────────────────────────

def test_gnss_accuracy_none_semantics():
    """TEST 20: Real GNSS fix with accuracy_m=None results in gps_quality=0.0 and INVALID opportunity."""
    from edge.app.opportunity.opportunity_evaluator import OpportunityEvaluator
    from edge.app.hal.simulated import SimulatedIMUProvider

    evaluator = OpportunityEvaluator(
        bus_id="BUS-001",
        device_id="DEV-001",
        camera_id="CAMERA-FRONT-01",
        deterministic=True,
    )
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    # Real fix, but accuracy estimate unavailable
    gnss = GNSSReading(
        latitude=17.4435,
        longitude=78.3772,
        altitude_m=500.0,
        accuracy_m=None,  # No accuracy reported
        heading_deg=45.0,
        timestamp=now,
        fix_quality=1,
    )
    imu = SimulatedIMUProvider().read()
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = CameraFrame("F-NOACC", "C1", now, 640, 480, image=dummy_img)

    opp = evaluator.evaluate(
        sensing_pass_id="PASS-001",
        window_start=now,
        window_end=now + timedelta(seconds=1),
        gnss=gnss,
        imu=imu,
        frame=frame,
    )

    assert opp.gps_quality_score == 0.0, "Unreported GNSS accuracy must receive 0.0 quality score, not fabricated value"
    assert opp.validity_status == ValidityStatus.INVALID, "Opportunity without GNSS accuracy must be marked INVALID"
    assert opp.fov_valid is False
    assert any("GNSS accuracy unavailable" in reason for reason in opp.invalid_reasons)


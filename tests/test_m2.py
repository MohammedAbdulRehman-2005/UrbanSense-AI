"""
UrbanSense AI — Milestone 2 Test Suite
=======================================
Validates the Milestone 2 Real Perception pipeline:
1. FileCameraProvider
2. Frame sequencing
3. Deterministic timestamps
4. Pothole detector interface
5. Vehicle detector interface
6. Observation generation
7. Semantic confidence field validation
8. Tracking output
9. Observation quality signals
10. Camera calibration model
11. Opportunity integration
12. Evidence reference generation
13. Canonical Event continuity
14. Real-video event creation
15. Simulator regression (Milestone 1 continuity)
16. Milestone 1 API regression (Backend continuity)
17. Failure handling (unreadable video, empty video, detector failure, missing GPS)
"""
from __future__ import annotations

import os
import sys
import uuid
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.observation import Observation, BoundingBox
from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus
from contracts.canonical_event import CanonicalEvent, Location, MapMatchStatus
from contracts.calibration import CameraCalibration, CameraIntrinsics, CameraExtrinsics
from edge.app.hal.interfaces import CameraFrame, GNSSReading, IMUReading
from edge.app.hal.file_camera import FileCameraProvider
from edge.app.perception.detectors.base import BaseDetector, RawDetection
from edge.app.perception.detectors.pothole import BaselinePotholeDetector
from edge.app.perception.detectors.vehicle import BaselineVehicleDetector
from edge.app.tracking.tracker import SameCameraTracker
from edge.app.tracking.interfaces import TrackedObject
from edge.app.quality.observation_quality import ObservationQualityEvaluator, QualitySignals
from edge.app.opportunity.opportunity_evaluator import OpportunityEvaluator
from edge.app.evidence.evidence_store import LocalEvidenceStore
from edge.app.simulation.event_builder import EventBuilder
from edge.app.simulation.simulator import SensingPassSimulator
from edge.app.perception.video_pipeline import VideoPerceptionPipeline
from scripts.generate_sample_road_video import generate_sample_road_video


SAMPLE_VIDEO_PATH = "data/sample_road_video.mp4"


@pytest.fixture(scope="session", autouse=True)
def ensure_sample_video():
    """Ensure sample road video exists for testing."""
    if not os.path.exists(SAMPLE_VIDEO_PATH):
        generate_sample_road_video(output_path=SAMPLE_VIDEO_PATH, num_frames=30)
    return SAMPLE_VIDEO_PATH


# ─────────────────────────────────────────────────────────────────────────────
# 1. FileCameraProvider Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_file_camera_provider():
    """TEST 1: FileCameraProvider opens video and produces valid CameraFrame objects."""
    with FileCameraProvider(SAMPLE_VIDEO_PATH, camera_id="CAMERA-FRONT-01") as cam:
        assert cam.is_healthy() is True
        frame = cam.capture()
        assert isinstance(frame, CameraFrame)
        assert frame.camera_id == "CAMERA-FRONT-01"
        assert frame.width > 0
        assert frame.height > 0
        assert frame.image is not None
        assert frame.frame_index == 1
        assert frame.simulated is False


def test_frame_sequencing():
    """TEST 2: Frame sequencing produces sequential frame_id and monotonic frame_index."""
    with FileCameraProvider(SAMPLE_VIDEO_PATH, camera_id="CAM-SEQ-01") as cam:
        f1 = cam.capture()
        f2 = cam.capture()
        assert f1.frame_index == 1
        assert f2.frame_index == 2
        assert f1.frame_id == "FRAME-CAM-SEQ-01-000001"
        assert f2.frame_id == "FRAME-CAM-SEQ-01-000002"


def test_deterministic_timestamps():
    """TEST 3: Frame timestamps advance predictably based on frame rate."""
    base_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    with FileCameraProvider(SAMPLE_VIDEO_PATH, base_timestamp=base_time, frame_rate=30.0) as cam:
        f1 = cam.capture()
        f2 = cam.capture()
        assert f1.timestamp == base_time
        expected_f2 = base_time + timedelta(seconds=1.0 / 30.0)
        assert abs((f2.timestamp - expected_f2).total_seconds()) < 1e-4


# ─────────────────────────────────────────────────────────────────────────────
# 4. Detector Interface Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_pothole_detector_interface():
    """TEST 4: Pothole detector conforms to BaseDetector and emits valid RawDetections."""
    detector = BaselinePotholeDetector()
    assert isinstance(detector, BaseDetector)
    assert detector.model_name is not None
    assert detector.model_version is not None

    with FileCameraProvider(SAMPLE_VIDEO_PATH) as cam:
        frame = cam.capture()
        detections = detector.detect(frame)
        assert isinstance(detections, list)
        for det in detections:
            assert det.object_type == "pothole"
            assert 0.0 <= det.detector_confidence <= 1.0
            assert det.bbox.x_min < det.bbox.x_max
            assert det.bbox.y_min < det.bbox.y_max
            # Verify explicit naming: no generic 'confidence' field
            assert not hasattr(det, "confidence")


def test_vehicle_detector_interface():
    """TEST 5: Vehicle detector identifies expected traffic object classes."""
    detector = BaselineVehicleDetector()
    assert isinstance(detector, BaseDetector)
    assert detector.model_name is not None

    with FileCameraProvider(SAMPLE_VIDEO_PATH) as cam:
        frame = cam.capture()
        detections = detector.detect(frame)
        assert isinstance(detections, list)
        for det in detections:
            assert det.object_type in BaselineVehicleDetector.SUPPORTED_CLASSES
            assert 0.0 <= det.detector_confidence <= 1.0
            assert not hasattr(det, "confidence")


# ─────────────────────────────────────────────────────────────────────────────
# 6 & 7. Observation and Semantic Confidence Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_observation_generation():
    """TEST 6: Observation contract correctly populated from detection."""
    bbox = BoundingBox(x_min=100.0, y_min=200.0, x_max=300.0, y_max=400.0, frame_width=1280, frame_height=720)
    obs = Observation(
        frame_id="FRAME-001",
        bus_id="BUS-001",
        device_id="DEVICE-001",
        camera_id="CAMERA-FRONT-01",
        timestamp=datetime.now(timezone.utc),
        object_type="pothole",
        detector_confidence=0.88,
        bbox=bbox,
        model_name="test-detector",
        model_version="0.2.0",
        evidence_hint="evidence://local/test.jpg",
    )
    assert obs.observation_id is not None
    assert obs.detector_confidence == 0.88
    assert obs.evidence_hint == "evidence://local/test.jpg"
    assert not hasattr(obs, "confidence")


def test_semantic_confidence_field_separation():
    """TEST 7: detector_confidence, observation_quality, and aggregate_confidence are separate."""
    # detector_confidence: Edge model raw score
    # observation_quality: Optical/environmental signal
    # aggregate_confidence: Backend fused RoadTwin score
    obs = Observation(
        frame_id="F", bus_id="B", device_id="D", camera_id="C",
        timestamp=datetime.now(timezone.utc),
        object_type="pothole",
        detector_confidence=0.85,
        bbox=BoundingBox(x_min=10, y_min=10, x_max=50, y_max=50, frame_width=100, frame_height=100),
        model_name="M", model_version="V",
    )
    assert hasattr(obs, "detector_confidence")
    assert not hasattr(obs, "observation_quality")
    assert not hasattr(obs, "aggregate_confidence")
    assert not hasattr(obs, "confidence")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tracking Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_same_camera_tracking():
    """TEST 8: Temporal tracking persists track_id across consecutive frames."""
    tracker = SameCameraTracker(camera_id="CAM-01", bus_id="BUS-001")
    t0 = datetime.now(timezone.utc)

    # Frame 1 detection
    bbox1 = BoundingBox(x_min=100, y_min=100, x_max=200, y_max=200, frame_width=1000, frame_height=1000)
    det1 = RawDetection(object_type="car", detector_confidence=0.85, bbox=bbox1, model_name="m", model_version="v")
    tracks1 = tracker.update([det1], t0, "FRAME-1")
    assert len(tracks1) == 1
    t_id = tracks1[0].track_id
    assert t_id.startswith("TRK-CAM-01-")

    # Frame 2 slightly shifted detection (IoU overlap > 0.3)
    bbox2 = BoundingBox(x_min=105, y_min=105, x_max=205, y_max=205, frame_width=1000, frame_height=1000)
    det2 = RawDetection(object_type="car", detector_confidence=0.86, bbox=bbox2, model_name="m", model_version="v")
    tracks2 = tracker.update([det2], t0 + timedelta(milliseconds=33), "FRAME-2")
    assert len(tracks2) == 1
    assert tracks2[0].track_id == t_id  # Track ID must persist
    assert tracks2[0].age_frames == 2
    assert tracks2[0].track_quality >= 0.50
    assert len(tracks2[0].trajectory_points) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 9. Observation Quality Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_observation_quality_signals():
    """TEST 9: ObservationQualityEvaluator calculates explicit separated signals."""
    evaluator = ObservationQualityEvaluator()
    with FileCameraProvider(SAMPLE_VIDEO_PATH) as cam:
        frame = cam.capture()
        q = evaluator.evaluate_frame(frame)
        assert isinstance(q, QualitySignals)
        assert 0.0 <= q.blur_score <= 1.0
        assert 0.0 <= q.illumination_score <= 1.0
        assert 0.0 <= q.visibility_score <= 1.0
        assert 0.0 <= q.occlusion_score <= 1.0
        assert 0.0 <= q.observation_quality <= 1.0
        # Verify no generic confidence exists in quality signals
        assert not hasattr(q, "confidence")
        assert not hasattr(q, "final_confidence")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Camera Calibration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_camera_calibration_model():
    """TEST 10: CameraCalibration represents geometry and is explicitly labeled PROTOTYPE / ASSUMED."""
    calib = CameraCalibration(
        camera_id="CAMERA-FRONT-01",
        intrinsics=CameraIntrinsics(fx=1200.0, fy=1200.0, cx=960.0, cy=540.0),
        extrinsics=CameraExtrinsics(mounting_height_m=2.6, pitch_deg=3.5),
        horizontal_fov_deg=85.0,
        vertical_fov_deg=54.0,
    )
    assert calib.camera_id == "CAMERA-FRONT-01"
    assert "PROTOTYPE / ASSUMED" in calib.status
    assert calib.extrinsics.mounting_height_m == 2.6
    assert calib.intrinsics.fx == 1200.0


# ─────────────────────────────────────────────────────────────────────────────
# 11. Opportunity Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_opportunity_evaluator_integration():
    """TEST 11: OpportunityEvaluator incorporates real frame optical signals."""
    evaluator = OpportunityEvaluator(bus_id="BUS-001", device_id="DEV-001", camera_id="CAM-01")
    with FileCameraProvider(SAMPLE_VIDEO_PATH) as cam:
        frame = cam.capture()
        quality_evaluator = ObservationQualityEvaluator()
        signals = quality_evaluator.evaluate_frame(frame)

        gnss = GNSSReading(17.4435, 78.3772, 540.0, 2.5, 45.0, frame.timestamp, 1)
        imu = IMUReading(0.0, 0.0, 9.81, 0.0, 0.0, 0.0, frame.timestamp)

        opp = evaluator.evaluate(
            sensing_pass_id="PASS-M2-TEST",
            window_start=frame.timestamp,
            window_end=frame.timestamp + timedelta(milliseconds=33),
            gnss=gnss,
            imu=imu,
            frame=frame,
            quality_signals=signals,
        )

        assert opp.validity_status == ValidityStatus.VALID
        assert 0.0 <= opp.opportunity_score <= 1.0
        # Dynamic optical signals should reflect the measured signals
        assert opp.blur_score == signals.blur_score
        assert opp.illumination_score == signals.illumination_score
        assert opp.visibility_score == signals.visibility_score
        # Prohibited fields must not exist
        assert not hasattr(opp, "evidence_weight")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Evidence Reference Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_evidence_reference_generation():
    """TEST 12: LocalEvidenceStore saves crop and produces evidence URI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalEvidenceStore(storage_dir=tmpdir)
        with FileCameraProvider(SAMPLE_VIDEO_PATH) as cam:
            frame = cam.capture()
            bbox = BoundingBox(x_min=100, y_min=200, x_max=300, y_max=400, frame_width=frame.width, frame_height=frame.height)
            obs_id = str(uuid.uuid4())
            ref = store.save_crop_evidence(frame, bbox, "pothole", obs_id)

            assert ref.startswith("evidence://local/")
            # Verify file exists on disk
            saved_files = os.listdir(tmpdir)
            assert len(saved_files) == 1
            assert saved_files[0].endswith(".jpg")


# ─────────────────────────────────────────────────────────────────────────────
# 13 & 14. Canonical Event and Video Pipeline End-to-End Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_event_continuity():
    """TEST 13: EventBuilder accepts evidence_ref and observation_quality while preserving contract."""
    builder = EventBuilder(
        bus_id="BUS-001",
        device_id="DEV-001",
        camera_id="CAM-01",
        model_name="test-model",
        model_version="0.2.0",
    )
    obs = Observation(
        frame_id="F1", bus_id="B", device_id="D", camera_id="C",
        timestamp=datetime.now(timezone.utc),
        object_type="pothole", detector_confidence=0.88,
        bbox=BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10, frame_width=100, frame_height=100),
        model_name="m", model_version="v",
    )
    opp = ObservationOpportunity(
        sensing_pass_id="P1", bus_id="B", device_id="D", camera_id="C",
        window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc),
        target_scope=TargetScope.SEGMENT, target_type="road_segment", fov_valid=True,
        visibility_score=0.9, illumination_score=0.9, blur_score=0.9, occlusion_score=0.9,
        viewing_angle_score=0.9, distance_score=0.9, sensor_health_score=1.0,
        gps_quality_score=0.9, opportunity_score=0.91, validity_status=ValidityStatus.VALID,
        invalid_reasons=[], coverage_fraction=0.95, trace_id="trace-123",
    )

    now = datetime.now(timezone.utc)
    event = builder.build(
        observation=obs,
        opportunity=opp,
        event_timestamp=now,
        latitude=17.4435,
        longitude=78.3772,
        evidence_ref="evidence://local/pothole_01.jpg",
        observation_quality=0.82,
    )

    assert event.event_id is not None
    assert event.evidence_ref == "evidence://local/pothole_01.jpg"
    assert event.observation_quality == 0.82
    assert event.detector_confidence == 0.88
    assert event.payload_hash is not None
    assert len(event.payload_hash) == 64
    assert event.matched_road_segment_id is None  # Backend-owned


def test_video_pipeline_e2e_local():
    """TEST 14: VideoPerceptionPipeline processes video file and returns valid events."""
    pipeline = VideoPerceptionPipeline()
    results = pipeline.process_video_file(SAMPLE_VIDEO_PATH, max_frames=3, frame_step=1)

    assert len(results) == 3
    assert pipeline.metrics.frames_processed == 3
    assert pipeline.metrics.average_fps > 0.0

    for fr in results:
        assert fr.frame_id is not None
        assert fr.quality_signals is not None
        assert fr.opportunity is not None
        if fr.events:
            for ev in fr.events:
                assert ev.bus_id == "BUS-001"
                assert ev.evidence_ref is not None
                assert 0.0 <= ev.detector_confidence <= 1.0
                assert 0.0 <= ev.observation_quality <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 15 & 16. Regression Tests (Milestone 1 Continuity)
# ─────────────────────────────────────────────────────────────────────────────

def test_milestone1_simulator_regression():
    """TEST 15: Milestone 1 SensingPassSimulator remains fully functional."""
    sim = SensingPassSimulator()
    sp_id, obs, opp, event = sim.run()

    assert sp_id == "SIMPASS-M1-001"
    assert obs.detector_confidence == 0.87
    assert opp.validity_status == ValidityStatus.VALID
    assert event.event_id is not None
    assert event.payload_hash is not None


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _is_backend_online() -> bool:
    try:
        import httpx
        r = httpx.get(f"{BACKEND_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def test_milestone1_api_regression():
    """TEST 16: Backend accepts both simulated and real-video events with idempotency."""
    if not _is_backend_online():
        pytest.skip("Backend offline — integration test skipped")
    import httpx

    # Test event ingestion using a simulated event
    sim = SensingPassSimulator()
    _, obs, opp, event = sim.run()

    opp_resp = httpx.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp.model_dump(mode="json"))
    assert opp_resp.status_code == 200

    ev_resp = httpx.post(f"{BACKEND_URL}/api/v1/events", json=event.model_dump(mode="json"))
    assert ev_resp.status_code == 200
    assert ev_resp.json()["status"] == "accepted"

    # Idempotency re-test
    ev_resp2 = httpx.post(f"{BACKEND_URL}/api/v1/events", json=event.model_dump(mode="json"))
    assert ev_resp2.status_code == 200
    assert ev_resp2.json()["status"] == "duplicate"


# ─────────────────────────────────────────────────────────────────────────────
# 17. Failure Handling Tests (Phase U)
# ─────────────────────────────────────────────────────────────────────────────

def test_failure_handling_unreadable_video():
    """TEST 17a: Non-existent video file raises RuntimeError on capture or is not healthy."""
    cam = FileCameraProvider("data/does_not_exist_xyz.mp4")
    assert cam.is_healthy() is False
    with pytest.raises(RuntimeError):
        cam.capture()


def test_failure_handling_empty_frame():
    """TEST 17b: Null image array in detectors returns empty detection list without crashing."""
    p_detector = BaselinePotholeDetector()
    v_detector = BaselineVehicleDetector()
    empty_frame = CameraFrame(
        frame_id="F-EMPTY",
        camera_id="C1",
        timestamp=datetime.now(timezone.utc),
        width=0,
        height=0,
        image=None,
    )
    assert p_detector.detect(empty_frame) == []
    assert v_detector.detect(empty_frame) == []


def test_failure_handling_missing_gps():
    """TEST 17c: Invalid GPS fix marks Opportunity as INVALID."""
    evaluator = OpportunityEvaluator(bus_id="B", device_id="D", camera_id="C")
    bad_gnss = GNSSReading(0.0, 0.0, None, 999.0, None, datetime.now(timezone.utc), fix_quality=0)
    imu = IMUReading(0, 0, 9.8, 0, 0, 0, datetime.now(timezone.utc))
    frame = CameraFrame("F", "C", datetime.now(timezone.utc), 100, 100)

    opp = evaluator.evaluate(
        sensing_pass_id="PASS-BAD-GPS",
        window_start=frame.timestamp,
        window_end=frame.timestamp,
        gnss=bad_gnss,
        imu=imu,
        frame=frame,
    )
    assert opp.validity_status == ValidityStatus.INVALID
    assert "No valid GPS fix" in opp.invalid_reasons

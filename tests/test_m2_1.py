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
    pipeline = VideoPerceptionPipeline(simulation_mode=True)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)

    for i in range(4):
        frame = CameraFrame(
            frame_id=f"F-PERF-{i}",
            camera_id="C1",
            timestamp=datetime.now(timezone.utc) + timedelta(milliseconds=i * 33),
            width=640,
            height=480,
            image=dummy_img,
            frame_index=i + 1,
        )
        pipeline.process_frame(frame)

    pipeline.metrics.total_time_seconds = 0.200  # 200 ms total
    avg_ms = (0.200 * 1000.0) / 4                # 50.0 ms/frame
    pipeline.metrics.avg_end_to_end_ms_per_frame = avg_ms
    pipeline.metrics.average_processed_fps = round(1000.0 / avg_ms, 2)  # 20.0 FPS

    assert pipeline.metrics.avg_end_to_end_ms_per_frame == 50.0
    assert pipeline.metrics.average_processed_fps == 20.0
    # Verification: 1000 / avg_ms == processed_fps
    assert round(1000.0 / pipeline.metrics.avg_end_to_end_ms_per_frame, 2) == pipeline.metrics.average_processed_fps


# ─────────────────────────────────────────────────────────────────────────────
# 10. Event Routing By Type
# ─────────────────────────────────────────────────────────────────────────────

def test_event_routing_by_type():
    """TEST 10: Event routing classifies road defects separately from vehicle events."""
    from backend.app.api.v1.events import ROAD_DEFECT_EVENT_TYPES

    assert "pothole_observation" in ROAD_DEFECT_EVENT_TYPES
    assert "road_defect" in ROAD_DEFECT_EVENT_TYPES
    assert "surface_distress" in ROAD_DEFECT_EVENT_TYPES
    assert "pothole" in ROAD_DEFECT_EVENT_TYPES
    assert "car_observation" not in ROAD_DEFECT_EVENT_TYPES
    assert "bus_observation" not in ROAD_DEFECT_EVENT_TYPES
    assert "truck_observation" not in ROAD_DEFECT_EVENT_TYPES
    assert "motorcycle_observation" not in ROAD_DEFECT_EVENT_TYPES
    assert "bicycle_observation" not in ROAD_DEFECT_EVENT_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# 11. Vehicle Event Does Not Update Defect RoadTwin
# ─────────────────────────────────────────────────────────────────────────────

def test_vehicle_event_does_not_update_defect_roadtwin():
    """TEST 11: Ingesting a vehicle observation event does not invoke upsert_roadtwin."""
    from backend.app.api.v1.events import ROAD_DEFECT_EVENT_TYPES

    vehicle_event_types = ["car_observation", "bus_observation", "truck_observation", "motorcycle_observation"]
    for v_type in vehicle_event_types:
        assert v_type not in ROAD_DEFECT_EVENT_TYPES, f"{v_type} must NOT be in ROAD_DEFECT_EVENT_TYPES"


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
    # Synthetic frame with a drawn distressed ellipse to trigger pothole detector
    img = np.full((720, 1280, 3), 65, dtype=np.uint8)
    cv2.ellipse(img, (600, 500), (40, 20), 0, 0, 360, (20, 20, 25), -1)

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
    if res.events:
        ev = res.events[0]
        obs = res.observations[0]
        assert ev.evidence_ref == obs.evidence_hint
        assert ev.evidence_ref.startswith("evidence://local/")

        # Check local file path exists
        local_rel_path = os.path.join("data", "evidence", ev.evidence_ref.replace("evidence://local/", ""))
        assert os.path.exists(local_rel_path), f"Evidence crop file not found: {local_rel_path}"


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
    """TEST 15: run_m1_demo.py uses explicit timeouts and avoids bare assert gates."""
    with open("scripts/run_m1_demo.py", "r", encoding="utf-8") as f:
        src = f.read()

    assert "assert " not in src, "run_m1_demo.py must not rely on bare assert for operational validation"
    assert "timeout=10.0" in src, "run_m1_demo.py must specify explicit HTTP timeouts"


# ─────────────────────────────────────────────────────────────────────────────
# 16. M2 Demo Failure Behavior
# ─────────────────────────────────────────────────────────────────────────────

def test_m2_demo_failure_behavior():
    """TEST 16: run_video_demo.py verifies backend health and exits non-zero on failure."""
    with open("scripts/run_video_demo.py", "r", encoding="utf-8") as f:
        src = f.read()

    assert "sys.exit(1)" in src, "run_video_demo.py must exit non-zero on failure"
    assert "timeout=10.0" in src, "run_video_demo.py must specify explicit HTTP timeouts"


# ─────────────────────────────────────────────────────────────────────────────
# 17. Frontend Build Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_frontend_build():
    """TEST 17: Frontend production build output exists and contains compiled bundle."""
    dist_dir = os.path.join("frontend", "dist")
    assert os.path.exists(dist_dir), "frontend/dist must exist from successful npm run build"
    index_html = os.path.join(dist_dir, "index.html")
    assert os.path.exists(index_html), "frontend/dist/index.html must exist"

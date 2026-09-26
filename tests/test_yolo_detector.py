"""
UrbanSense AI — YOLO Road Defect Detector Integration Tests
============================================================
Validates the trained YOLOv11 deep learning detector integrated into the
edge perception pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
import pytest

from edge.app.hal.interfaces import CameraFrame, GNSSReading
from edge.app.perception.detectors.yolo_detector import (
    YOLORoadDefectDetector,
    RDD_TO_URBANSENSE_DEFECT_MAP,
)
from edge.app.perception.detectors.vehicle import BaselineVehicleDetector
from edge.app.perception.video_pipeline import VideoPerceptionPipeline

SAMPLE_IMG_PATH = Path("datasets/India/India/train/images/India_000005.jpg")


class TestYOLORoadDefectDetector:
    """Unit and functional tests for the trained YOLO road defect detector."""

    def test_yolo_detector_loads_weights(self):
        detector = YOLORoadDefectDetector()
        assert detector.is_loaded is True
        assert detector.model_path is not None
        assert detector.model_path.exists()
        assert detector.model_name == "urbansense-yolo11n-rdd2022"
        assert detector.model_version == "1.0.0-candidate_b"

    def test_yolo_detector_detects_pothole_on_real_image(self):
        if not SAMPLE_IMG_PATH.exists():
            pytest.skip("Sample image not found on disk")

        detector = YOLORoadDefectDetector(confidence_threshold=0.25)
        img = cv2.imread(str(SAMPLE_IMG_PATH))
        frame = CameraFrame(
            frame_id="frame-pothole-01",
            camera_id="CAMERA-FRONT-01",
            timestamp=datetime.now(timezone.utc),
            image=img,
            width=img.shape[1],
            height=img.shape[0],
        )

        detections = detector.detect(frame)
        assert len(detections) > 0

        # Find pothole detection
        potholes = [d for d in detections if d.object_type == "pothole"]
        assert len(potholes) >= 1
        top_pothole = max(potholes, key=lambda x: x.detector_confidence)
        assert top_pothole.detector_confidence >= 0.70
        assert top_pothole.bbox.x_min < top_pothole.bbox.x_max
        assert top_pothole.bbox.y_min < top_pothole.bbox.y_max
        assert top_pothole.bbox.frame_width == 720
        assert top_pothole.bbox.frame_height == 720

    def test_rdd_class_mapping(self):
        assert RDD_TO_URBANSENSE_DEFECT_MAP["D40"] == "pothole"
        assert RDD_TO_URBANSENSE_DEFECT_MAP["D20"] == "alligator_crack"
        assert RDD_TO_URBANSENSE_DEFECT_MAP["D00"] == "longitudinal_crack"
        assert RDD_TO_URBANSENSE_DEFECT_MAP["D10"] == "transverse_crack"

    def test_empty_or_corrupt_frame_handling(self):
        detector = YOLORoadDefectDetector()
        empty_frame = CameraFrame(
            frame_id="empty-01",
            camera_id="CAMERA-FRONT-01",
            timestamp=datetime.now(timezone.utc),
            image=None,
            width=0,
            height=0,
        )
        assert detector.detect(empty_frame) == []

        zero_size_frame = CameraFrame(
            frame_id="zero-01",
            camera_id="CAMERA-FRONT-01",
            timestamp=datetime.now(timezone.utc),
            image=np.zeros((0, 0, 3), dtype=np.uint8),
            width=0,
            height=0,
        )
        assert detector.detect(zero_size_frame) == []

    def test_allowed_classes_filter(self):
        if not SAMPLE_IMG_PATH.exists():
            pytest.skip("Sample image not found on disk")

        # Restrict strictly to pothole
        detector = YOLORoadDefectDetector(confidence_threshold=0.20, allowed_classes={"pothole"})
        img = cv2.imread(str(SAMPLE_IMG_PATH))
        frame = CameraFrame(
            frame_id="frame-filter-01",
            camera_id="CAMERA-FRONT-01",
            timestamp=datetime.now(timezone.utc),
            image=img,
            width=img.shape[1],
            height=img.shape[0],
        )

        detections = detector.detect(frame)
        for d in detections:
            assert d.object_type == "pothole"

    def test_video_pipeline_integration(self):
        if not SAMPLE_IMG_PATH.exists():
            pytest.skip("Sample image not found on disk")

        class MockGNSS:
            def read(self):
                return GNSSReading(
                    latitude=17.4435,
                    longitude=78.3772,
                    altitude_m=540.0,
                    accuracy_m=1.2,
                    heading_deg=90.0,
                    timestamp=datetime.now(timezone.utc),
                    fix_quality=1,
                )

        pipeline = VideoPerceptionPipeline(
            bus_id="BUS-001",
            device_id="DEVICE-001",
            camera_id="CAMERA-FRONT-01",
            detectors=[YOLORoadDefectDetector(confidence_threshold=0.30), BaselineVehicleDetector()],
            gnss_provider=MockGNSS(),
            deterministic=True,
        )

        img = cv2.imread(str(SAMPLE_IMG_PATH))
        frame = CameraFrame(
            frame_id="test-e2e-001",
            camera_id="CAMERA-FRONT-01",
            timestamp=datetime.now(timezone.utc),
            image=img,
            width=img.shape[1],
            height=img.shape[0],
        )

        result = pipeline.process_frame(frame)
        assert len(result.detections) >= 1
        assert len(result.active_tracks) >= 1
        assert len(result.observations) >= 1
        assert len(result.events) >= 1

        pothole_events = [e for e in result.events if e.event_type == "pothole_observation"]
        assert len(pothole_events) >= 1
        pevt = pothole_events[0]
        assert pevt.detector_confidence >= 0.70
        assert pevt.location.latitude == 17.4435
        assert pevt.location.longitude == 78.3772

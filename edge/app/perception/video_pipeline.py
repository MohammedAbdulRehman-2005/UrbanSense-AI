"""
UrbanSense AI — Recorded Video Perception Pipeline (Milestone 2)
================================================================
Processes recorded road video through perception, tracking, quality evaluation,
opportunity evaluation, and canonical event generation.

Pipeline flow:
    Video Frame (via FileCameraProvider)
    → Object Detection (Pothole / Vehicle Detectors)
    → Same-Camera Tracking
    → Observation Quality Evaluation
    → Opportunity Evaluation (reusing OpportunityEvaluator)
    → Evidence Artifact Generation (LocalEvidenceStore)
    → Canonical Event Generation (EventBuilder)

HARD SCOPE BOUNDARY:
- Do NOT implement multi-bus fusion.
- Do NOT claim cross-bus vehicle identity.
- Do NOT calculate evidence_weight or advance RoadTwin past OBSERVED.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Iterator
import cv2

from contracts.observation import Observation
from contracts.opportunity import ObservationOpportunity, TargetScope
from contracts.canonical_event import CanonicalEvent
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


@dataclass
class PipelineMetrics:
    """Telemetry and timing metrics for a video processing run."""
    frames_processed: int = 0
    detections_found: int = 0
    events_generated: int = 0
    total_time_seconds: float = 0.0
    average_fps: float = 0.0
    inference_time_ms: float = 0.0
    tracking_time_ms: float = 0.0
    quality_eval_time_ms: float = 0.0


@dataclass
class ProcessedFrameResult:
    """Result for a single processed frame."""
    frame_id: str
    frame_index: int
    timestamp: datetime
    detections: List[RawDetection]
    active_tracks: List[TrackedObject]
    quality_signals: QualitySignals
    opportunity: ObservationOpportunity
    observations: List[Observation]
    events: List[CanonicalEvent]


class VideoPerceptionPipeline:
    """
    Coordinates perception processing over a video stream or recorded file.
    """

    def __init__(
        self,
        bus_id: str = "BUS-001",
        device_id: str = "DEVICE-001",
        camera_id: str = "CAMERA-FRONT-01",
        detectors: Optional[List[BaseDetector]] = None,
        tracker: Optional[SameCameraTracker] = None,
        evidence_store: Optional[LocalEvidenceStore] = None,
        quality_evaluator: Optional[ObservationQualityEvaluator] = None,
        opportunity_evaluator: Optional[OpportunityEvaluator] = None,
        event_builder: Optional[EventBuilder] = None,
        sensing_pass_id: Optional[str] = None,
    ):
        self.bus_id = bus_id
        self.device_id = device_id
        self.camera_id = camera_id
        self.sensing_pass_id = sensing_pass_id or f"VIDPASS-{uuid.uuid4().hex[:8].upper()}"

        # Initialize perception modules
        self.detectors = detectors or [
            BaselinePotholeDetector(),
            BaselineVehicleDetector(),
        ]
        self.tracker = tracker or SameCameraTracker(camera_id=camera_id, bus_id=bus_id)
        self.evidence_store = evidence_store or LocalEvidenceStore()
        self.quality_evaluator = quality_evaluator or ObservationQualityEvaluator()
        self.opportunity_evaluator = opportunity_evaluator or OpportunityEvaluator(
            bus_id=bus_id, device_id=device_id, camera_id=camera_id
        )
        self.event_builder = event_builder or EventBuilder(
            bus_id=bus_id,
            device_id=device_id,
            camera_id=camera_id,
            model_name="urbansense-perception-ensemble",
            model_version="0.2.0-PROTOTYPE",
        )

        self.metrics = PipelineMetrics()

    def process_frame(
        self,
        frame: CameraFrame,
        gnss: Optional[GNSSReading] = None,
        imu: Optional[IMUReading] = None,
        edge_road_segment_hint: Optional[str] = "SEG-001-HINT",
        trace_id: Optional[str] = None,
    ) -> ProcessedFrameResult:
        """
        Process a single camera frame through the entire perception stack.
        """
        _trace_id = trace_id or str(uuid.uuid4())

        # Fallback GNSS and IMU for simulated/prototype navigation context
        _gnss = gnss or GNSSReading(
            latitude=17.4435,
            longitude=78.3772,
            altitude_m=542.0,
            accuracy_m=3.5,
            heading_deg=45.0,
            timestamp=frame.timestamp,
            fix_quality=1,
        )
        _imu = imu or IMUReading(
            accel_x=0.02,
            accel_y=-0.01,
            accel_z=9.81,
            gyro_x=0.001,
            gyro_y=-0.002,
            gyro_z=0.000,
            timestamp=frame.timestamp,
        )

        # 1. Optical Quality Evaluation
        t_q0 = time.perf_counter()
        quality_signals = self.quality_evaluator.evaluate_frame(frame)
        self.metrics.quality_eval_time_ms += (time.perf_counter() - t_q0) * 1000.0

        # 2. Opportunity Evaluation (Reusing existing OpportunityEvaluator)
        window_start = frame.timestamp
        window_end = frame.timestamp + timedelta(milliseconds=33)  # ~30fps frame interval
        opportunity = self.opportunity_evaluator.evaluate(
            sensing_pass_id=self.sensing_pass_id,
            window_start=window_start,
            window_end=window_end,
            gnss=_gnss,
            imu=_imu,
            frame=frame,
            target_scope=TargetScope.SEGMENT,
            target_type="road_segment",
            edge_road_segment_hint=edge_road_segment_hint,
            trace_id=_trace_id,
            quality_signals=quality_signals,
        )

        # 3. Model Inference (Pothole + Vehicle Detectors)
        t_inf0 = time.perf_counter()
        raw_detections: List[RawDetection] = []
        for detector in self.detectors:
            try:
                dets = detector.detect(frame)
                raw_detections.extend(dets)
            except Exception as e:
                # Graceful detector failure handling
                continue
        self.metrics.inference_time_ms += (time.perf_counter() - t_inf0) * 1000.0
        self.metrics.detections_found += len(raw_detections)

        # 4. Temporal Tracking
        t_trk0 = time.perf_counter()
        active_tracks = self.tracker.update(raw_detections, frame.timestamp, frame.frame_id)
        self.metrics.tracking_time_ms += (time.perf_counter() - t_trk0) * 1000.0

        # 5. Form Observations and Canonical Events for qualifying detections
        observations: List[Observation] = []
        events: List[CanonicalEvent] = []

        for det in raw_detections:
            obs_id = str(uuid.uuid4())

            # Evaluate localized crop quality
            crop_quality = self.quality_evaluator.evaluate_detection_crop(frame, det.bbox)

            # Save evidence artifact
            evidence_ref = self.evidence_store.save_crop_evidence(
                frame=frame,
                bbox=det.bbox,
                object_type=det.object_type,
                observation_id=obs_id,
            )

            # Build Observation contract
            observation = Observation(
                observation_id=obs_id,
                frame_id=frame.frame_id,
                bus_id=self.bus_id,
                device_id=self.device_id,
                camera_id=self.camera_id,
                timestamp=frame.timestamp,
                object_type=det.object_type,
                detector_confidence=det.detector_confidence,
                bbox=det.bbox,
                mask_reference=det.mask_reference,
                track_id=det.track_id,
                trajectory_reference=f"traj://{det.track_id}" if det.track_id else None,
                model_name=det.model_name,
                model_version=det.model_version,
                evidence_hint=evidence_ref,
            )
            observations.append(observation)

            # Build Canonical Event (for road distress / potholes, or qualifying vehicle events)
            event_type = f"{det.object_type}_observation"
            event = self.event_builder.build(
                observation=observation,
                opportunity=opportunity,
                event_timestamp=frame.timestamp,
                latitude=_gnss.latitude,
                longitude=_gnss.longitude,
                altitude_m=_gnss.altitude_m,
                accuracy_m=_gnss.accuracy_m,
                heading_deg=_gnss.heading_deg,
                event_type=event_type,
                edge_road_segment_hint=edge_road_segment_hint,
                trace_id=_trace_id,
                gps_quality=opportunity.gps_quality_score,
                evidence_ref=evidence_ref,
                observation_quality=crop_quality.observation_quality,
            )
            events.append(event)
            self.metrics.events_generated += 1

        self.metrics.frames_processed += 1

        return ProcessedFrameResult(
            frame_id=frame.frame_id,
            frame_index=frame.frame_index,
            timestamp=frame.timestamp,
            detections=raw_detections,
            active_tracks=active_tracks,
            quality_signals=quality_signals,
            opportunity=opportunity,
            observations=observations,
            events=events,
        )

    def process_video_file(
        self,
        video_path: str,
        max_frames: Optional[int] = None,
        frame_step: int = 1,
    ) -> List[ProcessedFrameResult]:
        """
        Process a recorded video file from end to end.
        """
        results: List[ProcessedFrameResult] = []
        t0 = time.perf_counter()

        with FileCameraProvider(video_path=video_path, camera_id=self.camera_id) as camera:
            for frame in camera.frames(step=frame_step):
                res = self.process_frame(frame)
                results.append(res)
                if max_frames and len(results) >= max_frames:
                    break

        total_time = time.perf_counter() - t0
        self.metrics.total_time_seconds = total_time
        if total_time > 0 and self.metrics.frames_processed > 0:
            self.metrics.average_fps = round(self.metrics.frames_processed / total_time, 2)

        return results

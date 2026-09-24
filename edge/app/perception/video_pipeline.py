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

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Iterator
import cv2

from contracts.observation import Observation
from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus
from contracts.canonical_event import CanonicalEvent
from edge.app.hal.interfaces import CameraFrame, GNSSReading, IMUReading, GNSSProvider, IMUProvider
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

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Telemetry and timing metrics for a video processing run."""
    frames_processed: int = 0
    detections_found: int = 0
    events_generated: int = 0
    detector_failures: int = 0
    total_time_seconds: float = 0.0
    average_processed_fps: float = 0.0
    avg_end_to_end_ms_per_frame: float = 0.0
    # Component timings (total ms accumulated):
    acquisition_time_ms: float = 0.0
    inference_time_ms: float = 0.0
    tracking_time_ms: float = 0.0
    quality_eval_time_ms: float = 0.0
    opportunity_eval_time_ms: float = 0.0
    evidence_and_event_time_ms: float = 0.0
    overhead_time_ms: float = 0.0
    # Backward compatibility alias:
    average_fps: float = 0.0


@dataclass
class DetectorExecutionResult:
    """Explicit observable execution result for a detector invocation."""
    detector_name: str
    success: bool
    detections: List[RawDetection] = field(default_factory=list)
    error_message: Optional[str] = None
    error_code: Optional[str] = None


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
    detector_results: List[DetectorExecutionResult] = field(default_factory=list)
    detector_errors: List[dict] = field(default_factory=list)


class VideoPerceptionPipeline:
    """
    Coordinates perception processing over a video stream or recorded file.
    
    Milestone 2.1 Hardening:
    - Deterministic ID generation mode (sequential VIDPASS-, TRACE-, OBS-, EVT-)
    - Meaningful opportunity window grouping (multiple frames/observations share one Opportunity)
    - Removal of silent GNSS/IMU fabrication (missing GNSS remains missing; HAL provider boundary respected)
    - Observable detector failures (exceptions recorded, not silently swallowed)
    - Mathematically consistent performance accounting (end-to-end vs component timings)
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
        gnss_provider: Optional[GNSSProvider] = None,
        imu_provider: Optional[IMUProvider] = None,
        simulation_mode: bool = False,
        deterministic: bool = False,
        opportunity_window_duration_s: float = 1.0,  # PROTOTYPE / CONFIGURABLE
    ):
        self.bus_id = bus_id
        self.device_id = device_id
        self.camera_id = camera_id
        self.simulation_mode = simulation_mode
        self.deterministic = deterministic
        self.opportunity_window_duration_s = opportunity_window_duration_s

        # Sensor providers (HAL boundary)
        self.gnss_provider = gnss_provider
        self.imu_provider = imu_provider

        # Monotonic counters for deterministic mode
        self._opp_seq = 0
        self._obs_seq = 0
        self._evt_seq = 0
        self._trace_seq = 0

        # Deterministic vs production sensing pass identity
        if self.deterministic:
            self.sensing_pass_id = sensing_pass_id or f"VIDPASS-{bus_id}-001"
        else:
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
            bus_id=bus_id, device_id=device_id, camera_id=camera_id, deterministic=deterministic
        )
        self.event_builder = event_builder or EventBuilder(
            bus_id=bus_id,
            device_id=device_id,
            camera_id=camera_id,
            model_name="urbansense-perception-ensemble",
            model_version="0.2.0-PROTOTYPE",
            deterministic=deterministic,
        )

        # Active opportunity window state
        self._active_opportunity: Optional[ObservationOpportunity] = None

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
        self._trace_seq += 1
        if trace_id:
            _trace_id = trace_id
        elif self.deterministic:
            _trace_id = f"TRACE-{self.bus_id}-{self._trace_seq:06d}"
        else:
            _trace_id = str(uuid.uuid4())

        # Resolve GNSS reading via HAL boundary — DO NOT silently fabricate in normal/real mode
        if gnss is not None:
            _gnss = gnss
        elif self.gnss_provider is not None:
            _gnss = self.gnss_provider.read()
        elif self.simulation_mode:
            # Explicit simulation mode GNSS stub
            _gnss = GNSSReading(
                latitude=17.4435,
                longitude=78.3772,
                altitude_m=542.0,
                accuracy_m=3.5,
                heading_deg=45.0,
                timestamp=frame.timestamp,
                fix_quality=1,
            )
        else:
            _gnss = None

        # Resolve IMU reading via HAL boundary — DO NOT silently fabricate in normal/real mode
        if imu is not None:
            _imu = imu
        elif self.imu_provider is not None:
            _imu = self.imu_provider.read()
        elif self.simulation_mode:
            # Explicit simulation mode IMU stub
            _imu = IMUReading(
                accel_x=0.02,
                accel_y=-0.01,
                accel_z=9.81,
                gyro_x=0.001,
                gyro_y=-0.002,
                gyro_z=0.000,
                timestamp=frame.timestamp,
            )
        else:
            _imu = None

        # 1. Optical Quality Evaluation (frame-level observability)
        t_q0 = time.perf_counter()
        quality_signals = self.quality_evaluator.evaluate_frame(frame)
        self.metrics.quality_eval_time_ms += (time.perf_counter() - t_q0) * 1000.0

        # 2. Opportunity Window Evaluation (reusing/grouping over a meaningful window)
        # SENSING PASS -> OPPORTUNITY WINDOW -> MULTIPLE FRAMES
        need_new_opportunity = (
            self._active_opportunity is None or
            frame.timestamp >= self._active_opportunity.window_end or
            frame.timestamp < self._active_opportunity.window_start
        )

        if need_new_opportunity:
            t_opp0 = time.perf_counter()
            self._opp_seq += 1
            window_start = frame.timestamp
            window_end = frame.timestamp + timedelta(seconds=self.opportunity_window_duration_s)
            opp_id = f"OPP-{self.bus_id}-{self._opp_seq:06d}" if self.deterministic else str(uuid.uuid4())
            self._active_opportunity = self.opportunity_evaluator.evaluate(
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
                opportunity_id=opp_id,
            )
            self.metrics.opportunity_eval_time_ms += (time.perf_counter() - t_opp0) * 1000.0

        opportunity = self._active_opportunity

        # 3. Model Inference (Pothole + Vehicle Detectors)
        # DETECTOR FAILURE != NO DETECTION (observable error handling)
        t_inf0 = time.perf_counter()
        raw_detections: List[RawDetection] = []
        detector_results: List[DetectorExecutionResult] = []
        detector_errors: List[dict] = []

        for detector in self.detectors:
            det_name = getattr(detector, "model_name", detector.__class__.__name__)
            try:
                dets = detector.detect(frame)
                raw_detections.extend(dets)
                detector_results.append(
                    DetectorExecutionResult(
                        detector_name=det_name,
                        success=True,
                        detections=dets,
                    )
                )
            except Exception as e:
                err_msg = str(e)
                err_code = e.__class__.__name__
                logger.error(f"Detector '{det_name}' failed on frame {frame.frame_id}: {err_msg}")
                self.metrics.detector_failures += 1
                detector_results.append(
                    DetectorExecutionResult(
                        detector_name=det_name,
                        success=False,
                        error_message=err_msg,
                        error_code=err_code,
                    )
                )
                detector_errors.append({
                    "frame_id": frame.frame_id,
                    "model_name": det_name,
                    "trace_id": _trace_id,
                    "error": err_msg,
                    "error_code": err_code,
                })

        self.metrics.inference_time_ms += (time.perf_counter() - t_inf0) * 1000.0
        self.metrics.detections_found += len(raw_detections)

        # 4. Temporal Tracking
        t_trk0 = time.perf_counter()
        active_tracks = self.tracker.update(raw_detections, frame.timestamp, frame.frame_id)
        self.metrics.tracking_time_ms += (time.perf_counter() - t_trk0) * 1000.0

        # 5. Form Observations and Canonical Events
        t_ev0 = time.perf_counter()
        observations: List[Observation] = []
        events: List[CanonicalEvent] = []

        for det in raw_detections:
            self._obs_seq += 1
            obs_id = f"OBS-{self._obs_seq:06d}" if self.deterministic else str(uuid.uuid4())

            # Evaluate localized crop quality (strictly distinct from frame quality)
            crop_quality = self.quality_evaluator.evaluate_detection_crop(frame, det.bbox)

            # Save evidence artifact (traceable local prototype)
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

            # Assemble Canonical Event ONLY if GNSS location is available.
            # Do NOT assemble georeferenced events with missing coordinates.
            if _gnss is not None:
                self._evt_seq += 1
                evt_id = f"EVT-{self._evt_seq:06d}" if self.deterministic else None
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
                    event_id=evt_id,
                )
                events.append(event)
                self.metrics.events_generated += 1
            else:
                logger.warning(
                    f"Frame {frame.frame_id}: GNSS unavailable. "
                    f"Observation {obs_id} recorded, but CanonicalEvent skipped due to missing location."
                )

        self.metrics.evidence_and_event_time_ms += (time.perf_counter() - t_ev0) * 1000.0
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
            detector_results=detector_results,
            detector_errors=detector_errors,
        )

    def process_video_file(
        self,
        video_path: str,
        max_frames: Optional[int] = None,
        frame_step: int = 1,
    ) -> List[ProcessedFrameResult]:
        """
        Process a recorded video file from end to end with rigorous performance accounting.
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
        if self.metrics.frames_processed > 0:
            avg_e2e_ms = (total_time * 1000.0) / self.metrics.frames_processed
            self.metrics.avg_end_to_end_ms_per_frame = round(avg_e2e_ms, 2)
            self.metrics.average_processed_fps = round(1000.0 / avg_e2e_ms, 2) if avg_e2e_ms > 0 else 0.0
            self.metrics.average_fps = self.metrics.average_processed_fps

            # Calculate residual overhead (video decode, loop overhead, etc.)
            sum_accounted_ms = (
                self.metrics.quality_eval_time_ms +
                self.metrics.opportunity_eval_time_ms +
                self.metrics.inference_time_ms +
                self.metrics.tracking_time_ms +
                self.metrics.evidence_and_event_time_ms
            )
            self.metrics.overhead_time_ms = max(0.0, (total_time * 1000.0) - sum_accounted_ms)

        return results

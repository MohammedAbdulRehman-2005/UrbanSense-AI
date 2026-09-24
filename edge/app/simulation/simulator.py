"""
UrbanSense AI — Sensing Pass Simulator
=========================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

Generates one complete deterministic sensing pass for BUS-001.

SIMULATED — This is NOT real fleet data.
All values are deterministic stubs. The simulator explicitly identifies
itself as simulated in every generated object.

BUS: BUS-001
DEVICE: DEVICE-001
CAMERA: CAMERA-FRONT-01
Route: SEG-001 (Hyderabad HITEC City road segment, simulated)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Tuple

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from contracts.observation import Observation, BoundingBox
from contracts.opportunity import ObservationOpportunity, TargetScope
from contracts.canonical_event import CanonicalEvent, EventPriority

from edge.app.hal.simulated import SimulatedGNSSProvider, SimulatedIMUProvider, SimulatedCameraProvider
from edge.app.opportunity.opportunity_evaluator import OpportunityEvaluator
from edge.app.simulation.event_builder import EventBuilder


# ─── Deterministic IDs ────────────────────────────────────────────────────────
BUS_ID = "BUS-001"
DEVICE_ID = "DEVICE-001"
CAMERA_ID = "CAMERA-FRONT-01"
MODEL_NAME = "urbansense-sim-detector"
MODEL_VERSION = "0.1.0-SIMULATED"

# ADVISORY ONLY — not authoritative map-match
EDGE_ROAD_SEGMENT_HINT = "SEG-001-HINT"

# Deterministic sensing pass ID (for reproducibility in tests)
SENSING_PASS_ID = "SIMPASS-M1-001"


class SensingPassSimulator:
    """
    Generates one complete deterministic sensing pass.

    Output:
        sensing_pass_id
        observation          (simulated AI detection output)
        opportunity          (simulated sensing quality)
        canonical_event      (assembled canonical event)

    All objects are explicitly marked as simulated.
    PROTOTYPE / SIMULATED.
    """

    def __init__(self) -> None:
        self.gnss = SimulatedGNSSProvider()
        self.imu = SimulatedIMUProvider()
        self.camera = SimulatedCameraProvider()
        self.evaluator = OpportunityEvaluator(BUS_ID, DEVICE_ID, CAMERA_ID)
        self.builder = EventBuilder(BUS_ID, DEVICE_ID, CAMERA_ID, MODEL_NAME, MODEL_VERSION)

    def run(self) -> Tuple[str, Observation, ObservationOpportunity, CanonicalEvent]:
        """
        Execute one simulated sensing pass.

        Returns:
            (sensing_pass_id, observation, opportunity, canonical_event)
        """
        trace_id = str(uuid.uuid4())

        # 1. Read sensors (all deterministic stubs)
        gnss = self.gnss.read()
        imu = self.imu.read()
        frame = self.camera.capture()

        # 2. Define sensing window (1-second window around current time)
        window_start = datetime.now(timezone.utc)
        window_end = window_start + timedelta(seconds=1)

        # 3. Generate Opportunity
        opportunity = self.evaluator.evaluate(
            sensing_pass_id=SENSING_PASS_ID,
            window_start=window_start,
            window_end=window_end,
            gnss=gnss,
            imu=imu,
            frame=frame,
            target_scope=TargetScope.SEGMENT,
            target_type="road_segment",
            target_id=None,  # Segment ID resolved by backend map-match
            edge_road_segment_hint=EDGE_ROAD_SEGMENT_HINT,
            trace_id=trace_id,
        )

        # 4. Generate Observation (simulated detection result)
        observation = Observation(
            frame_id=frame.frame_id,
            bus_id=BUS_ID,
            device_id=DEVICE_ID,
            camera_id=CAMERA_ID,
            timestamp=gnss.timestamp,
            object_type="pothole",
            # SIMULATED: deterministic stub confidence value.
            # In real deployment this comes from YOLO/detector softmax.
            # PROTOTYPE — not a real model output.
            detector_confidence=0.87,
            bbox=BoundingBox(
                x_min=640, y_min=500, x_max=800, y_max=600,
                frame_width=frame.width, frame_height=frame.height,
            ),
            mask_reference=None,
            track_id=None,
            trajectory_reference=None,
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            evidence_hint="simulated_high_confidence",
        )

        # 5. Build Canonical Event
        event = self.builder.build(
            observation=observation,
            opportunity=opportunity,
            event_timestamp=gnss.timestamp,
            latitude=gnss.latitude,
            longitude=gnss.longitude,
            altitude_m=gnss.altitude_m,
            accuracy_m=gnss.accuracy_m,
            heading_deg=gnss.heading_deg,
            event_type="pothole_observation",
            priority=EventPriority.P2,
            edge_road_segment_hint=EDGE_ROAD_SEGMENT_HINT,
            trace_id=trace_id,
            gps_quality=gnss.accuracy_m / 10.0 if gnss.accuracy_m else None,
        )

        return SENSING_PASS_ID, observation, opportunity, event

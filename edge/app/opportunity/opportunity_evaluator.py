"""
UrbanSense AI — Opportunity Evaluator (THE ONLY evaluator)
===========================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

IMPORTANT: This is the ONLY Opportunity evaluator implementation.
Location: edge/app/opportunity/opportunity_evaluator.py
Do NOT create a second evaluator elsewhere.

SCOPE IN MILESTONE 1:
- Uses deterministic stub values (PROTOTYPE / SIMULATED).
- All score values come from configuration, not real sensor analysis.
- Scores are labelled with DECISION_REQUIRED where production thresholds
  must be determined before real deployment.

The evaluator MUST NOT:
- calculate evidence_weight
- change RoadTwin state
- confirm defects
- perform backend fusion
- make authoritative map-match decisions

PROTOTYPE / SIMULATED — scores are stubs for integration testing.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

# Import from contracts (shared data shapes)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from contracts.opportunity import ObservationOpportunity, TargetScope, ValidityStatus
from edge.app.hal.interfaces import GNSSReading, IMUReading, CameraFrame


# ─── PROTOTYPE Configuration ──────────────────────────────────────────────────
# All values below are PROTOTYPE / SIMULATED.
# DECISION_REQUIRED: production thresholds must be determined via real-world
# calibration before any non-local deployment.

PROTOTYPE_SCORES = {
    "visibility_score": 0.90,        # PROTOTYPE — assume good daylight visibility
    "illumination_score": 0.88,      # PROTOTYPE — assume adequate illumination
    "blur_score": 0.85,              # PROTOTYPE — assume acceptable motion blur
    "occlusion_score": 0.92,         # PROTOTYPE — assume minimal occlusion
    "viewing_angle_score": 0.80,     # PROTOTYPE — assume near-optimal angle
    "distance_score": 0.87,          # PROTOTYPE — assume appropriate distance
    "sensor_health_score": 1.00,     # PROTOTYPE — sensor healthy in simulation
    "gps_quality_score": 0.90,       # PROTOTYPE — good GPS in simulation
    "coverage_fraction": 0.95,       # PROTOTYPE — good target coverage
    # DECISION_REQUIRED: weighting scheme for opportunity_score composite
    # Using simple mean for prototype. Real weighting needs domain expert input.
    "opportunity_score_method": "mean",
}

# DECISION_REQUIRED: What minimum opportunity_score is required for VALID status?
# Using 0.70 as placeholder. Must be calibrated.
PROTOTYPE_VALIDITY_THRESHOLD = 0.70


class OpportunityEvaluator:
    """
    Evaluates a sensing context and produces an ObservationOpportunity.

    Milestone 1 implementation: deterministic stub values from PROTOTYPE_SCORES.
    Future milestones: replace score calculations with real sensor analysis.

    This is the ONLY place Opportunity evaluation logic lives.
    """

    def __init__(
        self,
        bus_id: str,
        device_id: str,
        camera_id: str,
        scores: Optional[dict] = None,
    ) -> None:
        self.bus_id = bus_id
        self.device_id = device_id
        self.camera_id = camera_id
        self._scores = scores or PROTOTYPE_SCORES

    def evaluate(
        self,
        sensing_pass_id: str,
        window_start: datetime,
        window_end: datetime,
        gnss: GNSSReading,
        imu: IMUReading,
        frame: CameraFrame,
        target_scope: TargetScope = TargetScope.SEGMENT,
        target_type: str = "road_segment",
        target_id: Optional[str] = None,
        edge_road_segment_hint: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> ObservationOpportunity:
        """
        Evaluate a sensing context and return an ObservationOpportunity.

        In Milestone 1, all scores are deterministic stubs.
        PROTOTYPE / SIMULATED.
        """
        scores = self._scores

        # PROTOTYPE: simple mean for composite score
        # DECISION_REQUIRED: production scoring should use domain-validated weighting
        score_values = [
            scores["visibility_score"],
            scores["illumination_score"],
            scores["blur_score"],
            scores["occlusion_score"],
            scores["viewing_angle_score"],
            scores["distance_score"],
            scores["sensor_health_score"],
            scores["gps_quality_score"],
        ]
        opportunity_score = round(sum(score_values) / len(score_values), 4)

        # Determine validity
        invalid_reasons = []
        fov_valid = True

        if not gnss.fix_quality > 0:
            invalid_reasons.append("No valid GPS fix")
            fov_valid = False
        if opportunity_score < PROTOTYPE_VALIDITY_THRESHOLD:
            invalid_reasons.append(
                f"Opportunity score {opportunity_score} below threshold {PROTOTYPE_VALIDITY_THRESHOLD}"
            )

        validity_status = ValidityStatus.VALID if not invalid_reasons else ValidityStatus.INVALID

        return ObservationOpportunity(
            opportunity_id=str(uuid.uuid4()),
            sensing_pass_id=sensing_pass_id,
            bus_id=self.bus_id,
            device_id=self.device_id,
            camera_id=self.camera_id,
            window_start=window_start,
            window_end=window_end,
            target_scope=target_scope,
            target_type=target_type,
            target_id=target_id,
            edge_road_segment_hint=edge_road_segment_hint,
            fov_valid=fov_valid,
            visibility_score=scores["visibility_score"],
            illumination_score=scores["illumination_score"],
            blur_score=scores["blur_score"],
            occlusion_score=scores["occlusion_score"],
            viewing_angle_score=scores["viewing_angle_score"],
            distance_score=scores["distance_score"],
            sensor_health_score=scores["sensor_health_score"],
            gps_quality_score=scores["gps_quality_score"],
            opportunity_score=opportunity_score,
            validity_status=validity_status,
            invalid_reasons=invalid_reasons,
            coverage_fraction=scores["coverage_fraction"],
            trace_id=trace_id or str(uuid.uuid4()),
        )

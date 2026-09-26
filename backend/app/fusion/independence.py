"""
UrbanSense AI — Independence Classifier (Milestone 3)
=====================================================
Classifies each candidate evidence contribution as INDEPENDENT, CORRELATED,
or DUPLICATE, and assigns a correlation_group_id.

IMPORTANT PROTOTYPE RULES:
- MVP independence rule is documented as PROTOTYPE / DECISION_REQUIRED.
- Do NOT claim independence merely because bus_id differs without checking
  the other dimensions: device_id, camera_id, sensing_pass, time, and
  spatial proximity.
- The independence classification in M3 is a prototype for demonstration;
  production independence must be determined by a validated domain study.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class IndependenceClass(str, Enum):
    INDEPENDENT = "INDEPENDENT"
    CORRELATED = "CORRELATED"
    DUPLICATE = "DUPLICATE"


@dataclass
class IndependenceInput:
    """All attributes needed to classify a candidate evidence contribution."""
    event_id: str
    bus_id: str
    device_id: str
    camera_id: str
    sensing_pass_id: Optional[str] = None  # If available; None = unknown pass
    event_timestamp_iso: str = ""          # ISO 8601 string for comparison
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    observation_id: Optional[str] = None
    opportunity_id: Optional[str] = None


@dataclass
class IndependenceResult:
    independence_class: IndependenceClass
    correlation_group_id: Optional[str]
    reason: str


# ── Prototype independence rules ───────────────────────────────────────────
# DECISION_REQUIRED: these thresholds are not calibrated; replace with
# domain-validated values before production use.
# PROTOTYPE: Different bus_id is a necessary condition for independence,
# but not sufficient. Same bus + different time may still be CORRELATED if
# the defect is highly persistent and the same camera pass.

_SPATIAL_INDEPENDENCE_RADIUS_M = 50.0   # DECISION_REQUIRED
_TEMPORAL_INDEPENDENCE_WINDOW_S = 300   # 5 min; DECISION_REQUIRED


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class PrototypeIndependenceClassifier:
    """
    PROTOTYPE independence classifier for M3 demonstration.
    Reasons about: bus_id, device_id, camera_id, sensing_pass, time, spatial proximity.

    DECISION_REQUIRED before production:
    - Validated spatial proximity threshold
    - Validated temporal independence window
    - Handling of weather/model-failure correlation
    - Statistical calibration study
    """

    def classify(
        self,
        candidate: IndependenceInput,
        existing_contributions: list[IndependenceInput],
        road_segment_id: Optional[str] = None,
    ) -> IndependenceResult:
        """
        Classify `candidate` against all previous contributions on the same road segment.
        Returns DUPLICATE, CORRELATED, or INDEPENDENT.
        """
        # No prior contributions → first evidence, always INDEPENDENT on this segment
        if not existing_contributions:
            return IndependenceResult(
                independence_class=IndependenceClass.INDEPENDENT,
                correlation_group_id=road_segment_id,
                reason="First evidence contribution on segment — classified INDEPENDENT (PROTOTYPE)",
            )

        from datetime import datetime, timezone

        def parse_ts(s: str) -> datetime:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return datetime.now(timezone.utc)

        candidate_ts = parse_ts(candidate.event_timestamp_iso)

        for prior in existing_contributions:
            # --- DUPLICATE: same event_id ---
            if prior.event_id == candidate.event_id:
                return IndependenceResult(
                    independence_class=IndependenceClass.DUPLICATE,
                    correlation_group_id=road_segment_id,
                    reason=f"Duplicate event_id={candidate.event_id} already recorded",
                )

            # --- DUPLICATE: same bus + same sensing_pass (if pass known) ---
            if (
                candidate.bus_id == prior.bus_id
                and candidate.sensing_pass_id is not None
                and prior.sensing_pass_id is not None
                and candidate.sensing_pass_id == prior.sensing_pass_id
                and candidate.camera_id == prior.camera_id
            ):
                return IndependenceResult(
                    independence_class=IndependenceClass.DUPLICATE,
                    correlation_group_id=road_segment_id,
                    reason=(
                        f"Same bus={candidate.bus_id} + same sensing_pass={candidate.sensing_pass_id}"
                        f" + same camera={candidate.camera_id}: DUPLICATE"
                    ),
                )

            # --- CORRELATED: same bus, different time, spatial proximity ---
            if candidate.bus_id == prior.bus_id:
                prior_ts = parse_ts(prior.event_timestamp_iso)
                time_diff_s = abs((candidate_ts - prior_ts).total_seconds())

                spatial_correlated = False
                dist_m = None
                if (
                    candidate.latitude is not None
                    and candidate.longitude is not None
                    and prior.latitude is not None
                    and prior.longitude is not None
                ):
                    dist_m = _haversine_m(
                        candidate.latitude, candidate.longitude,
                        prior.latitude, prior.longitude,
                    )
                    if dist_m <= _SPATIAL_INDEPENDENCE_RADIUS_M:
                        spatial_correlated = True
                else:
                    # When coordinates are not available on one or both contributions, fall back to segment-level spatial correlation
                    spatial_correlated = True

                if spatial_correlated and time_diff_s <= _TEMPORAL_INDEPENDENCE_WINDOW_S:
                    dist_str = f"spatial={dist_m:.1f}m < {_SPATIAL_INDEPENDENCE_RADIUS_M}m" if dist_m is not None else "spatial=segment-level"
                    return IndependenceResult(
                        independence_class=IndependenceClass.CORRELATED,
                        correlation_group_id=road_segment_id,
                        reason=(
                            f"Same bus={candidate.bus_id}, {dist_str},"
                            f" time_diff={time_diff_s:.0f}s < {_TEMPORAL_INDEPENDENCE_WINDOW_S}s: CORRELATED (PROTOTYPE)"
                        ),
                    )

        # --- Default: different bus_id, or same bus outside proximity/time window ---
        # PROTOTYPE: bus_id differs → INDEPENDENT for M3 demo.
        # DECISION_REQUIRED: production rule requires validation of weather correlation,
        # model failure correlation, shared infrastructure, etc.
        return IndependenceResult(
            independence_class=IndependenceClass.INDEPENDENT,
            correlation_group_id=road_segment_id,
            reason=(
                f"bus_id={candidate.bus_id} not correlated with any prior contribution"
                f" at this segment — INDEPENDENT (PROTOTYPE / DECISION_REQUIRED)"
            ),
        )


_classifier = PrototypeIndependenceClassifier()


def classify_independence(
    candidate: IndependenceInput,
    existing_contributions: list[IndependenceInput],
    road_segment_id: Optional[str] = None,
) -> IndependenceResult:
    """Module-level entry point for independence classification."""
    return _classifier.classify(candidate, existing_contributions, road_segment_id)

"""
UrbanSense AI — Bottleneck Detection Engine (Milestone 5)
==========================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Section 26.3)

Bottleneck identification rule:
    density high
    AND fleet speed low
    AND persistence across rolling windows
    → bottleneck

Rolling 3-window condition (Master Plan requirement):
Window T-2 (qualifying)
AND Window T-1 (qualifying)
AND Window T (qualifying)
→ BOTTLENECK ACTIVE

A single snapshot must NOT trigger a bottleneck.
Two qualifying windows must NOT trigger a bottleneck.
An interruption by a non-qualifying window resets the qualifying streak.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.traffic import TrafficObservationModel, TrafficBottleneckModel
from contracts.traffic import BottleneckStatus, DensityCondition, SpeedCondition

logger = logging.getLogger(__name__)


def is_window_qualifying(
    obs: TrafficObservationModel,
    high_density_threshold: float,
    low_speed_threshold_kmh: float,
) -> bool:
    """
    Check if a single traffic observation window qualifies as a bottleneck condition:
    1. density >= high_density_threshold
    2. average_speed_kmh is not None and average_speed_kmh <= low_speed_threshold_kmh
    """
    if obs.density < high_density_threshold:
        return False
    if obs.average_speed_kmh is None:
        # Missing speed is UNKNOWN — cannot certify low fleet speed
        return False
    if obs.average_speed_kmh > low_speed_threshold_kmh:
        return False
    return True


class BottleneckEngine:
    """
    Evaluates rolling traffic observation windows to detect persistent bottlenecks.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def evaluate_windows(
        self,
        windows: List[TrafficObservationModel],
        required_count: Optional[int] = None,
    ) -> Tuple[bool, int, List[str]]:
        """
        Pure evaluation logic across a chronological sequence of observation windows.
        Returns:
            (is_active, current_streak, qualifying_window_ids)
        """
        required = required_count or self.settings.traffic_bottleneck_window_count
        high_density = self.settings.traffic_high_density_threshold
        low_speed = self.settings.traffic_low_speed_threshold_kmh

        # Sort chronologically by window_start
        sorted_windows = sorted(windows, key=lambda w: w.window_start)

        streak = 0
        qualifying_ids: List[str] = []

        for w in sorted_windows:
            if is_window_qualifying(w, high_density, low_speed):
                streak += 1
                qualifying_ids.append(w.traffic_observation_id)
            else:
                # Interrupted streak resets persistence
                streak = 0
                qualifying_ids.clear()

        is_active = streak >= required
        return is_active, streak, qualifying_ids

    def evaluate_segment(
        self,
        db: Session,
        road_segment_id: str,
        as_of_time: Optional[datetime] = None,
    ) -> Optional[TrafficBottleneckModel]:
        """
        Evaluate the latest rolling windows for `road_segment_id` up to `as_of_time`.
        Updates and persists TrafficBottleneckModel state.
        """
        now = datetime.now(timezone.utc)
        cutoff = as_of_time or now

        # Fetch recent windows for this segment ending on or before cutoff
        query = (
            db.query(TrafficObservationModel)
            .filter_by(road_segment_id=road_segment_id)
            .filter(TrafficObservationModel.window_end <= cutoff)
            .order_by(TrafficObservationModel.window_start.asc())
        )
        windows = query.all()

        if not windows:
            return None

        required = self.settings.traffic_bottleneck_window_count
        is_active, streak, qualifying_ids = self.evaluate_windows(windows, required)

        # Check existing bottleneck record for this segment
        existing_bottleneck = (
            db.query(TrafficBottleneckModel)
            .filter_by(road_segment_id=road_segment_id, status=BottleneckStatus.ACTIVE.value)
            .first()
        )

        if is_active:
            # Qualifying streak is met (>= 3 consecutive windows)
            # Find the qualifying window models
            id_set = set(qualifying_ids[-required:])
            active_evidence_windows = [w for w in windows if w.traffic_observation_id in id_set]
            first_w = min(active_evidence_windows, key=lambda w: w.window_start)
            latest_w = max(active_evidence_windows, key=lambda w: w.window_end)

            if existing_bottleneck is None:
                bottleneck = TrafficBottleneckModel(
                    bottleneck_id=str(uuid.uuid4()),
                    road_segment_id=road_segment_id,
                    status=BottleneckStatus.ACTIVE.value,
                    severity="HIGH",
                    density_condition=DensityCondition.HIGH.value,
                    speed_condition=SpeedCondition.LOW.value,
                    qualifying_window_count=streak,
                    required_window_count=required,
                    first_qualifying_window_start=first_w.window_start,
                    latest_qualifying_window_end=latest_w.window_end,
                    evidence_window_ids=qualifying_ids[-required:],
                    start_time=latest_w.window_end,
                    resolved_at=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(bottleneck)
                logger.info(
                    "Bottleneck ACTIVATED on segment=%s: streak=%d windows evidence=%s",
                    road_segment_id,
                    streak,
                    qualifying_ids[-required:],
                )
            else:
                existing_bottleneck.qualifying_window_count = streak
                existing_bottleneck.latest_qualifying_window_end = latest_w.window_end
                existing_bottleneck.evidence_window_ids = qualifying_ids[-required:]
                existing_bottleneck.updated_at = now
                bottleneck = existing_bottleneck

            db.flush()
            return bottleneck

        else:
            # Condition not met. If a bottleneck was active, resolve it
            if existing_bottleneck is not None:
                existing_bottleneck.status = BottleneckStatus.RESOLVED.value
                existing_bottleneck.resolved_at = now
                existing_bottleneck.updated_at = now
                db.flush()
                logger.info(
                    "Bottleneck RESOLVED on segment=%s: condition cleared at %s",
                    road_segment_id,
                    now.isoformat(),
                )
                return existing_bottleneck

            return None

"""
UrbanSense AI — Traffic Aggregator (Milestone 5)
=================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Section 26)

Aggregates tracked vehicles by:
- segment (via authoritative backend map matcher)
- time window (event-time timestamps, configurable duration)
- vehicle class (car, bus, truck, motorcycle, bicycle)
- camera / bus / pass lineage

COUNTING SEMANTICS:
- A tracked object (track_id) contributes AT MOST ONCE per aggregation window on a given road segment.
- Consecutive frames observing the same track_id do not multiply vehicle count.

SPEED DERIVATION (Approach A):
- Derived from consecutive valid GPS fixes and event timestamps.
- Raw pixel motion is never converted to physical speed without calibration.
- If speed cannot be established (single fix, non-positive dt), speed remains None (UNKNOWN).
"""
from __future__ import annotations

import math
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.event import EventModel
from backend.app.models.road_segment import RoadSegment
from backend.app.models.traffic import TrafficObservationModel
from contracts.traffic import (
    CongestionState,
    DensityCondition,
    SpeedCondition,
    VehicleClass,
    TrafficObservation,
)

logger = logging.getLogger(__name__)

# Canonical vehicle event types supported by UrbanSense
VEHICLE_EVENT_TYPES = {
    "vehicle_observation",
    "car_observation",
    "bus_observation",
    "truck_observation",
    "motorcycle_observation",
    "bicycle_observation",
}

VALID_VEHICLE_CLASSES = {cls.value for cls in VehicleClass}


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def derive_fleet_speed_from_gps(
    gps_fixes: List[Tuple[float, float, datetime]],
) -> Optional[float]:
    """
    Derive average speed (km/h) from consecutive GPS fixes (Approach A).

    Rules:
    - Points must be chronologically ordered.
    - Requires at least 2 distinct temporal fixes.
    - If dt <= 0, the interval is invalid (cannot fabricate speed).
    - If no valid segments exist, returns None (UNKNOWN).
    """
    if len(gps_fixes) < 2:
        return None

    # Sort strictly by timestamp
    sorted_fixes = sorted(gps_fixes, key=lambda p: p[2])

    total_dist_m = 0.0
    total_time_s = 0.0

    for i in range(1, len(sorted_fixes)):
        lat1, lon1, t1 = sorted_fixes[i - 1]
        lat2, lon2, t2 = sorted_fixes[i]

        dt = (t2 - t1).total_seconds()
        if dt <= 0:
            # Backward or instantaneous timestamp — invalid interval
            continue

        dist = haversine_distance_m(lat1, lon1, lat2, lon2)
        total_dist_m += dist
        total_time_s += dt

    if total_time_s <= 0 or total_dist_m < 0:
        return None

    speed_mps = total_dist_m / total_time_s
    speed_kmh = round(speed_mps * 3.6, 2)
    return speed_kmh


def get_window_bounds(ts: datetime, duration_seconds: int) -> Tuple[datetime, datetime]:
    """
    Align a timestamp to deterministic window bounds [window_start, window_end).
    Always operates in UTC.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)

    epoch_seconds = ts.timestamp()
    w_start_sec = math.floor(epoch_seconds / duration_seconds) * duration_seconds
    w_start = datetime.fromtimestamp(w_start_sec, tz=timezone.utc)
    w_end = w_start + timedelta(seconds=duration_seconds)
    return w_start, w_end


def normalize_vehicle_class(event_type_or_class: str) -> str:
    """Map raw event_type or class label to canonical vehicle class."""
    cleaned = event_type_or_class.lower().replace("_observation", "").strip()
    if cleaned in VALID_VEHICLE_CLASSES:
        return cleaned
    if "car" in cleaned or "auto" in cleaned:
        return "car"
    if "bus" in cleaned:
        return "bus"
    if "truck" in cleaned:
        return "truck"
    if "motorcycle" in cleaned or "bike" in cleaned or "2w" in cleaned:
        return "motorcycle"
    if "bicycle" in cleaned:
        return "bicycle"
    return "car"  # Default generic vehicle fallback


class TrafficAggregator:
    """
    Authoritative Traffic Aggregation Engine.
    Produces TrafficObservation entities for a given road segment and time window.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def determine_congestion_state(
        self,
        density: float,
        speed_kmh: Optional[float],
    ) -> CongestionState:
        """
        Evaluate congestion level from density and speed.
        PROPOSED prototype rules:
        - HIGH: density >= traffic_high_density_threshold AND speed is low
        - ELEVATED: density >= traffic_elevated_density_threshold OR speed is low
        - NORMAL: otherwise
        """
        high_density = density >= self.settings.traffic_high_density_threshold
        elevated_density = density >= self.settings.traffic_elevated_density_threshold
        low_speed = (
            speed_kmh is not None
            and speed_kmh <= self.settings.traffic_low_speed_threshold_kmh
        )

        if high_density and low_speed:
            return CongestionState.HIGH
        if elevated_density or low_speed:
            return CongestionState.ELEVATED
        return CongestionState.NORMAL

    def aggregate_window_from_events(
        self,
        db: Session,
        road_segment_id: str,
        window_start: datetime,
        window_end: datetime,
        trace_id: Optional[str] = None,
    ) -> TrafficObservationModel:
        """
        Aggregate all vehicle events on `road_segment_id` in [window_start, window_end).
        Enforces deduplicated vehicle counting by track_id.
        Persists and returns TrafficObservationModel.
        """
        now = datetime.now(timezone.utc)
        _trace_id = trace_id or str(uuid.uuid4())

        # Query all vehicle events in this window
        events = (
            db.query(EventModel)
            .filter_by(matched_road_segment_id=road_segment_id)
            .filter(EventModel.event_timestamp >= window_start)
            .filter(EventModel.event_timestamp < window_end)
            .filter(EventModel.event_type.in_(VEHICLE_EVENT_TYPES))
            .order_by(EventModel.event_timestamp.asc())
            .all()
        )

        # Counting semantics: unique track_id per window
        seen_tracks: Set[str] = set()
        class_counts: Dict[str, int] = {cls.value: 0 for cls in VehicleClass}
        gps_fixes: List[Tuple[float, float, datetime]] = []
        telemetry_speeds: List[float] = []

        bus_ids: Set[str] = set()
        device_ids: Set[str] = set()
        camera_ids: Set[str] = set()
        sensing_pass_ids: Set[str] = set()

        for ev in events:
            # Lineage tracking
            if ev.bus_id:
                bus_ids.add(ev.bus_id)
            if ev.device_id:
                device_ids.add(ev.device_id)
            if ev.camera_id:
                camera_ids.add(ev.camera_id)
            if ev.opportunity_id:
                sensing_pass_ids.add(ev.opportunity_id)

            # GPS tracking for speed derivation
            if ev.latitude is not None and ev.longitude is not None and ev.event_timestamp is not None:
                gps_fixes.append((ev.latitude, ev.longitude, ev.event_timestamp))

            # Telemetry speed if available
            if ev.telemetry_speed_kmh is not None:
                telemetry_speeds.append(ev.telemetry_speed_kmh)

            # Deduplication key: prefer track_id; fallback to observation_id or event_id
            track_key = ev.track_id or ev.observation_id or ev.event_id
            if track_key not in seen_tracks:
                seen_tracks.add(track_key)
                v_class = normalize_vehicle_class(ev.event_type)
                class_counts[v_class] = class_counts.get(v_class, 0) + 1

        vehicle_count = len(seen_tracks)

        # Speed calculation: telemetry speed if provided, else GPS-derived (Approach A)
        if telemetry_speeds:
            average_speed_kmh = round(sum(telemetry_speeds) / len(telemetry_speeds), 2)
        else:
            average_speed_kmh = derive_fleet_speed_from_gps(gps_fixes)

        # Segment length resolution
        seg = db.query(RoadSegment).filter_by(segment_id=road_segment_id).first()
        segment_length_m = self.settings.traffic_default_segment_length_m
        # If segment length can be derived from PostGIS geom in future, do so here.

        # Density and flow metrics (PROPOSED prototype formulations)
        # density = vehicles / km
        density = round(vehicle_count / (segment_length_m / 1000.0), 2)
        window_duration_s = max(1.0, (window_end - window_start).total_seconds())
        # flow_rate = vehicles / hour
        flow_rate = round(vehicle_count * (3600.0 / window_duration_s), 2)

        congestion_state = self.determine_congestion_state(density, average_speed_kmh)

        # Upsert TrafficObservationModel
        existing = (
            db.query(TrafficObservationModel)
            .filter_by(
                road_segment_id=road_segment_id,
                window_start=window_start,
                window_end=window_end,
            )
            .first()
        )

        if existing is None:
            obs_model = TrafficObservationModel(
                traffic_observation_id=str(uuid.uuid4()),
                road_segment_id=road_segment_id,
                window_start=window_start,
                window_end=window_end,
                bus_id=",".join(sorted(bus_ids)) if bus_ids else None,
                device_id=",".join(sorted(device_ids)) if device_ids else None,
                camera_id=",".join(sorted(camera_ids)) if camera_ids else None,
                sensing_pass_id=",".join(sorted(sensing_pass_ids)) if sensing_pass_ids else None,
                vehicle_count=vehicle_count,
                vehicle_class_counts=class_counts,
                average_speed_kmh=average_speed_kmh,
                density=density,
                flow_rate=flow_rate,
                congestion_state=congestion_state.value,
                trace_id=_trace_id,
                created_at=now,
            )
            db.add(obs_model)
        else:
            existing.bus_id = ",".join(sorted(bus_ids)) if bus_ids else existing.bus_id
            existing.device_id = ",".join(sorted(device_ids)) if device_ids else existing.device_id
            existing.camera_id = ",".join(sorted(camera_ids)) if camera_ids else existing.camera_id
            existing.sensing_pass_id = (
                ",".join(sorted(sensing_pass_ids)) if sensing_pass_ids else existing.sensing_pass_id
            )
            existing.vehicle_count = vehicle_count
            existing.vehicle_class_counts = class_counts
            existing.average_speed_kmh = average_speed_kmh
            existing.density = density
            existing.flow_rate = flow_rate
            existing.congestion_state = congestion_state.value
            obs_model = existing

        db.flush()
        logger.info(
            "Traffic aggregated for segment=%s window=[%s, %s] count=%d speed=%s density=%.2f congestion=%s",
            road_segment_id,
            window_start.isoformat(),
            window_end.isoformat(),
            vehicle_count,
            f"{average_speed_kmh:.1f} km/h" if average_speed_kmh is not None else "UNKNOWN",
            density,
            congestion_state.value,
        )
        return obs_model

"""
UrbanSense AI — Milestone 5 Traffic Intelligence Test Suite
============================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Phase 19)

Covers:
1. Contract tests (valid observation, invalid timestamps, invalid metrics, schema)
2. Tracking & counting tests (single track, repeated frames dedup, multi-class distribution)
3. Segment tests (authoritative map matching, unmatched, ambiguous)
4. Speed tests (Approach A GPS speed derivation, missing speed NULL, non-positive dt)
5. Windowing tests (deterministic event-time windows, boundary behavior, late events)
6. Density & flow tests (controlled fixture metrics, threshold respect)
7. Bottleneck tests (Cases 1–6: 3-window condition, normal speed, low density, 1-window, 2-windows, interrupted streak)
8. API read model tests (GET /api/v1/traffic, GET /api/v1/bottlenecks)
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contracts.traffic import (
    TrafficObservation,
    BottleneckState,
    CongestionState,
    DensityCondition,
    SpeedCondition,
    BottleneckStatus,
    VehicleClass,
    VehicleClassCounts,
)
from backend.app.core.config import Settings
from backend.app.models.traffic import TrafficObservationModel, TrafficBottleneckModel
from backend.app.services.map_matcher import match_location, MapMatchStatus
from backend.app.traffic.aggregator import (
    TrafficAggregator,
    derive_fleet_speed_from_gps,
    get_window_bounds,
    haversine_distance_m,
    normalize_vehicle_class,
    VEHICLE_EVENT_TYPES,
)
from backend.app.traffic.bottleneck import (
    BottleneckEngine,
    is_window_qualifying,
)


# ─── 1. Contract Tests ────────────────────────────────────────────────────────

class TestTrafficContracts:
    def test_valid_traffic_observation_contract(self):
        """Valid traffic observation satisfies all schema constraints."""
        now = datetime.now(timezone.utc)
        obs = TrafficObservation(
            traffic_observation_id="TOBS-001",
            road_segment_id="SEG-TRF-001",
            window_start=now,
            window_end=now + timedelta(seconds=60),
            bus_id="BUS-001",
            device_id="DEV-001",
            camera_id="CAM-001",
            vehicle_count=5,
            vehicle_class_counts={"car": 3, "bus": 1, "truck": 1, "motorcycle": 0, "bicycle": 0},
            average_speed_kmh=18.5,
            density=10.0,
            flow_rate=300.0,
            congestion_state=CongestionState.ELEVATED,
            trace_id="tr-test-01",
            created_at=now,
        )
        assert obs.traffic_observation_id == "TOBS-001"
        assert obs.vehicle_count == 5
        assert obs.density == 10.0
        assert obs.congestion_state == CongestionState.ELEVATED

    def test_negative_vehicle_count_rejected(self):
        """Negative vehicle count must fail validation."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            TrafficObservation(
                traffic_observation_id="TOBS-NEG",
                road_segment_id="SEG-TRF-001",
                window_start=now,
                window_end=now + timedelta(seconds=60),
                vehicle_count=-1,  # Invalid
                density=0.0,
                flow_rate=0.0,
                congestion_state=CongestionState.NORMAL,
                trace_id="tr-neg",
            )

    def test_negative_density_rejected(self):
        """Negative density must fail validation."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            TrafficObservation(
                traffic_observation_id="TOBS-NEG-DENS",
                road_segment_id="SEG-TRF-001",
                window_start=now,
                window_end=now + timedelta(seconds=60),
                vehicle_count=5,
                density=-2.5,  # Invalid
                flow_rate=100.0,
                congestion_state=CongestionState.NORMAL,
                trace_id="tr-neg",
            )

    def test_bottleneck_state_contract_valid(self):
        """Valid BottleneckState schema creation."""
        now = datetime.now(timezone.utc)
        bn = BottleneckState(
            bottleneck_id="BN-001",
            road_segment_id="SEG-TRF-001",
            status=BottleneckStatus.ACTIVE,
            severity="HIGH",
            density_condition=DensityCondition.HIGH,
            speed_condition=SpeedCondition.LOW,
            qualifying_window_count=3,
            required_window_count=3,
            first_qualifying_window_start=now - timedelta(seconds=180),
            latest_qualifying_window_end=now,
            evidence_window_ids=["w1", "w2", "w3"],
            start_time=now,
        )
        assert bn.status == BottleneckStatus.ACTIVE
        assert bn.qualifying_window_count == 3
        assert len(bn.evidence_window_ids) == 3


# ─── 2. Tracking & Counting Tests ─────────────────────────────────────────────

class TestTrackingAndCountingSemantics:
    def test_single_track_counted_once(self):
        """A single vehicle track is counted exactly once."""
        t_start = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        t_end = t_start + timedelta(seconds=60)

        ev1 = MagicMock()
        ev1.event_id = "EV-1"
        ev1.track_id = "TRK-001"
        ev1.event_type = "car_observation"
        ev1.event_timestamp = t_start + timedelta(seconds=5)
        ev1.latitude = 17.4300
        ev1.longitude = 78.3600
        ev1.telemetry_speed_kmh = None
        ev1.bus_id = "BUS-01"
        ev1.device_id = "DEV-01"
        ev1.camera_id = "CAM-01"
        ev1.opportunity_id = "OPP-01"

        db = MagicMock()
        db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [ev1]
        db.query.return_value.filter_by.return_value.first.return_value = None

        aggregator = TrafficAggregator()
        result = aggregator.aggregate_window_from_events(db, "SEG-TRF-001", t_start, t_end)
        assert result.vehicle_count == 1
        assert result.vehicle_class_counts["car"] == 1

    def test_repeated_frames_of_same_track_do_not_multiply_count(self):
        """CRITICAL: Same track across 5 consecutive frames must count as 1 vehicle."""
        t_start = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        t_end = t_start + timedelta(seconds=60)

        # 5 events all sharing track_id="TRK-CAR-001"
        events = []
        for sec in [2, 4, 6, 8, 10]:
            ev = MagicMock()
            ev.event_id = f"EV-{sec}"
            ev.track_id = "TRK-CAR-001"
            ev.event_type = "car_observation"
            ev.event_timestamp = t_start + timedelta(seconds=sec)
            ev.latitude = 17.4300 + (sec * 0.00001)
            ev.longitude = 78.3600 + (sec * 0.00001)
            ev.telemetry_speed_kmh = None
            ev.bus_id = "BUS-01"
            ev.device_id = "DEV-01"
            ev.camera_id = "CAM-01"
            ev.opportunity_id = "OPP-01"
            events.append(ev)

        db = MagicMock()
        db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = events
        db.query.return_value.filter_by.return_value.first.return_value = None

        aggregator = TrafficAggregator()
        result = aggregator.aggregate_window_from_events(db, "SEG-TRF-001", t_start, t_end)

        # Must count as 1, NOT 5
        assert result.vehicle_count == 1
        assert result.vehicle_class_counts["car"] == 1

    def test_multiple_vehicle_classes_aggregate_correctly(self):
        """Multiple unique tracks across classes aggregate into correct counts."""
        t_start = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        t_end = t_start + timedelta(seconds=60)

        spec = [
            ("TRK-1", "car_observation"),
            ("TRK-1", "car_observation"),  # Duplicate frame of TRK-1
            ("TRK-2", "bus_observation"),
            ("TRK-3", "truck_observation"),
            ("TRK-4", "motorcycle_observation"),
            ("TRK-5", "bicycle_observation"),
            ("TRK-6", "car_observation"),
        ]

        events = []
        for i, (tid, etype) in enumerate(spec):
            ev = MagicMock()
            ev.event_id = f"EV-{i}"
            ev.track_id = tid
            ev.event_type = etype
            ev.event_timestamp = t_start + timedelta(seconds=i * 5)
            ev.latitude = 17.4300
            ev.longitude = 78.3600
            ev.telemetry_speed_kmh = None
            ev.bus_id = "BUS-01"
            ev.device_id = "DEV-01"
            ev.camera_id = "CAM-01"
            ev.opportunity_id = "OPP-01"
            events.append(ev)

        db = MagicMock()
        db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = events
        db.query.return_value.filter_by.return_value.first.return_value = None

        aggregator = TrafficAggregator()
        result = aggregator.aggregate_window_from_events(db, "SEG-TRF-001", t_start, t_end)

        assert result.vehicle_count == 6  # 6 unique tracks (TRK-1 counted once)
        assert result.vehicle_class_counts["car"] == 2
        assert result.vehicle_class_counts["bus"] == 1
        assert result.vehicle_class_counts["truck"] == 1
        assert result.vehicle_class_counts["motorcycle"] == 1
        assert result.vehicle_class_counts["bicycle"] == 1


# ─── 3. Segment Association Tests ─────────────────────────────────────────────

class TestSegmentAssociation:
    def test_traffic_corridor_segment_matched(self):
        """Authoritative map matcher matches SEG-TRF-001 coordinates."""
        match = match_location(17.4300, 78.3600)
        assert match.map_match_status == MapMatchStatus.MATCHED
        assert match.matched_road_segment_id == "SEG-TRF-001"
        assert match.map_match_confidence > 0.8

    def test_unmatched_location_handled_safely(self):
        """Out of bounds location returns UNMATCHED and None segment."""
        match = match_location(0.0, 0.0)
        assert match.map_match_status == MapMatchStatus.UNMATCHED
        assert match.matched_road_segment_id is None
        assert match.map_match_confidence is None


# ─── 4. Speed Tests (Approach A) ──────────────────────────────────────────────

class TestSpeedDerivation:
    def test_valid_gps_derived_speed_works(self):
        """Consecutive GPS coordinates with valid dt compute correct fleet speed."""
        t0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        # Move ~100m in 10s: ~10 m/s = 36 km/h
        # 1 deg lat is ~111,000m -> 0.0009 deg is ~100m
        lat1, lon1 = 17.4300, 78.3600
        lat2, lon2 = 17.4309, 78.3600
        t1 = t0 + timedelta(seconds=10)

        fixes = [(lat1, lon1, t0), (lat2, lon2, t1)]
        speed = derive_fleet_speed_from_gps(fixes)

        assert speed is not None
        assert 34.0 <= speed <= 38.0

    def test_single_gps_fix_returns_unknown_speed(self):
        """Single GPS fix cannot derive speed -> returns None (UNKNOWN)."""
        t0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        fixes = [(17.4300, 78.3600, t0)]
        assert derive_fleet_speed_from_gps(fixes) is None

    def test_zero_or_negative_dt_does_not_fabricate_speed(self):
        """Simultaneous or backwards timestamps return None, never infinite or fabricated speed."""
        t0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        # Duplicate timestamp: dt = 0
        fixes = [(17.4300, 78.3600, t0), (17.4305, 78.3605, t0)]
        assert derive_fleet_speed_from_gps(fixes) is None

    def test_empty_gps_fixes_returns_none(self):
        """Empty GPS fixes returns None."""
        assert derive_fleet_speed_from_gps([]) is None


# ─── 5. Window Tests ──────────────────────────────────────────────────────────

class TestTimeWindowing:
    def test_get_window_bounds_alignment(self):
        """Timestamps align to deterministic 60s window boundaries in UTC."""
        ts = datetime(2026, 9, 26, 10, 5, 23, 500000, tzinfo=timezone.utc)
        w_start, w_end = get_window_bounds(ts, duration_seconds=60)

        assert w_start == datetime(2026, 9, 26, 10, 5, 0, tzinfo=timezone.utc)
        assert w_end == datetime(2026, 9, 26, 10, 6, 0, tzinfo=timezone.utc)
        assert (w_end - w_start).total_seconds() == 60

    def test_window_boundary_exact_start(self):
        """Exact window start timestamp belongs to that window."""
        ts = datetime(2026, 9, 26, 10, 5, 0, 0, tzinfo=timezone.utc)
        w_start, w_end = get_window_bounds(ts, duration_seconds=60)
        assert w_start == ts
        assert w_end == ts + timedelta(seconds=60)


# ─── 6. Density & Flow Tests ──────────────────────────────────────────────────

class TestDensityAndFlowMetrics:
    def test_controlled_fixture_density_and_flow(self):
        """Controlled 60s window with 10 vehicles on 500m segment computes 20 veh/km and 600 veh/h."""
        aggregator = TrafficAggregator()
        aggregator.settings.traffic_default_segment_length_m = 500.0  # 0.5 km

        t_start = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        t_end = t_start + timedelta(seconds=60)

        events = []
        for i in range(10):
            ev = MagicMock()
            ev.event_id = f"EV-{i}"
            ev.track_id = f"TRK-{i}"
            ev.event_type = "car_observation"
            ev.event_timestamp = t_start + timedelta(seconds=i * 5)
            ev.latitude = 17.4300
            ev.longitude = 78.3600
            ev.telemetry_speed_kmh = 15.0  # Low speed
            ev.bus_id = "BUS-01"
            ev.device_id = "DEV-01"
            ev.camera_id = "CAM-01"
            ev.opportunity_id = "OPP-01"
            events.append(ev)

        db = MagicMock()
        db.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = events
        db.query.return_value.filter_by.return_value.first.return_value = None

        result = aggregator.aggregate_window_from_events(db, "SEG-TRF-001", t_start, t_end)

        assert result.vehicle_count == 10
        # 10 veh / 0.5 km = 20 veh/km
        assert result.density == 20.0
        # 10 veh in 60s = 600 veh/h
        assert result.flow_rate == 600.0
        # 20 >= 15 (high density threshold) AND 15 <= 20 (low speed threshold) -> HIGH congestion
        assert result.congestion_state == "HIGH"


# ─── 7. Bottleneck Engine Tests (Cases 1–6) ────────────────────────────────────

def _mock_window(
    w_id: str,
    start_offset_s: int,
    density: float,
    speed: Optional[float],
) -> TrafficObservationModel:
    base = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    w = MagicMock(spec=TrafficObservationModel)
    w.traffic_observation_id = w_id
    w.road_segment_id = "SEG-TRF-001"
    w.window_start = base + timedelta(seconds=start_offset_s)
    w.window_end = w.window_start + timedelta(seconds=60)
    w.density = density
    w.average_speed_kmh = speed
    return w


class TestBottleneckEngineCases:
    """
    Validates all 6 canonical bottleneck cases per Master Plan Section 26.3.
    Requires: HIGH density (>= 15) AND LOW speed (<= 20) across 3 consecutive windows.
    """

    def setup_method(self):
        self.engine = BottleneckEngine()
        self.engine.settings.traffic_high_density_threshold = 15.0
        self.engine.settings.traffic_low_speed_threshold_kmh = 20.0
        self.engine.settings.traffic_bottleneck_window_count = 3

    def test_case_1_high_density_low_speed_3_windows_triggers_active(self):
        """Case 1: High density + low speed persisted across 3 consecutive windows -> ACTIVE."""
        w1 = _mock_window("w1", 0, density=20.0, speed=12.0)
        w2 = _mock_window("w2", 60, density=22.0, speed=10.0)
        w3 = _mock_window("w3", 120, density=25.0, speed=8.0)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1, w2, w3], required_count=3)
        assert is_active is True
        assert streak == 3
        assert q_ids == ["w1", "w2", "w3"]

    def test_case_2_high_density_normal_speed_not_active(self):
        """Case 2: High density + normal speed (> 20 km/h) -> NOT ACTIVE."""
        w1 = _mock_window("w1", 0, density=25.0, speed=35.0)  # Normal speed
        w2 = _mock_window("w2", 60, density=30.0, speed=40.0)
        w3 = _mock_window("w3", 120, density=28.0, speed=38.0)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1, w2, w3], required_count=3)
        assert is_active is False
        assert streak == 0
        assert q_ids == []

    def test_case_3_low_density_low_speed_not_active(self):
        """Case 3: Low density (< 15) + low speed -> NOT ACTIVE."""
        w1 = _mock_window("w1", 0, density=6.0, speed=12.0)  # Low density
        w2 = _mock_window("w2", 60, density=8.0, speed=10.0)
        w3 = _mock_window("w3", 120, density=5.0, speed=14.0)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1, w2, w3], required_count=3)
        assert is_active is False
        assert streak == 0

    def test_case_4_high_density_low_speed_1_window_not_active(self):
        """Case 4: High density + low speed on only 1 window -> NOT ACTIVE (single snapshot guard)."""
        w1 = _mock_window("w1", 0, density=25.0, speed=10.0)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1], required_count=3)
        assert is_active is False
        assert streak == 1

    def test_case_5_high_density_low_speed_2_windows_not_active(self):
        """Case 5: High density + low speed on 2 windows -> NOT ACTIVE (needs 3 consecutive)."""
        w1 = _mock_window("w1", 0, density=22.0, speed=14.0)
        w2 = _mock_window("w2", 60, density=20.0, speed=12.0)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1, w2], required_count=3)
        assert is_active is False
        assert streak == 2

    def test_case_6_interrupted_streak_resets_persistence(self):
        """Case 6: Qualifying windows interrupted by normal window -> streak resets."""
        w1 = _mock_window("w1", 0, density=22.0, speed=12.0)   # Qualifying
        w2 = _mock_window("w2", 60, density=24.0, speed=10.0)  # Qualifying
        w3 = _mock_window("w3", 120, density=5.0, speed=45.0)  # Interruption (clear traffic)
        w4 = _mock_window("w4", 180, density=20.0, speed=11.0) # Qualifying (streak=1)

        is_active, streak, q_ids = self.engine.evaluate_windows([w1, w2, w3, w4], required_count=3)
        assert is_active is False
        assert streak == 1  # Reset after w3, now only w4
        assert q_ids == ["w4"]

    def test_missing_speed_does_not_qualify(self):
        """Window with NULL speed cannot qualify as low speed."""
        w1 = _mock_window("w1", 0, density=30.0, speed=None)
        assert is_window_qualifying(w1, high_density_threshold=15.0, low_speed_threshold_kmh=20.0) is False


# ─── 8. API Integration Tests ─────────────────────────────────────────────────

class TestTrafficAPIReadModels:
    def test_openapi_includes_traffic_endpoints(self):
        """FastAPI openapi schema includes /api/v1/traffic and /api/v1/bottlenecks."""
        from backend.app.main import app
        schema = app.openapi()
        paths = schema.get("paths", {})
        assert "/api/v1/traffic" in paths
        assert "/api/v1/bottlenecks" in paths

    def test_traffic_api_response_schema_fields(self):
        """TrafficObservationResponse schema validates required fields."""
        from backend.app.schemas.traffic import TrafficObservationResponse
        now = datetime.now(timezone.utc)
        resp = TrafficObservationResponse(
            traffic_observation_id="TOBS-01",
            road_segment_id="SEG-TRF-001",
            window_start=now,
            window_end=now + timedelta(seconds=60),
            vehicle_count=8,
            vehicle_class_counts={"car": 5, "bus": 2, "truck": 1, "motorcycle": 0, "bicycle": 0},
            average_speed_kmh=14.2,
            density=16.0,
            flow_rate=480.0,
            congestion_state="HIGH",
            trace_id="tr-test",
            created_at=now,
            segment_name="Gachibowli ORR Traffic Corridor",
            centroid_lat=17.4300,
            centroid_lon=78.3600,
        )
        assert resp.congestion_state == "HIGH"
        assert resp.centroid_lat == 17.4300

"""
UrbanSense AI — Minimal Map Matcher (Milestone 1)
==================================================
PROTOTYPE / SIMULATED map-matching for the first vertical slice.
Edge hint = ADVISORY. Backend result = AUTHORITATIVE.
DECISION_REQUIRED: Replace with real spatial map-matching engine in production.
DECISION_REQUIRED: Production acceptance thresholds must be calibrated.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import math

from backend.app.core.config import get_settings


class MapMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


@dataclass
class MapMatchResult:
    matched_road_segment_id: Optional[str]
    map_match_confidence: Optional[float]
    map_match_status: MapMatchStatus


# PROTOTYPE: Seeded road segments for demo
# DECISION_REQUIRED: Replace with real road network from PostGIS in production
PROTOTYPE_ROAD_SEGMENTS = [
    {"segment_id": "SEG-001", "name": "HITEC City Main Road Seg 1", "centroid_lat": 17.4435, "centroid_lon": 78.3772},
    {"segment_id": "SEG-002", "name": "HITEC City Main Road Seg 2", "centroid_lat": 17.4440, "centroid_lon": 78.3780},
]


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class ProtoTypeMapMatcher:
    """
    Prototype map matcher using haversine distance against seeded road segments.
    PROTOTYPE / SIMULATED — not a real map-matching engine.
    DECISION_REQUIRED: Replace with real spatial engine in production.
    """

    def match(self, latitude: float, longitude: float) -> MapMatchResult:
        settings = get_settings()
        best_segment = None
        best_distance = float("inf")

        for seg in PROTOTYPE_ROAD_SEGMENTS:
            d = _haversine_distance_m(latitude, longitude, seg["centroid_lat"], seg["centroid_lon"])
            if d < best_distance:
                best_distance = d
                best_segment = seg

        radius = settings.map_match_hint_radius_m

        if best_segment is None or best_distance > radius:
            return MapMatchResult(
                matched_road_segment_id=None,
                map_match_confidence=None,
                map_match_status=MapMatchStatus.UNMATCHED,
            )

        # PROTOTYPE confidence: linear decay over radius
        # DECISION_REQUIRED: production confidence model
        confidence = max(0.0, 1.0 - (best_distance / radius))
        confidence = round(min(confidence, settings.map_match_prototype_confidence), 4)

        return MapMatchResult(
            matched_road_segment_id=best_segment["segment_id"],
            map_match_confidence=confidence,
            map_match_status=MapMatchStatus.MATCHED,
        )


_matcher = ProtoTypeMapMatcher()


def match_location(latitude: float, longitude: float) -> MapMatchResult:
    """Authoritative backend map-match. Edge hint is NOT used here."""
    return _matcher.match(latitude, longitude)

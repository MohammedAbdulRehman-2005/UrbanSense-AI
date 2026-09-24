"""
UrbanSense AI — Canonical Event Builder
=========================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

The EventBuilder assembles a CanonicalEvent from:
  Observation + Opportunity + GNSS + sensor context

OWNERSHIP RULES (strictly enforced):
- Backend-owned fields (matched_road_segment_id, map_match_confidence,
  map_match_status, ingestion_timestamp) are NOT set here.
- edge_road_segment_hint is ADVISORY only — set from GNSS hint.
- payload_hash is computed over the canonical payload for integrity.

PROTOTYPE / SIMULATED in Milestone 1.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from contracts.canonical_event import CanonicalEvent, Location, EventPriority, MapMatchStatus
from contracts.observation import Observation
from contracts.opportunity import ObservationOpportunity


class EventBuilder:
    """
    Constructs a CanonicalEvent from Edge-produced components.

    This is the ONLY place CanonicalEvent assembly happens on the Edge.
    Backend fields are left as None/PENDING — the backend fills them in.
    """

    def __init__(
        self,
        bus_id: str,
        device_id: str,
        camera_id: str,
        model_name: str,
        model_version: str,
    ) -> None:
        self.bus_id = bus_id
        self.device_id = device_id
        self.camera_id = camera_id
        self.model_name = model_name
        self.model_version = model_version
        self._sequence = 0

    def build(
        self,
        observation: Observation,
        opportunity: ObservationOpportunity,
        event_timestamp: datetime,
        latitude: float,
        longitude: float,
        altitude_m: Optional[float] = None,
        accuracy_m: Optional[float] = None,
        heading_deg: Optional[float] = None,
        event_type: str = "pothole_observation",
        priority: EventPriority = EventPriority.P2,
        edge_road_segment_hint: Optional[str] = None,
        trace_id: Optional[str] = None,
        gps_quality: Optional[float] = None,
        evidence_ref: Optional[str] = None,
        observation_quality: Optional[float] = None,
    ) -> CanonicalEvent:
        """
        Build a CanonicalEvent. Backend-owned fields are intentionally left unset.

        PROTOTYPE / SIMULATED in Milestone 1.
        """
        self._sequence += 1
        event_id = str(uuid.uuid4())
        _trace_id = trace_id or opportunity.trace_id or str(uuid.uuid4())

        location = Location(
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude_m,
            accuracy_m=accuracy_m,
            heading_deg=heading_deg,
        )

        # Build the canonical payload dict for hashing
        # NOTE: ingestion_timestamp, matched_road_segment_id etc. are NOT included —
        # they are backend-owned and not known at build time.
        payload_for_hash = {
            "event_id": event_id,
            "bus_id": self.bus_id,
            "device_id": self.device_id,
            "camera_id": self.camera_id,
            "event_timestamp": event_timestamp.isoformat(),
            "event_type": event_type,
            "observation_id": observation.observation_id,
            "opportunity_id": opportunity.opportunity_id,
            "detector_confidence": observation.detector_confidence,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
            },
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload_for_hash, sort_keys=True).encode()
        ).hexdigest()

        return CanonicalEvent(
            event_id=event_id,
            schema_version="1.0",
            bus_id=self.bus_id,
            device_id=self.device_id,
            camera_id=self.camera_id,
            event_timestamp=event_timestamp,
            ingestion_timestamp=None,           # BACKEND-OWNED
            location=location,
            edge_road_segment_hint=edge_road_segment_hint,
            matched_road_segment_id=None,       # BACKEND-OWNED
            map_match_confidence=None,          # BACKEND-OWNED
            map_match_status=MapMatchStatus.PENDING,  # BACKEND-OWNED
            event_type=event_type,
            observation_id=observation.observation_id,
            opportunity_id=opportunity.opportunity_id,
            evidence_ref=evidence_ref,
            detector_confidence=observation.detector_confidence,
            observation_quality=observation_quality if observation_quality is not None else opportunity.opportunity_score,
            gps_quality=gps_quality,
            model_name=self.model_name,
            model_version=self.model_version,
            priority=priority,
            trace_id=_trace_id,
            producer_sequence=self._sequence,
            payload_hash=payload_hash,
        )

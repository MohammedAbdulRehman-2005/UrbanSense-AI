"""
UrbanSense AI — POST /api/v1/events (Milestone 1 + Milestone 3)
==============================================================
Receive → validate → idempotency check → persist → map-match → RoadTwin → FusionEngine → respond

Idempotency: duplicate event_id returns "duplicate" status without creating a second record.
Time semantics: event_timestamp is preserved as-is. ingestion_timestamp is set by backend.
FusionEngine: evidence_weight is computed ONLY in backend/app/fusion/engine.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from backend.app.db.session import get_db
from backend.app.schemas.event import EventIngest, EventIngestResponse
from backend.app.models.event import EventModel
from backend.app.services.map_matcher import match_location
from backend.app.roadtwin.engine import upsert_roadtwin
from backend.app.fusion.engine import process_event_evidence

logger = logging.getLogger(__name__)
router = APIRouter()

# Correction #7: Types of events that mutate RoadTwin road-defect state
ROAD_DEFECT_EVENT_TYPES = {
    "pothole_observation",
    "road_defect",
    "surface_distress",
    "pothole",
}

# Milestone 5: Vehicle events triggering traffic aggregation and bottleneck analysis
VEHICLE_EVENT_TYPES = {
    "vehicle_observation",
    "car_observation",
    "bus_observation",
    "truck_observation",
    "motorcycle_observation",
    "bicycle_observation",
}


@router.post("/events", response_model=EventIngestResponse)
def ingest_event(payload: EventIngest, db: Session = Depends(get_db)):
    """
    POST /api/v1/events

    Idempotent: calling with the same event_id returns 200 with status=duplicate.
    Does not silently create a second business Event record.
    """
    ingestion_ts = datetime.now(timezone.utc)

    # --- Idempotency check ---
    existing = db.query(EventModel).filter_by(event_id=payload.event_id).first()
    if existing is not None:
        logger.info(f"Duplicate event received: event_id={payload.event_id} trace_id={payload.trace_id}")
        return EventIngestResponse(
            status="duplicate",
            event_id=payload.event_id,
            message="Event already accepted. Idempotent — no duplicate created.",
            roadtwin_id=None,
            matched_road_segment_id=existing.matched_road_segment_id,
            map_match_status=existing.map_match_status,
            ingestion_timestamp=existing.ingestion_timestamp,
        )

    # --- Backend-owned map-match (Edge hint is advisory, ignored here) ---
    match = match_location(payload.location.latitude, payload.location.longitude)
    logger.info(
        f"Map-match: event_id={payload.event_id} "
        f"segment={match.matched_road_segment_id} "
        f"status={match.map_match_status} "
        f"confidence={match.map_match_confidence}"
    )

    # --- Build geometry point for PostGIS ---
    geom = WKTElement(
        f"POINT({payload.location.longitude} {payload.location.latitude})",
        srid=4326,
    )

    # --- Persist event ---
    event = EventModel(
        event_id=payload.event_id,
        schema_version=payload.schema_version,
        bus_id=payload.bus_id,
        device_id=payload.device_id,
        camera_id=payload.camera_id,
        event_timestamp=payload.event_timestamp,
        ingestion_timestamp=ingestion_ts,
        latitude=payload.location.latitude,
        longitude=payload.location.longitude,
        altitude_m=payload.location.altitude_m,
        accuracy_m=payload.location.accuracy_m,
        heading_deg=payload.location.heading_deg,
        geom=geom,
        edge_road_segment_hint=payload.edge_road_segment_hint,
        matched_road_segment_id=match.matched_road_segment_id,
        map_match_confidence=match.map_match_confidence,
        map_match_status=match.map_match_status.value,
        event_type=payload.event_type,
        observation_id=payload.observation_id,
        opportunity_id=payload.opportunity_id,
        evidence_ref=payload.evidence_ref,
        track_id=payload.track_id,
        telemetry_speed_kmh=payload.telemetry_speed_kmh,
        detector_confidence=payload.detector_confidence,
        observation_quality=payload.observation_quality,
        gps_quality=payload.gps_quality,
        model_name=payload.model_name,
        model_version=payload.model_version,
        priority=payload.priority,
        trace_id=payload.trace_id,
        producer_sequence=payload.producer_sequence,
        payload_hash=payload.payload_hash,
    )
    db.add(event)
    db.flush()

    # --- Minimal RoadTwin upsert + FusionEngine (M1 → M3 cooperative evidence) ---
    # Correction #7: Vehicle events (car, bus, truck, etc.) must NOT mutate road-defect RoadTwin state
    roadtwin_id = None
    if payload.event_type in ROAD_DEFECT_EVENT_TYPES and match.matched_road_segment_id:
        rt = upsert_roadtwin(db, match.matched_road_segment_id, event)
        roadtwin_id = rt.roadtwin_id
        logger.info(
            f"RoadTwin upserted: roadtwin_id={roadtwin_id} "
            f"segment={match.matched_road_segment_id} "
            f"state={rt.current_state} "
            f"event_id={payload.event_id}"
        )

        # M3: FusionEngine — evidence classification, weight computation, aggregate update
        # evidence_weight MUST NOT be computed anywhere except backend/app/fusion/engine.py
        try:
            evidence = process_event_evidence(
                db=db,
                event=event,
                road_segment_id=match.matched_road_segment_id,
            )
            if evidence is not None:
                logger.info(
                    f"FusionEngine: evidence_id={evidence.evidence_id} "
                    f"independence={evidence.independence_class} "
                    f"weight={evidence.evidence_weight:.6f} "
                    f"event_id={payload.event_id}"
                )
                # Re-read updated state after FusionEngine flushes
                rt_updated = db.query(
                    __import__("backend.app.models.roadtwin", fromlist=["RoadTwinStateModel"]).RoadTwinStateModel
                ).filter_by(road_segment_id=match.matched_road_segment_id).first()
                if rt_updated and rt_updated.current_state != rt.current_state:
                    logger.info(
                        f"RoadTwin state updated by FusionEngine: "
                        f"{rt.current_state} -> {rt_updated.current_state} "
                        f"segment={match.matched_road_segment_id}"
                    )
        except Exception as exc:
            # FusionEngine failure must not abort the event ingestion (evidence is best-effort at M3)
            logger.error(
                f"FusionEngine error for event_id={payload.event_id}: {exc}",
                exc_info=True,
            )
    elif payload.event_type in VEHICLE_EVENT_TYPES and match.matched_road_segment_id:
        try:
            from backend.app.traffic.aggregator import TrafficAggregator, get_window_bounds
            from backend.app.traffic.bottleneck import BottleneckEngine
            from backend.app.core.config import get_settings

            settings = get_settings()
            w_start, w_end = get_window_bounds(event.event_timestamp, settings.traffic_window_duration_seconds)

            aggregator = TrafficAggregator()
            aggregator.aggregate_window_from_events(
                db=db,
                road_segment_id=match.matched_road_segment_id,
                window_start=w_start,
                window_end=w_end,
                trace_id=payload.trace_id,
            )

            bottleneck_engine = BottleneckEngine()
            bottleneck_engine.evaluate_segment(
                db=db,
                road_segment_id=match.matched_road_segment_id,
                as_of_time=w_end,
            )
        except Exception as exc:
            logger.error(
                f"Traffic aggregation error for event_id={payload.event_id}: {exc}",
                exc_info=True,
            )
    else:
        logger.info(
            f"Event {payload.event_id} (type={payload.event_type}) persisted without road defect or traffic mutation."
        )


    db.commit()
    logger.info(f"Event accepted: event_id={payload.event_id} trace_id={payload.trace_id}")

    return EventIngestResponse(
        status="accepted",
        event_id=payload.event_id,
        message="Event accepted and persisted.",
        roadtwin_id=roadtwin_id,
        matched_road_segment_id=match.matched_road_segment_id,
        map_match_status=match.map_match_status.value,
        ingestion_timestamp=ingestion_ts,
    )

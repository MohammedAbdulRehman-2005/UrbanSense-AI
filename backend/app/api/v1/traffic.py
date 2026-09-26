"""
UrbanSense AI — Traffic Intelligence API (Milestone 5)
=======================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Section 33.4)

Endpoints:
- GET /api/v1/traffic: Query windowed traffic observations by segment/time.
- GET /api/v1/bottlenecks: Query active or historical bottleneck conditions.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.traffic import TrafficObservationModel, TrafficBottleneckModel
from backend.app.models.road_segment import RoadSegment
from backend.app.schemas.traffic import TrafficObservationResponse, BottleneckResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/traffic", response_model=List[TrafficObservationResponse])
def get_traffic_observations(
    road_segment_id: Optional[str] = Query(default=None, description="Filter by road segment ID"),
    start_time: Optional[datetime] = Query(default=None, description="Filter windows ending after start_time"),
    end_time: Optional[datetime] = Query(default=None, description="Filter windows starting before end_time"),
    limit: int = Query(default=100, ge=1, le=500, description="Max observations to return"),
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/traffic
    Retrieve aggregated traffic observation records with deduplicated vehicle counts,
    speed, density, and flow metrics.
    """
    query = db.query(TrafficObservationModel)

    if road_segment_id:
        query = query.filter(TrafficObservationModel.road_segment_id == road_segment_id)
    if start_time:
        query = query.filter(TrafficObservationModel.window_end >= start_time)
    if end_time:
        query = query.filter(TrafficObservationModel.window_start <= end_time)

    records = query.order_by(TrafficObservationModel.window_start.desc()).limit(limit).all()

    # Enrich with road segment spatial metadata
    segment_ids = {r.road_segment_id for r in records}
    segments = {
        s.segment_id: s
        for s in db.query(RoadSegment).filter(RoadSegment.segment_id.in_(segment_ids)).all()
    } if segment_ids else {}

    results = []
    for r in records:
        seg = segments.get(r.road_segment_id)
        results.append(
            TrafficObservationResponse(
                traffic_observation_id=r.traffic_observation_id,
                road_segment_id=r.road_segment_id,
                window_start=r.window_start,
                window_end=r.window_end,
                bus_id=r.bus_id,
                device_id=r.device_id,
                camera_id=r.camera_id,
                sensing_pass_id=r.sensing_pass_id,
                vehicle_count=r.vehicle_count,
                vehicle_class_counts=r.vehicle_class_counts or {},
                average_speed_kmh=r.average_speed_kmh,
                density=r.density,
                flow_rate=r.flow_rate,
                congestion_state=r.congestion_state,
                trace_id=r.trace_id,
                created_at=r.created_at,
                segment_name=seg.name if seg else None,
                centroid_lat=seg.centroid_lat if seg else None,
                centroid_lon=seg.centroid_lon if seg else None,
            )
        )
    return results


@router.get("/bottlenecks", response_model=List[BottleneckResponse])
def get_bottlenecks(
    road_segment_id: Optional[str] = Query(default=None, description="Filter by road segment ID"),
    status: Optional[str] = Query(default="ACTIVE", description="Filter by status (ACTIVE, RESOLVED, or ALL)"),
    limit: int = Query(default=50, ge=1, le=200, description="Max bottleneck records to return"),
    db: Session = Depends(get_db),
):
    """
    GET /api/v1/bottlenecks
    Retrieve persistent bottleneck states identified across rolling 3-windows.
    Exposes explainability: density condition, speed condition, qualifying window streak.
    """
    query = db.query(TrafficBottleneckModel)

    if road_segment_id:
        query = query.filter(TrafficBottleneckModel.road_segment_id == road_segment_id)
    if status and status.upper() != "ALL":
        query = query.filter(TrafficBottleneckModel.status == status.upper())

    records = query.order_by(TrafficBottleneckModel.start_time.desc()).limit(limit).all()

    segment_ids = {r.road_segment_id for r in records}
    segments = {
        s.segment_id: s
        for s in db.query(RoadSegment).filter(RoadSegment.segment_id.in_(segment_ids)).all()
    } if segment_ids else {}

    results = []
    for r in records:
        seg = segments.get(r.road_segment_id)
        results.append(
            BottleneckResponse(
                bottleneck_id=r.bottleneck_id,
                road_segment_id=r.road_segment_id,
                status=r.status,
                severity=r.severity,
                density_condition=r.density_condition,
                speed_condition=r.speed_condition,
                qualifying_window_count=r.qualifying_window_count,
                required_window_count=r.required_window_count,
                first_qualifying_window_start=r.first_qualifying_window_start,
                latest_qualifying_window_end=r.latest_qualifying_window_end,
                evidence_window_ids=r.evidence_window_ids or [],
                start_time=r.start_time,
                resolved_at=r.resolved_at,
                segment_name=seg.name if seg else None,
                centroid_lat=seg.centroid_lat if seg else None,
                centroid_lon=seg.centroid_lon if seg else None,
            )
        )
    return results

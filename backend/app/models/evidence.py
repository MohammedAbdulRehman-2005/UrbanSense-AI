"""
UrbanSense AI — Evidence ORM Model (Milestone 3)
================================================
Evidence is BACKEND-OWNED. It is produced by the FusionEngine after
deduplication and independence classification.

Do NOT compute evidence_weight in Edge, EventBuilder, OpportunityEvaluator,
any API route, or the frontend. The ONLY place is backend/app/fusion/engine.py.

Append-only: Evidence records are never deleted or mutated after creation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Integer, Boolean
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class EvidenceModel(Base):
    __tablename__ = "evidence"

    evidence_id = Column(String, primary_key=True)

    # Source provenance
    event_id = Column(String, nullable=True, index=True)  # nullable for negative evidence
    observation_id = Column(String, nullable=True)
    opportunity_id = Column(String, nullable=True)

    # Identity
    polarity = Column(String, nullable=False)  # POSITIVE | NEGATIVE
    source_type = Column(String, nullable=False, default="BUS_CAMERA")
    source_id = Column(String, nullable=True)  # bus_id for cross-bus dedup
    bus_id = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=True)
    camera_id = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)  # event_timestamp (event-time)
    ingestion_timestamp = Column(DateTime(timezone=True), nullable=False)

    # Spatial
    matched_road_segment_id = Column(String, nullable=True, index=True)
    map_match_status = Column(String, nullable=True)

    # Quality signals (inputs to fusion formula)
    # evidence_weight = detector_confidence * observation_quality * gps_quality (MVP)
    # PROTOTYPE: signals are uncalibrated heuristic outputs; see DECISION-020
    detector_confidence = Column(Float, nullable=True)   # null for negative evidence
    observation_quality = Column(Float, nullable=True)
    opportunity_score = Column(Float, nullable=True)
    gps_quality = Column(Float, nullable=True)
    sensor_health = Column(Float, nullable=True)

    # Independence classification
    independence_class = Column(String, nullable=False)  # INDEPENDENT | CORRELATED | DUPLICATE
    correlation_group_id = Column(String, nullable=True)

    # Computed evidence weight (ONLY set by FusionEngine)
    evidence_weight = Column(Float, nullable=False)

    # Fusion metadata
    fusion_strategy = Column(String, nullable=False, default="MVP")
    fusion_version = Column(String, nullable=False, default="1.0")

    # Negative evidence path
    negative_evidence_strength = Column(Float, nullable=True)

    # Research / future fields (nullable)
    source_reliability = Column(Float, nullable=True)
    temporal_consistency = Column(Float, nullable=True)
    spatial_consistency = Column(Float, nullable=True)
    historical_consistency = Column(Float, nullable=True)
    independence_score = Column(Float, nullable=True)
    correlation_penalty = Column(Float, nullable=True)

    # Lineage
    lineage = Column(String, nullable=True)  # JSON string describing derivation chain

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

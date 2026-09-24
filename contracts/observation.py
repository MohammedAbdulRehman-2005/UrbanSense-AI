"""
UrbanSense AI — Observation Contract
=====================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

An Observation is the raw AI-detector output attached to a single frame.
It is produced by the Edge module after running an object-detection model.

SEMANTIC NOTES:
- `detector_confidence` = the model's raw output confidence score.
  It is NOT evidence confidence, NOT RoadTwin confidence, NOT truth confidence.
  Do NOT generalise this to a field named "confidence".
- `object_type` is the detector class label, not a UrbanSense semantic type.
- Fields marked SIMULATED are deterministic stubs used in Milestone 1.
  They do not represent real sensor or model output.

DATA SHAPES ONLY. No business logic here.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
import uuid


class BoundingBox(BaseModel):
    """Pixel-space bounding box from the detector."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    frame_width: int
    frame_height: int


class Observation(BaseModel):
    """
    AI detector output for a single detected object in a single frame.

    Edge-produced. Backend reads but does not own the core fields.
    """

    observation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable unique identifier for this detection instance.",
    )
    frame_id: str = Field(
        description="Identifier of the video frame from which this observation was made."
    )
    bus_id: str = Field(description="Fleet vehicle that produced this observation.")
    device_id: str = Field(description="Edge compute device on the bus.")
    camera_id: str = Field(description="Camera module that captured the frame.")

    timestamp: datetime = Field(
        description="UTC time of the frame capture. This is event_timestamp semantics."
    )

    object_type: str = Field(
        description=(
            "Detector class label (e.g. 'pothole', 'road_crack', 'vehicle'). "
            "This is the raw class, not a UrbanSense semantic category."
        )
    )

    # IMPORTANT: this is the model's raw softmax/score output, not a fused score.
    detector_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Raw model output confidence [0.0, 1.0]. "
            "This is NOT evidence confidence, NOT RoadTwin confidence."
        ),
    )

    bbox: BoundingBox = Field(description="Bounding box in pixel space.")

    # Optional fields — present only when the pipeline supports them
    mask_reference: Optional[str] = Field(
        default=None,
        description="Reference to segmentation mask (GCS/MinIO key). Optional.",
    )
    track_id: Optional[str] = Field(
        default=None,
        description="Multi-frame track identifier. Optional.",
    )
    trajectory_reference: Optional[str] = Field(
        default=None,
        description="Reference to trajectory data. Optional.",
    )

    model_name: str = Field(description="Name of the detector model.")
    model_version: str = Field(description="Version of the detector model.")

    evidence_hint: Optional[str] = Field(
        default=None,
        description=(
            "Advisory hint from Edge about evidence quality. "
            "Backend is not obligated to follow this."
        ),
    )

    model_config = ConfigDict()

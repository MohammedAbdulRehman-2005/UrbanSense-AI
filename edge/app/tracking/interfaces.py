"""
UrbanSense AI — Tracking Abstraction (Milestone 2)
===================================================
Provides same-camera temporal tracking interface.

HARD SCOPE BOUNDARY:
- Same-camera temporal tracking ONLY.
- NO cross-bus vehicle re-identification.
- Never claim two detections from different buses or cameras are the same physical object.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from contracts.observation import BoundingBox
from edge.app.perception.detectors.base import RawDetection


@dataclass
class TrackedObject:
    """
    Representation of an active or updated tracked object.
    """
    track_id: str
    class_name: str
    bbox: BoundingBox
    detector_confidence: float
    timestamp: datetime
    camera_id: str
    bus_id: str
    track_quality: float                 # Confidence in tracking continuity [0, 1]
    trajectory_reference: Optional[str] = None  # Reference to recorded trajectory points
    trajectory_points: List[tuple[float, float]] = field(default_factory=list)
    age_frames: int = 1
    missed_frames: int = 0


class BaseTracker(ABC):
    """
    Abstract interface for object tracking.
    """

    @abstractmethod
    def update(
        self,
        detections: List[RawDetection],
        timestamp: datetime,
        frame_id: str,
    ) -> List[TrackedObject]:
        """
        Update tracker with detections from the current frame.
        Returns list of currently active TrackedObject instances.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset all active tracks (e.g., when switching camera or video file)."""
        ...

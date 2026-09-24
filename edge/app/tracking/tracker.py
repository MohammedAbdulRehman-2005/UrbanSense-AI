"""
UrbanSense AI — Same-Camera Temporal Tracker (Milestone 2)
===========================================================
Implements BaseTracker using IoU and centroid association across sequential frames.

HARD SCOPE BOUNDARY:
- Same-camera tracking only.
- Does NOT perform cross-bus re-identification.
"""
from __future__ import annotations

from typing import List, Dict, Tuple
from datetime import datetime
import uuid

from contracts.observation import BoundingBox
from edge.app.perception.detectors.base import RawDetection
from edge.app.tracking.interfaces import BaseTracker, TrackedObject


def _compute_iou(b1: BoundingBox, b2: BoundingBox) -> float:
    """Calculate Intersection-over-Union between two bounding boxes."""
    x1 = max(b1.x_min, b2.x_min)
    y1 = max(b1.y_min, b2.y_min)
    x2 = min(b1.x_max, b2.x_max)
    y2 = min(b1.y_max, b2.y_max)

    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = (b1.x_max - b1.x_min) * (b1.y_max - b1.y_min)
    area2 = (b2.x_max - b2.x_min) * (b2.y_max - b2.y_min)

    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


class SameCameraTracker(BaseTracker):
    """
    Temporal tracker for objects detected in consecutive frames of the same camera stream.
    """

    def __init__(
        self,
        camera_id: str = "CAMERA-FRONT-01",
        bus_id: str = "BUS-001",
        iou_threshold: float = 0.30,
        max_missed_frames: int = 5,
    ):
        self.camera_id = camera_id
        self.bus_id = bus_id
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self._next_track_num = 1
        self._tracks: Dict[str, TrackedObject] = {}

    def update(
        self,
        detections: List[RawDetection],
        timestamp: datetime,
        frame_id: str,
    ) -> List[TrackedObject]:
        """
        Associate detections to existing tracks via IoU, initiate new tracks,
        and retire stale tracks.
        """
        matched_det_indices = set()
        matched_track_ids = set()

        # Try to match existing active tracks with incoming detections of same class
        for track_id, track in list(self._tracks.items()):
            best_iou = 0.0
            best_idx = -1

            for idx, det in enumerate(detections):
                if idx in matched_det_indices:
                    continue
                if det.object_type != track.class_name:
                    continue

                iou = _compute_iou(track.bbox, det.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx

            if best_iou >= self.iou_threshold and best_idx >= 0:
                det = detections[best_idx]
                matched_det_indices.add(best_idx)
                matched_track_ids.add(track_id)

                # Update track state
                cx = (det.bbox.x_min + det.bbox.x_max) / 2.0
                cy = (det.bbox.y_min + det.bbox.y_max) / 2.0
                track.bbox = det.bbox
                track.detector_confidence = det.detector_confidence
                track.timestamp = timestamp
                track.age_frames += 1
                track.missed_frames = 0
                track.trajectory_points.append((cx, cy))
                # Track quality scales with consistency and match score
                track.track_quality = round(min(1.0, 0.4 + 0.3 * best_iou + 0.3 * min(1.0, track.age_frames / 10.0)), 4)
                det.track_id = track_id
            else:
                track.missed_frames += 1

        # Prune expired tracks
        self._tracks = {
            t_id: t for t_id, t in self._tracks.items()
            if t.missed_frames <= self.max_missed_frames
        }

        # Initialize new tracks for unmatched detections
        for idx, det in enumerate(detections):
            if idx not in matched_det_indices:
                t_id = f"TRK-{self.camera_id}-{self._next_track_num:05d}"
                self._next_track_num += 1

                cx = (det.bbox.x_min + det.bbox.x_max) / 2.0
                cy = (det.bbox.y_min + det.bbox.y_max) / 2.0

                new_track = TrackedObject(
                    track_id=t_id,
                    class_name=det.object_type,
                    bbox=det.bbox,
                    detector_confidence=det.detector_confidence,
                    timestamp=timestamp,
                    camera_id=self.camera_id,
                    bus_id=self.bus_id,
                    track_quality=0.50,  # initial track quality
                    trajectory_reference=f"traj://{t_id}",
                    trajectory_points=[(cx, cy)],
                    age_frames=1,
                    missed_frames=0,
                )
                self._tracks[t_id] = new_track
                det.track_id = t_id

        return list(self._tracks.values())

    def reset(self) -> None:
        self._tracks.clear()
        self._next_track_num = 1

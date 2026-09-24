"""
UrbanSense AI — Baseline Vehicle Detector (Milestone 2)
========================================================
Implements BaseDetector for vehicle category detection:
- car
- bus
- truck
- motorcycle (2W)
- bicycle

NOTE ON HARD SCOPE BOUNDARY:
Vehicle detection alone does NOT equal traffic density or bottleneck analytics.
Vehicle density and traffic flow metrics belong strictly to later analytics milestones.
"""
from __future__ import annotations

from typing import List, Optional
import cv2
import numpy as np

from contracts.observation import BoundingBox
from edge.app.hal.interfaces import CameraFrame
from edge.app.perception.detectors.base import BaseDetector, RawDetection


class BaselineVehicleDetector(BaseDetector):
    """
    Baseline vehicle detector identifying traffic objects in road scenes.
    Uses candidate bounding region extraction and classification heuristics.
    Interface is 100% plug-and-play with YOLO/ONNX models in Milestone 3+.
    """

    SUPPORTED_CLASSES = ("car", "bus", "truck", "motorcycle", "bicycle")

    def __init__(
        self,
        min_area: int = 600,
        confidence_threshold: float = 0.50,
        model_name: str = "urbansense-vehicle-baseline-cv",
        model_version: str = "0.2.0-PROTOTYPE",
    ):
        self._min_area = min_area
        self._confidence_threshold = confidence_threshold
        self._model_name = model_name
        self._model_version = model_version

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    def detect(self, frame: CameraFrame) -> List[RawDetection]:
        """
        Detect vehicle objects in the roadway portion of the frame.
        """
        if frame.image is None or not isinstance(frame.image, np.ndarray):
            return []

        img = frame.image
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return []

        # Vehicle search zone: middle 50% vertical (horizon to mid-ground)
        y_start = int(h * 0.25)
        y_end = int(h * 0.75)
        roi = img[y_start:y_end, 0:w]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)

        # Morphological closing to join edge boundaries into closed vehicle hulls
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: List[RawDetection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= self._min_area:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / float(ch) if ch > 0 else 0

                # Determine candidate vehicle class based on geometry
                obj_class = "car"
                if aspect > 1.8 and cw > 150:
                    obj_class = "bus" if cw > 220 else "truck"
                elif aspect < 0.8:
                    obj_class = "motorcycle" if area > 2000 else "bicycle"
                elif 0.8 <= aspect <= 1.8:
                    obj_class = "car"

                # Prototype detector confidence estimation
                det_conf = round(min(0.92, max(0.55, 0.55 + min(0.35, area / 20000.0))), 4)
                if det_conf >= self._confidence_threshold:
                    global_y = y_start + y
                    bbox = BoundingBox(
                        x_min=float(x),
                        y_min=float(global_y),
                        x_max=float(x + cw),
                        y_max=float(global_y + ch),
                        frame_width=w,
                        frame_height=h,
                    )
                    detections.append(
                        RawDetection(
                            object_type=obj_class,
                            detector_confidence=det_conf,
                            bbox=bbox,
                            model_name=self._model_name,
                            model_version=self._model_version,
                        )
                    )

        return detections

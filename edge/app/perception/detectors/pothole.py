"""
UrbanSense AI — Baseline Pothole Detector (Milestone 2)
========================================================
Implements BaseDetector for road surface distress / pothole detection.
Designed with a pluggable provider interface:
- Replaceable by custom YOLO / PyTorch / ONNX models in Milestone 3+
- Model choice recorded as PROPOSED in docs/decision-log.md
"""
from __future__ import annotations

from typing import List, Optional
import cv2
import numpy as np

from contracts.observation import BoundingBox
from edge.app.hal.interfaces import CameraFrame
from edge.app.perception.detectors.base import BaseDetector, RawDetection


class BaselinePotholeDetector(BaseDetector):
    """
    Baseline computer vision pothole detector.
    Analyzes the lower road region of the image for dark, high-gradient depressions.
    Can be replaced transparently by deep learning inference engines.
    """

    def __init__(
        self,
        min_area: int = 200,
        max_area: int = 150000,
        confidence_threshold: float = 0.50,
        model_name: str = "urbansense-pothole-baseline-cv",
        model_version: str = "0.2.0-PROTOTYPE",
    ):
        self._min_area = min_area
        self._max_area = max_area
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
        Detect potholes within the lower road region of the frame.
        """
        if frame.image is None or not isinstance(frame.image, np.ndarray):
            return []

        img = frame.image
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return []

        # Road Region of Interest: lower 60% of front-facing camera frame
        roi_top = int(h * 0.40)
        road_roi = img[roi_top:h, 0:w]

        # Convert to grayscale
        gray = cv2.cvtColor(road_roi, cv2.COLOR_BGR2GRAY) if len(road_roi.shape) == 3 else road_roi
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Detect dark surface depressions relative to local road luminance
        mean_lum = float(np.mean(blurred))
        dark_thresh_val = max(10, int(mean_lum * 0.65))
        _, thresh = cv2.threshold(blurred, dark_thresh_val, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: List[RawDetection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._min_area <= area <= self._max_area:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / float(ch) if ch > 0 else 0
                if 0.3 <= aspect <= 3.5:
                    hull = cv2.convexHull(cnt)
                    hull_area = cv2.contourArea(hull)
                    solidity = float(area) / hull_area if hull_area > 0 else 0.5
                    det_conf = round(min(0.95, max(0.55, 0.55 + 0.35 * solidity)), 4)

                    if det_conf >= self._confidence_threshold:
                        global_y = roi_top + y
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
                                object_type="pothole",
                                detector_confidence=det_conf,
                                bbox=bbox,
                                model_name=self._model_name,
                                model_version=self._model_version,
                            )
                        )

        return detections

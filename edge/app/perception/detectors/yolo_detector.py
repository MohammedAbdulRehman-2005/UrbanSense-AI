"""
UrbanSense AI — Trained YOLO Road Defect Detector
==================================================
Production inference provider implementing BaseDetector using Ultralytics YOLOv11
trained on the curated RDD2022 India dataset.

Architecture:
- Pluggable provider fulfilling edge BaseDetector contract.
- Maps RDD2022 classes (D40, D20, D00, D10, etc.) to UrbanSense canonical defect taxonomy.
- Preserves raw model confidence as detector_confidence.
- Graceful fallbacks and configurable confidence/IOU thresholds.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
import numpy as np

from contracts.observation import BoundingBox
from edge.app.hal.interfaces import CameraFrame
from edge.app.perception.detectors.base import BaseDetector, RawDetection

logger = logging.getLogger(__name__)

# Canonical mapping from RDD2022 classes to UrbanSense domain defect types
RDD_TO_URBANSENSE_DEFECT_MAP: Dict[str, str] = {
    "D40": "pothole",
    "D20": "alligator_crack",
    "D00": "longitudinal_crack",
    "D01": "longitudinal_joint",
    "D10": "transverse_crack",
    "D11": "transverse_joint",
    "D43": "crosswalk_blur",
    "D44": "whiteline_blur",
}

# Default candidate weights search paths
DEFAULT_WEIGHT_PATHS = [
    Path("models/weights/urbansense_yolo11_rdd_best.pt"),
    Path("backend/app/models/urbansense_runs/candidate_b_oversampled/weights/best.pt"),
    Path("backend/app/models/urbansense_runs/candidate_a_baseline/weights/best.pt"),
]


class YOLORoadDefectDetector(BaseDetector):
    """
    Deep learning road damage and surface distress detector powered by YOLOv11.
    Trained on the RDD2022 India dataset.
    """

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        allowed_classes: Optional[Set[str]] = None,
        device: Optional[str] = None,
        model_name: str = "urbansense-yolo11n-rdd2022",
        model_version: str = "1.0.0-candidate_b",
    ):
        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._allowed_classes = allowed_classes
        self._device = device
        self._model_name = model_name
        self._model_version = model_version
        self._model = None
        self._resolved_model_path: Optional[Path] = None

        # Resolve weights path
        env_path = os.getenv("URBANSENSE_YOLO_MODEL_PATH")
        candidate_paths = []
        if model_path:
            candidate_paths.append(Path(model_path))
        if env_path:
            candidate_paths.append(Path(env_path))
        candidate_paths.extend(DEFAULT_WEIGHT_PATHS)

        for p in candidate_paths:
            if p.exists() and p.is_file():
                self._resolved_model_path = p.resolve()
                break

        if self._resolved_model_path is None:
            logger.warning(
                "YOLORoadDefectDetector: No valid model weights found in paths: %s",
                [str(p) for p in candidate_paths],
            )
        else:
            self._load_model()

    def _load_model(self) -> None:
        """Load YOLO model via Ultralytics."""
        try:
            from ultralytics import YOLO
            logger.info("Loading YOLO road defect detector from %s", self._resolved_model_path)
            self._model = YOLO(str(self._resolved_model_path))
            logger.info(
                "YOLO model loaded successfully. Classes: %s",
                getattr(self._model, "names", {}),
            )
        except ImportError:
            logger.error("ultralytics package not installed. YOLORoadDefectDetector unavailable.")
            self._model = None
        except Exception as e:
            logger.error("Failed to load YOLO model from %s: %s", self._resolved_model_path, e)
            self._model = None

    @property
    def is_loaded(self) -> bool:
        """Check if model is successfully loaded and ready for inference."""
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def model_path(self) -> Optional[Path]:
        return self._resolved_model_path

    def detect(self, frame: CameraFrame) -> List[RawDetection]:
        """
        Run inference on the camera frame and return canonical RawDetection objects.
        """
        if frame.image is None or not isinstance(frame.image, np.ndarray):
            return []

        h, w = frame.image.shape[:2]
        if h == 0 or w == 0:
            return []

        if self._model is None:
            logger.debug("YOLORoadDefectDetector not loaded, returning empty detections")
            return []

        try:
            # Run inference
            results = self._model.predict(
                source=frame.image,
                conf=self._confidence_threshold,
                iou=self._iou_threshold,
                device=self._device,
                verbose=False,
            )

            if not results or len(results) == 0:
                return []

            res = results[0]
            boxes = res.boxes
            if boxes is None or len(boxes) == 0:
                return []

            detections: List[RawDetection] = []
            names = getattr(self._model, "names", {})

            for b in boxes:
                cls_id = int(b.cls[0].item())
                conf = float(b.conf[0].item())
                xyxy = b.xyxy[0].tolist()

                raw_class_name = names.get(cls_id, str(cls_id))
                canonical_type = RDD_TO_URBANSENSE_DEFECT_MAP.get(raw_class_name, raw_class_name.lower())

                # Filter by allowed classes if configured
                if self._allowed_classes and canonical_type not in self._allowed_classes and raw_class_name not in self._allowed_classes:
                    continue

                x1, y1, x2, y2 = xyxy

                # Validate and clamp coordinates
                x1 = max(0.0, min(float(w), float(x1)))
                y1 = max(0.0, min(float(h), float(y1)))
                x2 = max(0.0, min(float(w), float(x2)))
                y2 = max(0.0, min(float(h), float(y2)))

                if x2 <= x1 or y2 <= y1:
                    continue

                bbox = BoundingBox(
                    x_min=round(x1, 2),
                    y_min=round(y1, 2),
                    x_max=round(x2, 2),
                    y_max=round(y2, 2),
                    frame_width=w,
                    frame_height=h,
                )

                detections.append(
                    RawDetection(
                        object_type=canonical_type,
                        detector_confidence=round(conf, 4),
                        bbox=bbox,
                        model_name=self._model_name,
                        model_version=self._model_version,
                    )
                )

            return detections

        except Exception as e:
            logger.error("Error during YOLORoadDefectDetector inference: %s", e)
            return []

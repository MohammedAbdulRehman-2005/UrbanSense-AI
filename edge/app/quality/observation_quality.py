"""
UrbanSense AI — Observation Quality Module (Milestone 2)
=========================================================
Calculates explicit semantic quality signals for camera frames and detections:
- blur_score
- illumination_score
- visibility_score
- occlusion_score
- observation_quality (composite)

SEMANTIC RULES:
- Never collapse these signals into a generic 'confidence' field.
- Never create 'final_confidence', 'truth_confidence', or 'road_confidence'.
- Signal ownership:
    GPS quality -> explicit GNSS fix signal
    Sensor health -> explicit hardware health signal
    Observation quality -> derived exclusively from optical / environmental metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np

from contracts.observation import BoundingBox
from edge.app.hal.interfaces import CameraFrame


@dataclass
class QualitySignals:
    """
    Explicit, separated quality dimensions for a frame or detection region.
    """
    blur_score: float             # [0, 1]: 1.0 = sharp, 0.0 = completely blurred
    illumination_score: float     # [0, 1]: 1.0 = optimal lighting, 0.0 = severe under/over exposure
    visibility_score: float       # [0, 1]: 1.0 = clear road visibility, 0.0 = obscured/foggy
    occlusion_score: float        # [0, 1]: 1.0 = fully unoccluded, 0.0 = heavily blocked
    observation_quality: float    # [0, 1]: composite observation quality metric


class ObservationQualityEvaluator:
    """
    Evaluates visual quality of input frames and bounding box crops.
    """

    def evaluate_frame(self, frame: CameraFrame) -> QualitySignals:
        """
        Evaluate full frame optical quality.
        """
        if frame.image is None or not isinstance(frame.image, np.ndarray):
            # Fallback for synthetic/stub frames
            return QualitySignals(
                blur_score=0.88,
                illumination_score=0.90,
                visibility_score=0.85,
                occlusion_score=0.95,
                observation_quality=0.89,
            )

        img = frame.image
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        # 1. Blur measurement via Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        # Normalization: typical variance ranges 0-1000, 100+ is reasonably sharp
        blur_score = round(min(1.0, max(0.0, laplacian_var / 300.0)), 4)

        # 2. Illumination measurement via luminance histogram
        mean_lum = float(np.mean(gray))
        # Ideal luminance is ~128. Penalize below 40 (underexposed) and above 220 (overexposed)
        if mean_lum < 40:
            illum_score = max(0.05, mean_lum / 40.0)
        elif mean_lum > 220:
            illum_score = max(0.05, (255.0 - mean_lum) / 35.0)
        else:
            illum_score = 1.0 - abs(mean_lum - 128.0) / 128.0 * 0.5
        illumination_score = round(float(np.clip(illum_score, 0.0, 1.0)), 4)

        # 3. Visibility measurement via dynamic range / contrast
        contrast = float(np.std(gray))
        visibility_score = round(min(1.0, max(0.0, contrast / 65.0)), 4)

        # 4. Occlusion baseline (assume mostly clear if not obstructed by hood/wiper)
        occlusion_score = 0.95

        # Composite observation quality (weighted mean of visual factors)
        observation_quality = round(
            0.35 * blur_score + 0.35 * illumination_score + 0.20 * visibility_score + 0.10 * occlusion_score,
            4,
        )

        return QualitySignals(
            blur_score=blur_score,
            illumination_score=illumination_score,
            visibility_score=visibility_score,
            occlusion_score=occlusion_score,
            observation_quality=observation_quality,
        )

    def evaluate_detection_crop(self, frame: CameraFrame, bbox: BoundingBox) -> QualitySignals:
        """
        Evaluate localized quality within a specific detection bounding box.
        """
        if frame.image is None or not isinstance(frame.image, np.ndarray):
            return self.evaluate_frame(frame)

        img = frame.image
        h, w = img.shape[:2]

        x1 = max(0, min(w - 1, int(bbox.x_min)))
        y1 = max(0, min(h - 1, int(bbox.y_min)))
        x2 = max(x1 + 1, min(w, int(bbox.x_max)))
        y2 = max(y1 + 1, min(h, int(bbox.y_max)))

        crop = img[y1:y2, x1:x2]
        crop_frame = CameraFrame(
            frame_id=f"{frame.frame_id}-crop",
            camera_id=frame.camera_id,
            timestamp=frame.timestamp,
            width=crop.shape[1],
            height=crop.shape[0],
            simulated=frame.simulated,
            image=crop,
        )
        return self.evaluate_frame(crop_frame)

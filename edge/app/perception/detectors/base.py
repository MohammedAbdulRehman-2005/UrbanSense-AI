"""
UrbanSense AI — Perception Inference Provider Abstraction (Milestone 2)
========================================================================
Defines the replaceable detector interface.
The application is NOT hardcoded to a single model architecture.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import numpy as np

from contracts.observation import BoundingBox
from edge.app.hal.interfaces import CameraFrame


@dataclass
class RawDetection:
    """
    Standard detection output from any perception provider.
    Semantic rule: detector_confidence represents model output probability only.
    No bare 'confidence' field allowed.
    """
    object_type: str
    detector_confidence: float
    bbox: BoundingBox
    model_name: str
    model_version: str
    track_id: Optional[str] = None
    mask_reference: Optional[str] = None


class BaseDetector(ABC):
    """
    Abstract interface for object detection providers.
    Allows substituting ONNX, TensorRT, YOLO, or classical CV baselines without
    altering downstream perception or business logic.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_version(self) -> str:
        ...

    @abstractmethod
    def detect(self, frame: CameraFrame) -> List[RawDetection]:
        """
        Run inference on the given frame.
        Must return list of RawDetection with valid bounding boxes and detector_confidence.
        """
        ...

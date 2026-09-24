"""
UrbanSense AI — HAL File Camera Provider (Milestone 2)
======================================================
Implements CameraProvider for recorded video files (MP4, AVI, etc.).

Encapsulates OpenCV VideoCapture entirely inside this HAL provider.
Perception and business logic interact ONLY through the CameraProvider
interface and CameraFrame dataclass, never touching VideoCapture directly.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterator
import cv2

from edge.app.hal.interfaces import CameraProvider, CameraFrame


class FileCameraProvider(CameraProvider):
    """
    Video file camera provider reading recorded video tracks.
    """

    def __init__(
        self,
        video_path: str,
        camera_id: str = "CAMERA-FRONT-01",
        base_timestamp: Optional[datetime] = None,
        frame_rate: Optional[float] = None,
    ):
        self.video_path = video_path
        self.camera_id = camera_id
        self.base_timestamp = base_timestamp or datetime.now(timezone.utc)
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._fps = frame_rate
        self._width = 0
        self._height = 0
        self._is_open = False
        self._initialize()

    def _initialize(self) -> None:
        if not os.path.exists(self.video_path):
            self._is_open = False
            return

        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            self._is_open = False
            return

        self._is_open = True
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._fps = self._fps or (fps if fps > 0 else 30.0)
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._frame_count = 0

    def capture(self) -> CameraFrame:
        """
        Capture the next sequential frame from the video file.
        Raises EOFError when the video ends, or RuntimeError on decode error.
        """
        if not self._is_open or self._cap is None:
            raise RuntimeError(f"FileCameraProvider is not open or file invalid: {self.video_path}")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self._is_open = False
            raise EOFError(f"End of video stream reached for {self.video_path}")

        self._frame_count += 1
        frame_time = self.base_timestamp + timedelta(seconds=(self._frame_count - 1) / self._fps)
        h, w = frame.shape[:2]

        return CameraFrame(
            frame_id=f"FRAME-{self.camera_id}-{self._frame_count:06d}",
            camera_id=self.camera_id,
            timestamp=frame_time,
            width=w,
            height=h,
            simulated=False,
            data_ref=f"file://{self.video_path}#frame={self._frame_count}",
            image=frame,
            frame_index=self._frame_count,
        )

    def frames(self, step: int = 1) -> Iterator[CameraFrame]:
        """Iterate through frames with optional downsampling step."""
        while self.is_healthy():
            try:
                frame = self.capture()
                if (frame.frame_index - 1) % step == 0:
                    yield frame
            except (EOFError, RuntimeError):
                break

    def is_healthy(self) -> bool:
        """Return True if the video capture is active and ready."""
        return self._is_open and self._cap is not None and self._cap.isOpened()

    def close(self) -> None:
        """Release video capture resources."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._is_open = False

    def __enter__(self) -> FileCameraProvider:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

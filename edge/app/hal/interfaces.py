"""
UrbanSense AI — HAL Provider Interfaces
=========================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

These abstract base classes define the HAL boundary.
Real hardware implementations (camera, GNSS, IMU) must conform to these
interfaces. The Milestone 1 simulation uses SimulatedXxxProvider.

The existence of this HAL boundary means future hardware substitution
does NOT require changing the backend contract or the simulator logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class GNSSReading:
    """Minimum GNSS output required by the UrbanSense pipeline."""
    latitude: float
    longitude: float
    altitude_m: Optional[float]
    accuracy_m: float              # Horizontal accuracy estimate
    heading_deg: Optional[float]   # Vehicle heading
    timestamp: datetime
    fix_quality: int               # 0=invalid, 1=GPS, 2=DGPS, 4=RTK
    speed_mps: Optional[float] = None    # Speed in metres per second from GNSS
    speed_kmh: Optional[float] = None    # Explicit telemetry / CAN / GNSS speed in km/h

    def get_speed_kmh(self) -> Optional[float]:
        """Return speed in km/h if available from speed_kmh or speed_mps."""
        if self.speed_kmh is not None:
            return self.speed_kmh
        if self.speed_mps is not None:
            return round(self.speed_mps * 3.6, 2)
        return None


@dataclass
class IMUReading:
    """Minimum IMU output required by the UrbanSense pipeline."""
    accel_x: float   # m/s² — forward
    accel_y: float   # m/s² — lateral
    accel_z: float   # m/s² — vertical
    gyro_x: float    # rad/s — roll rate
    gyro_y: float    # rad/s — pitch rate
    gyro_z: float    # rad/s — yaw rate
    timestamp: datetime


@dataclass
class CameraFrame:
    """
    Represents a single camera frame reference.
    In Milestone 1, this was a deterministic simulated stub.
    In Milestone 2, it carries image data (e.g., numpy ndarray) when available.
    """
    frame_id: str
    camera_id: str
    timestamp: datetime
    width: int
    height: int
    simulated: bool = True           # True in M1 simulation; False for real/recorded frames
    data_ref: Optional[str] = None   # Buffer/file reference
    image: Optional[object] = None   # Raw frame array (e.g. numpy.ndarray)
    frame_index: int = 0             # Monotonic frame index in stream


class GNSSProvider(ABC):
    """Abstract HAL interface for GNSS sensor."""

    @abstractmethod
    def read(self) -> GNSSReading:
        """Return the current GNSS reading."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the sensor is operational."""
        ...


class IMUProvider(ABC):
    """Abstract HAL interface for IMU sensor."""

    @abstractmethod
    def read(self) -> IMUReading:
        """Return the current IMU reading."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the sensor is operational."""
        ...


class CameraProvider(ABC):
    """Abstract HAL interface for camera module."""

    @abstractmethod
    def capture(self) -> CameraFrame:
        """Capture and return a single frame reference."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the camera is operational."""
        ...

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
    In Milestone 1, this is a deterministic simulated stub.
    Real implementation would carry actual pixel data or a buffer reference.
    """
    frame_id: str
    camera_id: str
    timestamp: datetime
    width: int
    height: int
    simulated: bool = True    # Always True in Milestone 1
    data_ref: Optional[str] = None   # Buffer/file reference (future)


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

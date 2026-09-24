"""
UrbanSense AI — Simulated HAL Providers
=========================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

THESE ARE SIMULATION STUBS — NOT REAL HARDWARE DRIVERS.
All values are deterministic. They do NOT represent real sensor output.

BUS: BUS-001
DEVICE: DEVICE-001
CAMERA: CAMERA-FRONT-01

Simulated route: a small segment of Hyderabad, Telangana road network.
Fixed seed GPS: approximately 17.4435°N, 78.3772°E (HITEC City area).
"""

from __future__ import annotations

from datetime import datetime, timezone
from .interfaces import GNSSProvider, IMUProvider, CameraProvider
from .interfaces import GNSSReading, IMUReading, CameraFrame
import uuid


# ─── Simulated GNSS Provider ──────────────────────────────────────────────────

class SimulatedGNSSProvider(GNSSProvider):
    """
    Deterministic GNSS provider for simulation.
    Returns a fixed GPS position to represent BUS-001 on SEG-001.

    PROTOTYPE / SIMULATED — not real GPS data.
    """

    # Deterministic position: HITEC City road, Hyderabad (SEG-001 seed)
    FIXED_LAT = 17.4435
    FIXED_LON = 78.3772
    FIXED_ALT = 542.0    # metres above sea level (approximate)
    FIXED_ACCURACY = 3.5  # metres
    FIXED_HEADING = 45.0  # degrees (NE direction)
    FIXED_FIX_QUALITY = 1  # Standard GPS

    def read(self) -> GNSSReading:
        return GNSSReading(
            latitude=self.FIXED_LAT,
            longitude=self.FIXED_LON,
            altitude_m=self.FIXED_ALT,
            accuracy_m=self.FIXED_ACCURACY,
            heading_deg=self.FIXED_HEADING,
            timestamp=datetime.now(timezone.utc),
            fix_quality=self.FIXED_FIX_QUALITY,
        )

    def is_healthy(self) -> bool:
        return True


# ─── Simulated IMU Provider ───────────────────────────────────────────────────

class SimulatedIMUProvider(IMUProvider):
    """
    Deterministic IMU provider for simulation.
    Returns flat-road steady-state values for BUS-001.

    PROTOTYPE / SIMULATED — not real IMU data.
    """

    def read(self) -> IMUReading:
        return IMUReading(
            accel_x=0.05,    # m/s² — slight forward acceleration
            accel_y=0.01,    # m/s² — negligible lateral
            accel_z=9.81,    # m/s² — gravity (flat road)
            gyro_x=0.001,    # rad/s — minimal roll
            gyro_y=0.001,    # rad/s — minimal pitch
            gyro_z=0.002,    # rad/s — minimal yaw
            timestamp=datetime.now(timezone.utc),
        )

    def is_healthy(self) -> bool:
        return True


# ─── Simulated Camera Provider ────────────────────────────────────────────────

class SimulatedCameraProvider(CameraProvider):
    """
    Deterministic camera provider for simulation.
    Returns a stub frame reference (no actual pixel data).

    PROTOTYPE / SIMULATED — no real CV inference.
    In future milestones this would return a real frame buffer.
    """

    CAMERA_ID = "CAMERA-FRONT-01"
    FRAME_WIDTH = 1920
    FRAME_HEIGHT = 1080

    def __init__(self) -> None:
        self._seq = 0

    def capture(self) -> CameraFrame:
        self._seq += 1
        frame_id = f"SIM-FRAME-{self._seq:06d}"
        return CameraFrame(
            frame_id=frame_id,
            camera_id=self.CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            width=self.FRAME_WIDTH,
            height=self.FRAME_HEIGHT,
            simulated=True,
            data_ref=None,  # No real pixel data in M1
        )

    def is_healthy(self) -> bool:
        return True

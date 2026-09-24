"""
UrbanSense AI — Camera Calibration Contract
============================================
Defines the camera calibration model.
In Milestone 2, values are explicitly marked PROTOTYPE / ASSUMED.
Do not invent physical geometry claims without field calibration.
"""
from __future__ import annotations

from typing import Optional, Dict
from pydantic import BaseModel, Field, ConfigDict


class CameraIntrinsics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fx: float = Field(description="Focal length x in pixels")
    fy: float = Field(description="Focal length y in pixels")
    cx: float = Field(description="Principal point x in pixels")
    cy: float = Field(description="Principal point y in pixels")
    distortion_coefficients: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0])


class CameraExtrinsics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pitch_deg: float = Field(default=0.0, description="Camera pitch angle relative to vehicle chassis")
    roll_deg: float = Field(default=0.0, description="Camera roll angle")
    yaw_deg: float = Field(default=0.0, description="Camera yaw angle relative to forward axis")
    mounting_height_m: float = Field(default=2.5, description="Mounting height above road surface in metres")
    x_offset_m: float = Field(default=0.0, description="Lateral offset from vehicle centerline")
    y_offset_m: float = Field(default=1.0, description="Longitudinal offset from front axle")


class CameraCalibration(BaseModel):
    """
    Camera calibration specification.
    PROTOTYPE / ASSUMED in Milestone 2.
    """
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    calibration_version: str = "0.1.0-ASSUMED"
    status: str = "PROTOTYPE / ASSUMED"
    image_width: int = 1920
    image_height: int = 1080
    intrinsics: CameraIntrinsics
    extrinsics: CameraExtrinsics
    horizontal_fov_deg: float = Field(default=85.0, description="Horizontal field of view")
    vertical_fov_deg: float = Field(default=54.0, description="Vertical field of view")
    notes: Optional[str] = "Assumed calibration for prototype front-facing transit camera."

"""
UrbanSense AI — Sample Road Video Generator
============================================
Generates a realistic synthetic road test video with:
- Asphalt road surface and horizon
- Lane markings
- Moving vehicles ahead
- Potholes on the road surface
- Realistic road textures

Used for reproducible local testing of the perception and tracking pipelines
without committing large binary video files to Git.
"""
from __future__ import annotations

import os
import cv2
import numpy as np


def generate_sample_road_video(
    output_path: str = "data/sample_road_video.mp4",
    num_frames: int = 60,
    width: int = 1280,
    height: int = 720,
    fps: float = 30.0,
) -> str:
    """
    Generate a synthetic road video file with roadway, moving vehicles, and potholes.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    horizon_y = int(height * 0.40)

    # Fixed pothole positions on the road
    potholes = [
        {"cx": int(width * 0.45), "cy": int(height * 0.75), "rx": 35, "ry": 18},
        {"cx": int(width * 0.65), "cy": int(height * 0.85), "rx": 45, "ry": 22},
    ]

    for frame_idx in range(num_frames):
        # Create base frame
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Sky (upper 40%)
        frame[:horizon_y, :] = (200, 180, 140)  # Light blueish/gray sky

        # Asphalt Road (lower 60%)
        asphalt_color = (65, 65, 70)
        frame[horizon_y:, :] = asphalt_color

        # Road texture noise
        noise = np.random.randint(-8, 8, (height - horizon_y, width, 3), dtype=np.int16)
        road_region = frame[horizon_y:, :].astype(np.int16) + noise
        frame[horizon_y:, :] = np.clip(road_region, 0, 255).astype(np.uint8)

        # Road boundaries / perspective lines
        cv2.line(frame, (int(width * 0.42), horizon_y), (int(width * 0.05), height), (220, 220, 220), 4)
        cv2.line(frame, (int(width * 0.58), horizon_y), (int(width * 0.95), height), (220, 220, 220), 4)

        # Center dashed lane divider
        dash_offset = (frame_idx * 15) % 80
        for y in range(horizon_y + dash_offset, height, 80):
            # Perspective scaling for dash width and length
            factor = (y - horizon_y) / float(height - horizon_y)
            x = int(width * 0.50)
            len_dash = int(30 * factor) + 5
            w_dash = max(2, int(4 * factor))
            cv2.line(frame, (x, y), (x, min(height, y + len_dash)), (0, 220, 255), w_dash)

        # Draw Potholes (darker distressed elliptical regions)
        for p in potholes:
            # Dark distressed core
            cv2.ellipse(
                frame,
                (p["cx"], p["cy"]),
                (p["rx"], p["ry"]),
                angle=10,
                startAngle=0,
                endAngle=360,
                color=(20, 20, 25),
                thickness=-1,
            )
            # Rough edge boundary
            cv2.ellipse(
                frame,
                (p["cx"], p["cy"]),
                (p["rx"] + 4, p["ry"] + 3),
                angle=10,
                startAngle=0,
                endAngle=360,
                color=(40, 40, 45),
                thickness=2,
            )

        # Draw a moving vehicle ahead (car driving in right lane)
        # Vehicle slowly moves forward (grows slightly larger and shifts slightly)
        veh_progress = frame_idx / float(num_frames)
        veh_scale = 1.0 + 0.3 * veh_progress
        vw = int(90 * veh_scale)
        vh = int(60 * veh_scale)
        vx = int(width * 0.58) + int(10 * np.sin(frame_idx * 0.1))
        vy = int(height * 0.48) + int(veh_progress * 40)

        # Vehicle body (metallic blue)
        cv2.rectangle(frame, (vx, vy), (vx + vw, vy + vh), (160, 80, 40), -1)
        # Vehicle roof / cabin
        cabin_w = int(vw * 0.7)
        cabin_h = int(vh * 0.45)
        cabin_x = vx + int((vw - cabin_w) / 2)
        cabin_y = vy - cabin_h
        cv2.rectangle(frame, (cabin_x, cabin_y), (cabin_x + cabin_w, cabin_y + cabin_h), (140, 70, 30), -1)
        # Rear windshield
        cv2.rectangle(frame, (cabin_x + 4, cabin_y + 4), (cabin_x + cabin_w - 4, cabin_y + cabin_h - 2), (50, 40, 30), -1)
        # Tail lights
        cv2.rectangle(frame, (vx + 4, vy + vh - 18), (vx + 18, vy + vh - 6), (0, 0, 220), -1)
        cv2.rectangle(frame, (vx + vw - 18, vy + vh - 18), (vx + vw - 4, vy + vh - 6), (0, 0, 220), -1)

        out.write(frame)

    out.release()
    return output_path


if __name__ == "__main__":
    vid_path = generate_sample_road_video()
    print(f"Sample road video generated: {vid_path}")

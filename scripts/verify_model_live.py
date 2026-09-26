"""
UrbanSense AI — Single-Image Live Model Verification Tool
==========================================================
Usage:
    python scripts/verify_model_live.py --image datasets/India/India/train/images/India_000005.jpg
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
import cv2

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from edge.app.perception.detectors.yolo_detector import YOLORoadDefectDetector
from edge.app.hal.interfaces import CameraFrame

DEFAULT_WEIGHTS = ROOT_DIR / "models" / "weights" / "urbansense_yolo11_rdd_best.pt"
OUTPUT_DIR = ROOT_DIR / "output"


def main():
    parser = argparse.ArgumentParser(description="UrbanSense AI — Live Model Verification")
    parser.add_argument("--image", required=True, help="Path to input road image")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Path to model weights")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--out", default=None, help="Output annotated image path")
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"ERROR: Image not found at {img_path}")
        sys.exit(1)

    weights_path = Path(args.weights)
    if not weights_path.exists():
        print(f"ERROR: Weights not found at {weights_path}")
        sys.exit(1)

    print("=" * 65)
    print("URBANSENSE AI - LIVE INFERENCE VERIFICATION")
    print("=" * 65)
    print(f"Image:     {img_path}")
    print(f"Weights:   {weights_path} ({weights_path.stat().st_size / (1024*1024):.1f} MB)")
    print(f"Threshold: {args.conf:.2f}")

    detector = YOLORoadDefectDetector(
        model_path=weights_path,
        confidence_threshold=args.conf,
        device="cpu",
    )

    img = cv2.imread(str(img_path))
    if img is None:
        print("ERROR: Failed to read image using OpenCV.")
        sys.exit(1)

    h, w = img.shape[:2]
    from datetime import datetime, timezone
    frame = CameraFrame(
        frame_id="verify-01",
        camera_id="CAM-FRONT-01",
        timestamp=datetime.now(timezone.utc),
        width=w,
        height=h,
        image=img,
    )

    t0 = time.perf_counter()
    detections = detector.detect(frame)
    latency_ms = (time.perf_counter() - t0) * 1000

    print("-" * 65)
    print(f"Inference Latency: {latency_ms:.1f} ms  ({1000.0/latency_ms:.1f} FPS)")
    print(f"Detections Found:  {len(detections)}")
    print("-" * 65)

    annotated = img.copy()
    for idx, d in enumerate(detections, 1):
        bbox = d.bbox
        x1, y1 = int(bbox.x_min), int(bbox.y_min)
        x2, y2 = int(bbox.x_max), int(bbox.y_max)
        conf_pct = d.detector_confidence * 100.0
        print(f"  [{idx}] Defect: {d.object_type.upper():<20s} | Confidence: {conf_pct:5.1f}% | BBox: ({x1},{y1}) -> ({x2},{y2})")

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 235), 3)
        label = f"{d.object_type}: {conf_pct:.1f}%"
        cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 235), 2)

    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"prediction_{img_path.name}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), annotated)
    print("-" * 65)
    print(f"Annotated Output Saved: {out_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()

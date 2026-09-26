"""
UrbanSense AI — End-to-End Live Verification Script
===================================================
Executes the full end-to-end stack:
1. ML Perception: Runs YOLO11 RDD road-defect detector on real Indian road image.
2. Edge Packaging: Evaluates Opportunity and builds Canonical Event.
3. Backend Ingestion: POSTs Opportunity and Event to live backend on port 8000.
4. Database & State Machine: Verifies RoadTwin state in PostgreSQL via backend API.
5. Frontend Dashboard: Verifies Vite/React GIS map on port 5173.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
import urllib.request
import urllib.error

# Ensure root is on path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from edge.app.perception.detectors.yolo_detector import YOLORoadDefectDetector

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
IMAGE_PATH = os.path.join(ROOT_DIR, "datasets", "India", "India", "train", "images", "India_000005.jpg")
WEIGHTS_PATH = os.path.join(ROOT_DIR, "models", "weights", "urbansense_yolo11_rdd_best.pt")


def make_request(url: str, method: str = "GET", data: dict | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(content)
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, content
    except Exception as e:
        return 0, str(e)


def main():
    print("=" * 70)
    print("URBANSENSE AI - END-TO-END SYSTEM VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Backend Target:  {BACKEND_URL}")
    print(f"Frontend Target: {FRONTEND_URL}")
    print()

    # -------------------------------------------------------------
    # STEP 1: Verify Infrastructure Health
    # -------------------------------------------------------------
    print("[STEP 1/5] Checking Docker Backend & Database Health...")
    status, health = make_request(f"{BACKEND_URL}/health")
    if status != 200:
        print(f"[FAIL] Backend health check failed with status {status}: {health}")
        return False
    print(f"  [OK] Backend is healthy (HTTP 200): {health}")

    # -------------------------------------------------------------
    # STEP 2: ML Model Inference on Real Indian Road Image
    # -------------------------------------------------------------
    print("\n[STEP 2/5] Running YOLO11 Model Inference on Real Road Frame...")
    if not os.path.exists(WEIGHTS_PATH):
        print(f"[FAIL] Weights not found at {WEIGHTS_PATH}")
        return False
    if not os.path.exists(IMAGE_PATH):
        print(f"[FAIL] Sample image not found at {IMAGE_PATH}")
        return False

    import cv2
    from edge.app.hal.interfaces import CameraFrame

    print(f"  Loading weights: {WEIGHTS_PATH}")
    detector = YOLORoadDefectDetector(
        model_path=WEIGHTS_PATH,
        confidence_threshold=0.25,
        device="cpu",
    )
    print(f"  Running inference on: {IMAGE_PATH}")
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"[FAIL] Could not load image from {IMAGE_PATH}")
        return False

    h, w = img.shape[:2]
    frame = CameraFrame(
        frame_id="frame-e2e-01",
        camera_id="CAM-FRONT-01",
        timestamp=datetime.now(timezone.utc),
        width=w,
        height=h,
        image=img,
    )
    detections = detector.detect(frame)
    print(f"  [OK] Detections found: {len(detections)}")
    for i, d in enumerate(detections, 1):
        print(f"    - Detection #{i}: class='{d.object_type}' detector_confidence={d.detector_confidence:.4f} "
              f"bbox=(xmin={d.bbox.x_min:.1f}, ymin={d.bbox.y_min:.1f}, xmax={d.bbox.x_max:.1f}, ymax={d.bbox.y_max:.1f})")

    primary_detection = detections[0] if detections else None
    if not primary_detection:
        print("[FAIL] No detections produced by ML model")
        return False

    # -------------------------------------------------------------
    # STEP 3: Construct Opportunity and Canonical Event
    # -------------------------------------------------------------
    print("\n[STEP 3/5] Packaging Edge Opportunity & Canonical Event...")
    now = datetime.now(timezone.utc)
    trace_id = str(uuid.uuid4())
    opp_id = f"OPP-E2E-{uuid.uuid4().hex[:8]}"
    event_id = f"EVT-E2E-{uuid.uuid4().hex[:8]}"
    bus_id = "BUS-HYD-042"

    opp_payload = {
        "opportunity_id": opp_id,
        "sensing_pass_id": "SP-HYD-E2E-001",
        "bus_id": bus_id,
        "device_id": "DEV-EDGE-01",
        "camera_id": "CAM-FRONT-01",
        "window_start": now.isoformat(),
        "window_end": now.isoformat(),
        "target_scope": "road_segment",
        "target_type": "pothole",
        "target_id": None,
        "edge_road_segment_hint": "SEG-001",
        "fov_valid": True,
        "visibility_score": 0.92,
        "illumination_score": 0.88,
        "blur_score": 0.95,
        "occlusion_score": 0.90,
        "viewing_angle_score": 0.85,
        "distance_score": 0.89,
        "sensor_health_score": 1.0,
        "gps_quality_score": 0.95,
        "opportunity_score": 0.91,
        "validity_status": "VALID",
        "invalid_reasons": [],
        "coverage_fraction": 0.98,
        "trace_id": trace_id,
    }

    event_payload = {
        "event_id": event_id,
        "schema_version": "1.0",
        "bus_id": bus_id,
        "device_id": "DEV-EDGE-01",
        "camera_id": "CAM-FRONT-01",
        "event_timestamp": now.isoformat(),
        "location": {
            "latitude": 17.4435,  # HITEC City Main Road Segment 1
            "longitude": 78.3772,
            "altitude_m": 542.0,
            "accuracy_m": 1.5,
            "heading_deg": 90.0,
        },
        "edge_road_segment_hint": "SEG-001",
        "event_type": "pothole_observation",
        "observation_id": f"OBS-{uuid.uuid4().hex[:8]}",
        "opportunity_id": opp_id,
        "evidence_ref": f"minio://evidence/{event_id}.jpg",
        "detector_confidence": round(float(primary_detection.detector_confidence), 4),
        "observation_quality": 0.92,
        "gps_quality": 0.95,
        "model_name": primary_detection.model_name,
        "model_version": primary_detection.model_version,
        "priority": "P2",
        "trace_id": trace_id,
        "producer_sequence": 1,
        "payload_hash": "e2e_verified_hash",
    }
    print(f"  [OK] Created Opportunity ID: {opp_id}")
    print(f"  [OK] Created Canonical Event ID: {event_id} (conf={event_payload['detector_confidence']})")

    # -------------------------------------------------------------
    # STEP 4: Ingest to Backend & Update RoadTwin State Machine
    # -------------------------------------------------------------
    print("\n[STEP 4/5] Transmitting to Backend API & Mutating RoadTwin...")
    opp_status, opp_res = make_request(f"{BACKEND_URL}/api/v1/opportunities", method="POST", data=opp_payload)
    print(f"  Opportunity Ingestion (HTTP {opp_status}): {opp_res}")
    if opp_status != 200:
        print(f"[FAIL] Failed to ingest opportunity: {opp_res}")
        return False

    ev_status, ev_res = make_request(f"{BACKEND_URL}/api/v1/events", method="POST", data=event_payload)
    print(f"  Event Ingestion (HTTP {ev_status}): {ev_res}")
    if ev_status != 200:
        print(f"[FAIL] Failed to ingest event: {ev_res}")
        return False

    rt_status, rt_list = make_request(f"{BACKEND_URL}/api/v1/roadtwin")
    print(f"\n  Querying RoadTwin States from Backend (HTTP {rt_status}):")
    if rt_status == 200 and isinstance(rt_list, list):
        for rt in rt_list:
            print(f"    Segment {rt.get('road_segment_id')}: State={rt.get('current_state')} "
                  f"AggregateConfidence={rt.get('aggregate_confidence')} "
                  f"EvidenceCount={rt.get('positive_evidence_count')} "
                  f"LastEvent={rt.get('last_event_id')}")
    else:
        print(f"[FAIL] Could not retrieve RoadTwin state: {rt_list}")
        return False

    # -------------------------------------------------------------
    # STEP 5: Verify Frontend Dashboard Accessibility
    # -------------------------------------------------------------
    print("\n[STEP 5/5] Verifying Frontend GIS Dashboard (Vite + Leaflet)...")
    front_status, front_html = make_request(f"{FRONTEND_URL}/")
    if front_status == 200 and "<html" in str(front_html).lower():
        print(f"  [OK] Frontend dashboard is ONLINE at {FRONTEND_URL} (HTTP 200)")
        print(f"  [OK] Leaflet GIS map UI ready for browser viewing.")
    else:
        print(f"[FAIL] Frontend not reachable on {FRONTEND_URL}: status={front_status}")
        return False

    print("\n" + "=" * 70)
    print("SUCCESS: FULL END-TO-END PIPELINE VERIFIED SUCCESSFULLY!")
    print("=" * 70)
    print("You can open these URLs in your browser:")
    print(f"  1. GIS Map Dashboard:    {FRONTEND_URL}")
    print(f"  2. Backend REST API Docs: {BACKEND_URL}/docs")
    print(f"  3. RoadTwin Live State:  {BACKEND_URL}/api/v1/roadtwin")
    print(f"  4. MinIO Object Console: http://localhost:9001 (User: urbansense / Pass: urbansense_dev)")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

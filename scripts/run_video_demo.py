"""
UrbanSense AI — Milestone 2 Real Video Perception Demo
======================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

Performs:
    Recorded Video File
    -> FileCameraProvider (HAL)
    -> Pothole & Vehicle Detectors (Perception)
    -> Same-Camera Tracking (Tracking)
    -> Observation Quality Evaluation (Quality)
    -> Opportunity Evaluation (Opportunity)
    -> Evidence Artifact Cropping (LocalEvidenceStore)
    -> Canonical Event Assembly (EventBuilder)
    -> POST /api/v1/opportunities (Backend Ingest)
    -> POST /api/v1/events (Backend Ingest)
    -> Backend Map Matching (authoritative match to SEG-001)
    -> RoadTwin State Upsert (OBSERVED state)
    -> GET /api/v1/roadtwin (Frontend Read Model)
    -> Actual measured performance report

USAGE:
    python scripts/run_video_demo.py [--video-path path/to/video.mp4] [--max-frames 15]

PROTOTYPE / EXPERIMENTAL perception baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from edge.app.perception.video_pipeline import VideoPerceptionPipeline
from scripts.generate_sample_road_video import generate_sample_road_video

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def main() -> None:
    parser = argparse.ArgumentParser(description="UrbanSense AI Milestone 2.1 Video Perception Demo")
    parser.add_argument("--video-path", default="data/sample_road_video.mp4", help="Path to video file")
    parser.add_argument("--max-frames", type=int, default=10, help="Number of frames to process")
    parser.add_argument("--frame-step", type=int, default=2, help="Frame downsample step")
    parser.add_argument("--deterministic", action="store_true", default=True, help="Enable deterministic simulation ID mode")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for synthetic video fixture")
    args = parser.parse_args()

    section("UrbanSense AI — Milestone 2.1 Perception Hardening Demo")
    print("NOTE: Using SYNTHETIC TEST VIDEO FIXTURE (deterministic prototype). Not real recorded fleet video.")
    print(f"Backend Target: {BACKEND_URL}")
    print(f"Video Fixture:  {args.video_path}")
    print(f"Frames Target:  {args.max_frames} (sampling step: {args.frame_step}, seed: {args.seed})")
    print(f"Deterministic:  {args.deterministic}")

    # Step 0: Ensure video exists
    if not os.path.exists(args.video_path):
        print("\nVideo fixture not found. Generating deterministic synthetic road video...")
        generate_sample_road_video(output_path=args.video_path, num_frames=60, seed=args.seed)
        print(f"Generated synthetic road video fixture at: {args.video_path}")

    # Step 1: Initialize perception pipeline
    section("STEP 1: Initializing Hardened Video Perception Stack")
    pipeline = VideoPerceptionPipeline(
        bus_id="BUS-001",
        device_id="DEVICE-001",
        camera_id="CAMERA-FRONT-01",
        simulation_mode=True,       # Explicit simulation navigation mode for test fixture
        deterministic=args.deterministic,
        opportunity_window_duration_s=1.0,  # Group frames across 1-second sensing windows
    )
    print("  HAL Camera:      FileCameraProvider")
    print("  Detectors:       BaselinePotholeDetector, BaselineVehicleDetector (heuristic scores)")
    print("  Tracker:         SameCameraTracker (IoU temporal)")
    print("  Quality:         ObservationQualityEvaluator (frame quality vs crop quality separated)")
    print("  Opportunity:     OpportunityEvaluator (1.0s windowed grouping; not 1:1 per-frame)")
    print("  Evidence:        LocalEvidenceStore (prototype local store at data/evidence/)")
    print("  Event Builder:   EventBuilder (SHA-256 payload_hash)")

    # Step 2: Run video perception pipeline
    section("STEP 2: Processing Synthetic Video Stream")
    t_start = time.perf_counter()
    frame_results = pipeline.process_video_file(
        video_path=args.video_path,
        max_frames=args.max_frames,
        frame_step=args.frame_step,
    )
    t_pipeline = time.perf_counter() - t_start

    if not frame_results or len(frame_results) == 0:
        print("ERROR: Pipeline processed 0 frames from video fixture.")
        sys.exit(1)

    print(f"  Processed Frames:     {len(frame_results)}")
    print(f"  Detections Extracted: {pipeline.metrics.detections_found}")
    print(f"  Canonical Events:     {pipeline.metrics.events_generated}")
    print(f"  Detector Failures:    {pipeline.metrics.detector_failures}")
    print(f"  Total Pipeline Time:  {t_pipeline:.3f} s")
    print(f"  Average Throughput:   {pipeline.metrics.average_processed_fps:.2f} FPS")

    # Step 3: Ingest opportunities and events into backend
    section("STEP 3: Ingesting Opportunities & Events into Backend")
    ingested_events = 0
    duplicate_events = 0
    last_roadtwin_id = None
    last_matched_segment = None

    with httpx.Client(timeout=10.0) as client:
        # Check backend health first
        try:
            health_resp = client.get(f"{BACKEND_URL}/health")
            if health_resp.status_code != 200:
                print(f"ERROR: Backend returned status {health_resp.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Cannot connect to backend at {BACKEND_URL}: {e}")
            sys.exit(1)

        # Ingest unique opportunity windows (Correction #2: multiple frames share one Opportunity)
        unique_opportunities = {}
        for fr in frame_results:
            if fr.opportunity.opportunity_id not in unique_opportunities:
                unique_opportunities[fr.opportunity.opportunity_id] = fr.opportunity

        print(f"  Unique Opportunity Windows: {len(unique_opportunities)} (across {len(frame_results)} frames)")
        for opp_id, opp in unique_opportunities.items():
            opp_payload = opp.model_dump(mode="json")
            opp_resp = client.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp_payload)
            if opp_resp.status_code not in (200, 201):
                print(f"ERROR: Opportunity {opp_id} failed with status {opp_resp.status_code}: {opp_resp.text}")
                sys.exit(1)

        # Ingest all generated canonical events
        total_events_to_post = sum(len(fr.events) for fr in frame_results)
        if total_events_to_post == 0:
            print("ERROR: No CanonicalEvents generated from video detections.")
            sys.exit(1)

        for fr in frame_results:
            for ev in fr.events:
                ev_payload = ev.model_dump(mode="json")
                ev_resp = client.post(f"{BACKEND_URL}/api/v1/events", json=ev_payload)
                if ev_resp.status_code not in (200, 201):
                    print(f"ERROR: Event {ev.event_id} failed with status {ev_resp.status_code}: {ev_resp.text}")
                    sys.exit(1)

                data = ev_resp.json()
                if data.get("status") == "accepted":
                    ingested_events += 1
                    # Vehicle events do not mutate RoadTwin, defect events do (Correction #7)
                    if data.get("roadtwin_id"):
                        last_roadtwin_id = data.get("roadtwin_id")
                        last_matched_segment = data.get("matched_road_segment_id")
                elif data.get("status") == "duplicate":
                    duplicate_events += 1

    print(f"  Events Ingested:      {ingested_events}")
    print(f"  Duplicate Events:     {duplicate_events}")
    print(f"  Authoritative Match:  {last_matched_segment}")
    print(f"  Last RoadTwin ID:     {last_roadtwin_id}")

    if ingested_events == 0:
        print("ERROR: No events were accepted by the backend.")
        sys.exit(1)

    # Step 4: Verify RoadTwin state via GET API
    section("STEP 4: Querying RoadTwin State (Frontend Read Model)")
    with httpx.Client(timeout=10.0) as client:
        rt_resp = client.get(f"{BACKEND_URL}/api/v1/roadtwin")
        if rt_resp.status_code != 200:
            print(f"ERROR: GET /api/v1/roadtwin failed with status {rt_resp.status_code}")
            sys.exit(1)
        roadtwins = rt_resp.json()

    print(f"  Active RoadTwins: {len(roadtwins)}")
    if not isinstance(roadtwins, list) or len(roadtwins) == 0:
        print("ERROR: Expected at least one RoadTwin in GET response.")
        sys.exit(1)

    for rt in roadtwins:
        print(f"\n  roadtwin_id:          {rt['roadtwin_id']}")
        print(f"  road_segment_id:      {rt['road_segment_id']} ({rt.get('segment_name')})")
        print(f"  current_state:        {rt['current_state']}")
        print(f"  aggregate_confidence: {rt['aggregate_confidence']:.4f}")
        print(f"  positive_evidence:    {rt['positive_evidence_count']}")
        print(f"  last_event_id:        {rt.get('last_event_id')}")
        print(f"  freshness_status:     {rt['freshness_status']}")

    # Step 5: Display Mathematically Consistent Performance Breakdown
    section("STEP 5: Mathematically Consistent Performance Telemetry")
    m = pipeline.metrics
    n = max(1, m.frames_processed)
    print(f"  Source Video Rate:       30.0 fps")
    print(f"  Frame Sampling Step:     {args.frame_step} (evaluates every {args.frame_step} frames)")
    print(f"  Frames Processed:        {m.frames_processed}")
    print(f"  Total Pipeline Time:     {m.total_time_seconds:.3f} s")
    print(f"  Processed Throughput:    {m.average_processed_fps:.2f} processed frames/sec (FPS)")
    print(f"  Avg End-to-End Time:     {m.avg_end_to_end_ms_per_frame:.2f} ms/frame")
    print("  Detailed Component Timings:")
    print(f"    - Model Inference:     {(m.inference_time_ms / n):.2f} ms/frame")
    print(f"    - Same-Camera Tracking:{(m.tracking_time_ms / n):.2f} ms/frame")
    print(f"    - Frame Optical Qual:  {(m.quality_eval_time_ms / n):.2f} ms/frame")
    print(f"    - Opportunity Window:  {(m.opportunity_eval_time_ms / n):.2f} ms/frame")
    print(f"    - Evidence & Event:    {(m.evidence_and_event_time_ms / n):.2f} ms/frame")
    print(f"    - Overhead / Decoding: {(m.overhead_time_ms / n):.2f} ms/frame")
    print("  Note: Prototype throughput measured on local CPU. Not claimed as real-time production performance.")

    # Step 6: End-to-End Chain Verification
    section("END-TO-END PERCEPTION PROOF COMPLETE")
    sample_fr = frame_results[0]
    sample_ev = sample_fr.events[0] if sample_fr.events else None
    print("""
  RECORDED VIDEO FIXTURE
  -> FRAME ACQUISITION (HAL FileCameraProvider)
  -> OBJECT DETECTION (Baseline Detectors - uncalibrated heuristic scores)
  -> TEMPORAL TRACKING (SameCameraTracker)
  -> OPTICAL QUALITY EVALUATION (Frame-level observability)
  -> OPPORTUNITY WINDOW EVALUATION (1.0s windowed context)
  -> EVIDENCE CROPPING & STORAGE (LocalEvidenceStore)
  -> CANONICAL EVENT CREATION (EventBuilder with SHA-256 payload_hash)
  -> POST /api/v1/opportunities (Backend Ingest)
  -> POST /api/v1/events (Backend Ingest - type-gated routing)
  -> POSTGIS SPATIAL RESOLUTION (Advisory hint -> Authoritative match)
  -> ROADTWIN ENGINE (OBSERVED state for road defects only)
  -> GET /api/v1/roadtwin (Frontend GIS Read API)
""")

    if sample_ev:
        print("  Sample Event Audit Trail:")
        print(f"    event_id:         {sample_ev.event_id}")
        print(f"    observation_id:   {sample_ev.observation_id}")
        print(f"    opportunity_id:   {sample_ev.opportunity_id}")
        print(f"    trace_id:         {sample_ev.trace_id}")
        print(f"    evidence_ref:     {sample_ev.evidence_ref}")
        print(f"    detector_conf:    {sample_ev.detector_confidence} (heuristic score)")
        print(f"    observ_quality:   {sample_ev.observation_quality}")
        print(f"    payload_hash:     {sample_ev.payload_hash}")

    print("\n  MILESTONE 2.1 STATUS: PASS")


if __name__ == "__main__":
    main()

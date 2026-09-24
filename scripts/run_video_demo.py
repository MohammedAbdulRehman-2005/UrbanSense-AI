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

from edge.app.hal.file_camera import FileCameraProvider
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
    parser.add_argument(
        "--deterministic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Deterministic IDs (default). Use --no-deterministic for a fresh sensing pass with fresh IDs.",
    )
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

    # Read the actual source frame rate from the HAL provider (not a hard-coded number)
    with FileCameraProvider(args.video_path, camera_id="CAMERA-FRONT-01") as probe_cam:
        source_fps = probe_cam.fps

    print(f"  Processed Frames:     {len(frame_results)}")
    print(f"  Detections Extracted: {pipeline.metrics.detections_found}")
    print(f"  Canonical Events:     {pipeline.metrics.events_generated}")
    print(f"  Detector Failures:    {pipeline.metrics.detector_failures}")
    print(f"  Total Pipeline Time:  {t_pipeline:.3f} s")
    print(f"  Average Throughput:   {pipeline.metrics.average_processed_fps:.2f} processed FPS")

    # Step 3: Ingest opportunities and events into backend
    section("STEP 3: Ingesting Opportunities & Events into Backend")
    ingested_events = 0
    duplicate_events = 0
    run_defect_roadtwin_ids: set = set()
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
            try:
                opp_resp = client.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp_payload)
            except Exception as e:
                print(f"ERROR: Opportunity {opp_id} POST raised a transport failure: {e}")
                sys.exit(1)
            if opp_resp.status_code not in (200, 201):
                print(f"ERROR: Opportunity {opp_id} failed with status {opp_resp.status_code}: {opp_resp.text}")
                sys.exit(1)
            try:
                opp_data = opp_resp.json()
            except Exception as e:
                print(f"ERROR: Opportunity {opp_id} returned an invalid (non-JSON) response: {e}")
                sys.exit(1)

        # Ingest all generated canonical events
        total_events_to_post = sum(len(fr.events) for fr in frame_results)
        if total_events_to_post == 0:
            print("ERROR: No CanonicalEvents generated from video detections.")
            sys.exit(1)

        for fr in frame_results:
            for ev in fr.events:
                ev_payload = ev.model_dump(mode="json")
                try:
                    ev_resp = client.post(f"{BACKEND_URL}/api/v1/events", json=ev_payload)
                except Exception as e:
                    print(f"ERROR: Event {ev.event_id} POST raised a transport failure: {e}")
                    sys.exit(1)
                if ev_resp.status_code not in (200, 201):
                    print(f"ERROR: Event {ev.event_id} failed with status {ev_resp.status_code}: {ev_resp.text}")
                    sys.exit(1)
                try:
                    data = ev_resp.json()
                except Exception as e:
                    print(f"ERROR: Event {ev.event_id} returned an invalid (non-JSON) response: {e}")
                    sys.exit(1)

                if data.get("status") == "accepted":
                    ingested_events += 1
                    # Vehicle events do not mutate RoadTwin, defect events do (Correction #7)
                    if data.get("roadtwin_id"):
                        run_defect_roadtwin_ids.add(data.get("roadtwin_id"))
                        last_matched_segment = data.get("matched_road_segment_id")
                elif data.get("status") == "duplicate":
                    duplicate_events += 1
                    # Duplicate responses still carry the original authoritative
                    # match (backend idempotency response contract) — needed so a
                    # full idempotent re-run can still verify the read model.
                    if data.get("matched_road_segment_id"):
                        last_matched_segment = data.get("matched_road_segment_id")
                else:
                    print(f"ERROR: Event {ev.event_id} returned unexpected status: {data.get('status')}")
                    sys.exit(1)

    print(f"  Events Ingested:      {ingested_events}")
    print(f"  Duplicate Events:     {duplicate_events}")
    print(f"  Authoritative Match:  {last_matched_segment}")
    print(f"  Defect RoadTwin IDs mutated by this run: {sorted(run_defect_roadtwin_ids) if run_defect_roadtwin_ids else 'none (idempotent re-run)'}")

    if ingested_events == 0 and duplicate_events == 0:
        print("ERROR: No events were accepted or recognised as duplicates by the backend.")
        sys.exit(1)

    # A PASS claim requires this run to have either produced/mutated a defect RoadTwin
    # (fresh run) or hit idempotent duplicates of this exact deterministic event set
    # (re-run of the same sensing pass — R4 §14.3 retry semantics).
    if not run_defect_roadtwin_ids and duplicate_events == 0:
        print("ERROR: No defect RoadTwin was created or updated by this run's events.")
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

    # Verify the run's evidence is reflected in the read model:
    # - fresh run: a RoadTwin mutated by this run's accepted defect events, or
    # - idempotent re-run: a RoadTwin on the authoritatively matched segment.
    visible_run_rts = [
        rt for rt in roadtwins
        if (rt.get("roadtwin_id") in run_defect_roadtwin_ids)
        or (duplicate_events > 0 and rt.get("road_segment_id") == last_matched_segment)
    ]
    if not visible_run_rts:
        print("ERROR: RoadTwin evidence from this run was not found in the GET /api/v1/roadtwin read model.")
        sys.exit(1)

    for rt in visible_run_rts:
        print(f"\n  roadtwin_id:          {rt['roadtwin_id']}")
        print(f"  road_segment_id:      {rt['road_segment_id']} ({rt.get('segment_name')})")
        print(f"  current_state:        {rt['current_state']}")
        print(f"  aggregate_confidence: {rt['aggregate_confidence']:.4f}")
        print(f"  positive_evidence:    {rt['positive_evidence_count']}")
        print(f"  last_event_id:        {rt.get('last_event_id')}")
        print(f"  freshness_status:     {rt['freshness_status']}")

    # Step 5: Performance Report (measured, honest scope)
    section("STEP 5: Measured Performance Telemetry")
    m = pipeline.metrics
    n = max(1, m.frames_processed)
    sum_components_ms = (
        m.acquisition_time_ms +
        m.quality_eval_time_ms +
        m.opportunity_eval_time_ms +
        m.inference_time_ms +
        m.tracking_time_ms +
        m.evidence_and_event_time_ms
    )
    residual_fraction = (m.overhead_time_ms / (m.total_time_seconds * 1000.0)) if m.total_time_seconds > 0 else 1.0
    print(f"  Source Video Rate:       {source_fps:.2f} fps (from video file)")
    print(f"  Frame Sampling Step:     {args.frame_step} (evaluates every {args.frame_step} frames)")
    print(f"  Frames Processed:        {m.frames_processed}")
    print(f"  Total Pipeline Time:     {m.total_time_seconds:.3f} s (measured wall-clock)")
    print(f"  Processed Throughput:    {m.average_processed_fps:.2f} processed frames/sec (distinct from source rate)")
    print(f"  Avg End-to-End Time:     {m.avg_end_to_end_ms_per_frame:.2f} ms/frame")
    print("  Measured Component Timings (wall-clock, prototype laptop/CPU):")
    print(f"    - Frame Acquisition:   {(m.acquisition_time_ms / n):.2f} ms/frame (video decode)")
    print(f"    - Model Inference:     {(m.inference_time_ms / n):.2f} ms/frame")
    print(f"    - Same-Camera Tracking:{(m.tracking_time_ms / n):.2f} ms/frame")
    print(f"    - Frame Optical Qual:  {(m.quality_eval_time_ms / n):.2f} ms/frame")
    print(f"    - Opportunity Window:  {(m.opportunity_eval_time_ms / n):.2f} ms/frame")
    print(f"    - Evidence & Event:    {(m.evidence_and_event_time_ms / n):.2f} ms/frame")
    print(f"    - Residual Overhead:    {(m.overhead_time_ms / n):.2f} ms/frame "
          f"({residual_fraction * 100:.1f}% of total; loop overhead by construction)")
    print(f"  Component Sum:          {sum_components_ms:.1f} ms + residual {m.overhead_time_ms:.1f} ms "
          f"= {sum_components_ms + m.overhead_time_ms:.1f} ms (total measured: {m.total_time_seconds * 1000.0:.1f} ms)")
    print("  Note: Prototype throughput measured on local CPU. NOT real-time, embedded, or production performance.")

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

    print("\n  M2.1 DEMO RUN: PASS")
    if run_defect_roadtwin_ids:
        print("  Run type: FRESH ingestion — defect RoadTwin created/updated by this run.")
    else:
        print("  Run type: IDEMPOTENT RE-RUN — this deterministic sensing pass was already")
        print("            ingested; backend correctly returned duplicates (R4 §14.3 retry semantics).")
    print(f"  Verified in THIS run against the live backend at {BACKEND_URL}:")
    print("    health check, opportunity ingestion, event ingestion,")
    print("    RoadTwin evidence verified through the read model.")
    print("  Scope: SYNTHETIC test video fixture with heuristic baseline detectors.")
    print("  NOT real recorded fleet video; NOT a validated detector benchmark.")


if __name__ == "__main__":
    main()

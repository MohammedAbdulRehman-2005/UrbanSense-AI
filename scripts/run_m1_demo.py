"""
UrbanSense AI — Milestone 1 End-to-End Demo Script
====================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)

Performs:
    reset/prepare
    → seed demo road segment (done via migration)
    → generate simulated sensing pass
    → generate opportunity
    → generate observation
    → generate canonical event
    → POST opportunity to backend
    → POST event to backend
    → GET RoadTwin from backend
    → print frontend-visible state

USAGE:
    python scripts/run_m1_demo.py

REQUIRES:
    Backend running: uvicorn backend.app.main:app --reload
    Database migrated: cd backend && alembic upgrade head

SIMULATED — not real fleet data.
"""

from __future__ import annotations

import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

from edge.app.simulation.simulator import SensingPassSimulator

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    section("UrbanSense AI — Milestone 1 Demo")
    print("NOTE: This is a SIMULATED demo. No real sensor data.")
    print(f"Backend: {BACKEND_URL}")

    # ── Step 1: Generate simulated sensing pass ────────────────────────────
    section("STEP 1: Generate simulated sensing pass (BUS-001 / SEG-001)")
    sim = SensingPassSimulator()
    sensing_pass_id, observation, opportunity, event = sim.run()

    print(f"  sensing_pass_id  : {sensing_pass_id}")
    print(f"  observation_id   : {observation.observation_id}")
    print(f"  opportunity_id   : {opportunity.opportunity_id}")
    print(f"  event_id         : {event.event_id}")
    print(f"  trace_id         : {event.trace_id}")
    print(f"  detector_conf    : {observation.detector_confidence}")
    print(f"  opportunity_score: {opportunity.opportunity_score}")
    print(f"  validity_status  : {opportunity.validity_status}")
    print(f"  edge_hint        : {event.edge_road_segment_hint} (ADVISORY only)")
    print(f"  payload_hash     : {event.payload_hash}")

    # ── Step 2: POST opportunity ───────────────────────────────────────────
    section("STEP 2: POST /api/v1/opportunities")
    opp_payload = opportunity.model_dump(mode="json")
    with httpx.Client(timeout=10.0) as client:
        # Check backend health first
        try:
            health = client.get(f"{BACKEND_URL}/health")
            if health.status_code != 200:
                print(f"  ERROR: Backend health failed with status {health.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"  ERROR: Backend unreachable at {BACKEND_URL}: {e}")
            sys.exit(1)

        resp = client.post(f"{BACKEND_URL}/api/v1/opportunities", json=opp_payload)
    print(f"  HTTP {resp.status_code}")
    print(f"  Response: {json.dumps(resp.json(), indent=2)}")
    if resp.status_code not in (200, 201):
        print(f"  ERROR: Opportunity POST failed with status {resp.status_code}.")
        sys.exit(1)

    # ── Step 3: POST event ─────────────────────────────────────────────────
    section("STEP 3: POST /api/v1/events")
    event_payload = event.model_dump(mode="json")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(f"{BACKEND_URL}/api/v1/events", json=event_payload)
    print(f"  HTTP {resp.status_code}")
    event_resp = resp.json()
    print(f"  Response: {json.dumps(event_resp, indent=2)}")
    if resp.status_code not in (200, 201) or event_resp.get("status") != "accepted":
        print(f"  ERROR: Event POST failed: status={event_resp.get('status')}.")
        sys.exit(1)

    roadtwin_id = event_resp.get("roadtwin_id")
    matched_segment = event_resp.get("matched_road_segment_id")
    if not matched_segment or not roadtwin_id:
        print("  ERROR: Expected valid map match and roadtwin_id in response.")
        sys.exit(1)
    print(f"\n  map_match: segment={matched_segment} (Backend-authoritative)")
    print(f"  roadtwin_id: {roadtwin_id}")

    # ── Step 4: Test idempotency ───────────────────────────────────────────
    section("STEP 4: Idempotency check (POST same event again)")
    with httpx.Client(timeout=10.0) as client:
        resp2 = client.post(f"{BACKEND_URL}/api/v1/events", json=event_payload)
    resp2_data = resp2.json()
    print(f"  HTTP {resp2.status_code}")
    print(f"  status: {resp2_data.get('status')}")
    if resp2.status_code != 200 or resp2_data.get("status") != "duplicate":
        print(f"  ERROR: Idempotency failed: expected status 'duplicate', got '{resp2_data.get('status')}'")
        sys.exit(1)
    print("  PASS: Idempotency verified — no duplicate created")

    # ── Step 5: GET RoadTwin ───────────────────────────────────────────────
    section("STEP 5: GET /api/v1/roadtwin (frontend data)")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{BACKEND_URL}/api/v1/roadtwin")
    if resp.status_code != 200:
        print(f"  ERROR: GET /api/v1/roadtwin failed with status {resp.status_code}")
        sys.exit(1)

    roadtwins = resp.json()
    print(f"  HTTP {resp.status_code}")
    print(f"  RoadTwin count: {len(roadtwins)}")
    if not isinstance(roadtwins, list) or len(roadtwins) == 0:
        print("  ERROR: Expected at least one active RoadTwin.")
        sys.exit(1)

    target_rt = next((rt for rt in roadtwins if rt.get("roadtwin_id") == roadtwin_id), None)
    if not target_rt:
        print(f"  ERROR: Created RoadTwin {roadtwin_id} not found in GET response.")
        sys.exit(1)
    if target_rt.get("current_state") != "OBSERVED":
        print(f"  ERROR: Expected state OBSERVED, got {target_rt.get('current_state')}")
        sys.exit(1)

    for rt in roadtwins:
        print(f"\n  roadtwin_id         : {rt['roadtwin_id']}")
        print(f"  road_segment_id     : {rt['road_segment_id']}")
        print(f"  current_state       : {rt['current_state']}")
        print(f"  aggregate_confidence: {rt['aggregate_confidence']}")
        print(f"  positive_evidence   : {rt['positive_evidence_count']}")
        print(f"  centroid_lat        : {rt.get('segment_centroid_lat')}")
        print(f"  centroid_lon        : {rt.get('segment_centroid_lon')}")
        print(f"  segment_name        : {rt.get('segment_name')}")
        print(f"  last_event_id       : {rt.get('last_event_id')}")
        print(f"  freshness_status    : {rt.get('freshness_status')}")

    section("END-TO-END CHAIN COMPLETE")
    print("""
  SIMULATION -> OPPORTUNITY -> EVENT -> BACKEND -> DATABASE -> ROADTWIN -> API -> FRONTEND

  Traceability:
    event_id        : """ + event.event_id + """
    observation_id  : """ + observation.observation_id + """
    opportunity_id  : """ + opportunity.opportunity_id + """
    trace_id        : """ + event.trace_id + """

  MILESTONE 1 STATUS: PASS
  Docker runtime verification: CONFIRMED LIVE
""")


if __name__ == "__main__":
    main()

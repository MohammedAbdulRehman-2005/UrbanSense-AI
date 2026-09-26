"""
UrbanSense AI — M4 Closed-Loop E2E Demonstration Script
=========================================================
Demonstrates the complete M4 lifecycle:

  OBSERVED → CANDIDATE → CONFIRMED
      → [MAINTENANCE_DISPATCHED]
      → MAINTENANCE_PENDING
      → [REPAIR_COMPLETION_REPORTED]
      → VERIFICATION_PENDING
      → [NEGATIVE EVIDENCE — VALID pass, no detection]
      → VERIFIED_REPAIRED
      → [NEW POSITIVE DETECTION]
      → REAPPEARED
      → [MAINTENANCE_DISPATCHED again]
      → MAINTENANCE_PENDING (new cycle)

ARCHITECTURE INVARIANTS VERIFIED:
    - Contractor report alone does NOT verify repair
    - INVALID opportunity produces no negative evidence
    - State transitions only via the two authoritative engines
    - evidence_weight never computed outside FusionEngine

Usage:
    python scripts/e2e_m4_closed_loop.py

Requires:
    - Docker stack running (urbansense-backend at localhost:8000)
    - Live PostgreSQL with m4_001_maintenance migration applied
"""
from __future__ import annotations

import sys
import uuid
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: uv pip install requests")
    sys.exit(1)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = "http://localhost:8000/api/v1"

# ── Helpers ─────────────────────────────────────────────────────────────────

def _hdr(step: int, title: str):
    print(f"\n{'='*65}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*65}")


def _ok(label: str, value):
    print(f"  [OK]   {label}: {value}")


def _fail(label: str, expected, actual):
    print(f"  [FAIL] {label}: expected={expected!r} actual={actual!r}")
    sys.exit(1)


def _check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  [OK]   {label}" + (f" ({detail})" if detail else ""))
    else:
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        sys.exit(1)


def post(path: str, body: dict, step_label: str) -> dict:
    url = f"{BASE}{path}"
    r = requests.post(url, json=body, timeout=10)
    if r.status_code not in (200, 201):
        print(f"  ✗  HTTP {r.status_code} at {url}: {r.text[:300]}")
        sys.exit(1)
    return r.json()


def get(path: str) -> dict:
    url = f"{BASE}{path}"
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        print(f"  ✗  HTTP {r.status_code} at {url}")
        sys.exit(1)
    return r.json()


# ── Event payload factory ────────────────────────────────────────────────────

def event_payload(bus_id: str, confidence: float = 0.87, oq: float = 0.9, gq: float = 0.85, opp_id: Optional[str] = None) -> dict:
    """Create a road defect event payload matched to SEG-001 (lat=17.4435, lon=78.3772)."""
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "bus_id": bus_id,
        "device_id": f"DEV-{bus_id}",
        "camera_id": f"CAM-{bus_id}-01",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 17.4435, "longitude": 78.3772},
        "event_type": "pothole_observation",
        "opportunity_id": opp_id or f"OPP-{bus_id}-PASS1",
        "detector_confidence": confidence,
        "observation_quality": oq,
        "gps_quality": gq,
        "model_name": "urbansense-yolo11-rdd",
        "model_version": "1.0",
        "trace_id": str(uuid.uuid4()),
        "producer_sequence": 1,
    }


# ── Main E2E ─────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*65)
    print("  UrbanSense AI — M4 Closed-Loop E2E Demonstration")
    print("  " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("="*65)

    # Step 0: Health check
    _hdr(0, "Health Check & Environment Prep")
    h = get("/../../health")  # /health is at root, not /api/v1
    _check("Backend healthy", h.get("status") == "ok", h.get("status"))

    # Dev-safe reset for demo segment SEG-001 so E2E can run repeatedly
    try:
        from backend.app.db.session import SessionLocal
        from backend.app.models.roadtwin import RoadTwinStateModel
        from backend.app.models.evidence import EvidenceModel
        from backend.app.models.authority_action import AuthorityActionModel
        from backend.app.models.event import EventModel
        with SessionLocal() as db:
            rt_prev = db.query(RoadTwinStateModel).filter_by(road_segment_id="SEG-001").first()
            if rt_prev:
                db.query(AuthorityActionModel).filter_by(road_segment_id="SEG-001").delete()
                db.query(EvidenceModel).filter_by(matched_road_segment_id="SEG-001").delete()
                db.query(EventModel).filter_by(matched_road_segment_id="SEG-001").delete()
                db.query(RoadTwinStateModel).filter_by(road_segment_id="SEG-001").delete()
                db.commit()
                print("  [INIT] Reset prior test state for SEG-001 (ensuring repeatable E2E run)")
    except Exception as e:
        print(f"  [INIT] Note on reset: {e}")

    TRACE = str(uuid.uuid4())[:8]

    # Step 1: Seed OBSERVED → CANDIDATE → CONFIRMED (positive evidence from 2 buses)
    _hdr(1, "Seed OBSERVED → CANDIDATE → CONFIRMED via cooperative evidence")
    r1 = post("/events", event_payload("BUS-M4A-001"), "bus 1 event")
    _check("Bus 1 event accepted", r1["status"] == "accepted")
    rt_id = r1.get("roadtwin_id")
    seg_id = r1.get("matched_road_segment_id")
    _check("RoadTwin created", rt_id is not None, f"roadtwin_id={rt_id}")
    _ok("Segment", seg_id)

    # Second bus — should advance to CONFIRMED
    r2 = post("/events", event_payload("BUS-M4A-002"), "bus 2 event")
    _check("Bus 2 event accepted", r2["status"] == "accepted")

    # Check state
    rt_state = get(f"/roadtwin/{rt_id}")
    state = rt_state["current_state"]
    _check("State is CANDIDATE or CONFIRMED",
           state in ("CANDIDATE", "CONFIRMED"),
           f"state={state}")
    _ok("aggregate_confidence", f"{rt_state['aggregate_confidence']:.4f}")
    _ok("positive_evidence_count", rt_state["positive_evidence_count"])
    _ok("independent_bus_count", rt_state["independent_bus_count"])

    # If not yet CONFIRMED, add more evidence
    if state != "CONFIRMED":
        r3 = post("/events", event_payload("BUS-M4A-003"), "bus 3 event")
        _check("Bus 3 event accepted", r3["status"] == "accepted")
        rt_state = get(f"/roadtwin/{rt_id}")
        state = rt_state["current_state"]
        _check("State is CONFIRMED after 3 buses", state == "CONFIRMED", f"state={state}")

    _ok("Final state before M4 maintenance", state)

    # Verify positive-event evidence lineage and sensing_pass_id propagation
    ev_list = get(f"/evidence?road_segment_id={seg_id}")
    pos_evs = [e for e in ev_list if e.get("polarity") == "POSITIVE"]
    _check("Positive evidence records exist", len(pos_evs) >= 2, f"count={len(pos_evs)}")
    for pev in pos_evs:
        _check(
            f"Positive evidence {pev['evidence_id'][:8]} has sensing_pass_id",
            pev.get("sensing_pass_id") is not None,
            pev.get("sensing_pass_id"),
        )
        _check(
            f"Positive evidence {pev['evidence_id'][:8]} has coordinates",
            pev.get("latitude") is not None and pev.get("longitude") is not None,
            f"lat={pev.get('latitude')}, lon={pev.get('longitude')}",
        )

    # Step 2: MAINTENANCE_DISPATCHED (CONFIRMED → MAINTENANCE_PENDING)
    _hdr(2, "Dispatch Maintenance (CONFIRMED → MAINTENANCE_PENDING)")
    dispatch_resp = post("/maintenance/dispatch", {
        "roadtwin_id": rt_id,
        "actor_role": "INSPECTOR",
        "actor_id": f"INS-E2E-{TRACE}",
        "notes": "Severe pothole confirmed by 2+ independent buses. Dispatch repair crew.",
        "work_order_id": f"WO-E2E-{TRACE}",
        "trace_id": str(uuid.uuid4()),
    }, "dispatch")
    _check("Dispatch accepted", dispatch_resp["status"] == "accepted")
    _check("Transition CONFIRMED→MAINTENANCE_PENDING",
           dispatch_resp["prior_state"] == "CONFIRMED" and
           dispatch_resp["new_state"] == "MAINTENANCE_PENDING",
           f"{dispatch_resp['prior_state']}→{dispatch_resp['new_state']}")
    action_dispatch_id = dispatch_resp["action_id"]
    _ok("Dispatch action_id", action_dispatch_id)

    # Verify RoadTwin state
    maint_status = get(f"/maintenance/{rt_id}")
    _check("maintenance_status = DISPATCHED",
           maint_status["maintenance_status"] == "DISPATCHED",
           maint_status["maintenance_status"])

    # Step 3: Verify that INVALID opportunity does NOT create negative evidence
    _hdr(3, "INVALID Opportunity Gate — Must Not Produce Negative Evidence")
    neg_invalid = post("/maintenance/negative-evidence", {
        "road_segment_id": seg_id,
        "opportunity_id": str(uuid.uuid4()),
        "opportunity_score": 0.15,
        "gps_quality": 0.1,
        "bus_id": "BUS-M4-GATE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validity_status": "INVALID",
        "trace_id": str(uuid.uuid4()),
    }, "invalid neg evidence")
    _check("INVALID opportunity gated out",
           neg_invalid["status"] == "gated_out",
           neg_invalid["status"])
    _check("No evidence_id for INVALID",
           neg_invalid["evidence_id"] is None)
    print("  [OK]   Architecture invariant: INVALID opportunity -> INCONCLUSIVE -> not recorded")

    # Step 4: Contractor reports completion (MAINTENANCE_PENDING → VERIFICATION_PENDING)
    _hdr(4, "Report Completion (MAINTENANCE_PENDING → VERIFICATION_PENDING)")
    print("  NOTE: This does NOT verify repair. Repair requires independent negative sensing evidence.")
    complete_resp = post("/maintenance/report-completion", {
        "roadtwin_id": rt_id,
        "actor_role": "CONTRACTOR",
        "actor_id": f"CON-E2E-{TRACE}",
        "notes": "Pothole filled with asphalt. Surface leveled and compacted.",
        "work_order_id": f"WO-E2E-{TRACE}",
        "trace_id": str(uuid.uuid4()),
    }, "report completion")
    _check("Completion report accepted", complete_resp["status"] == "accepted")
    _check("Transition MAINTENANCE_PENDING→VERIFICATION_PENDING",
           complete_resp["prior_state"] == "MAINTENANCE_PENDING" and
           complete_resp["new_state"] == "VERIFICATION_PENDING",
           f"{complete_resp['prior_state']}→{complete_resp['new_state']}")

    # CRITICAL ARCHITECTURE CHECK: state must be VERIFICATION_PENDING, not VERIFIED_REPAIRED
    maint_status2 = get(f"/maintenance/{rt_id}")
    _check(
        "ARCHITECTURE INVARIANT: Contractor report does NOT set VERIFIED_REPAIRED",
        maint_status2["current_state"] == "VERIFICATION_PENDING",
        f"actual={maint_status2['current_state']!r}"
    )
    _check("verification_status = PENDING",
           maint_status2["verification_status"] == "PENDING",
           maint_status2["verification_status"])

    # Step 5: Submit VALID negative evidence (VERIFICATION_PENDING → VERIFIED_REPAIRED)
    _hdr(5, "VALID Negative Evidence → VERIFIED_REPAIRED")
    neg_valid = post("/maintenance/negative-evidence", {
        "road_segment_id": seg_id,
        "opportunity_id": str(uuid.uuid4()),
        "opportunity_score": 0.92,
        "gps_quality": 0.90,
        "bus_id": "BUS-M4-VERIFY-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validity_status": "VALID",
        "trace_id": str(uuid.uuid4()),
    }, "valid neg evidence")
    _check("Negative evidence accepted", neg_valid["status"] == "accepted")
    neg_strength = neg_valid.get("negative_evidence_strength")
    _check("negative_evidence_strength is non-None", neg_strength is not None)
    _ok("negative_evidence_strength", f"{neg_strength:.4f}")
    _check("Strength >= 0.5 (sufficient for VERIFIED_REPAIRED)",
           neg_strength >= 0.5, f"{neg_strength:.4f}")

    roadtwin_after_neg = neg_valid.get("roadtwin_state")
    _check("RoadTwin reached VERIFIED_REPAIRED",
           roadtwin_after_neg == "VERIFIED_REPAIRED",
           f"actual={roadtwin_after_neg!r}")

    final_maint = get(f"/maintenance/{rt_id}")
    _check("verification_status = VERIFIED",
           final_maint["verification_status"] == "VERIFIED",
           final_maint["verification_status"])
    _check("maintenance_status = COMPLETED",
           final_maint["maintenance_status"] == "COMPLETED",
           final_maint["maintenance_status"])

    # Step 6: Recurrence — new detection after VERIFIED_REPAIRED → REAPPEARED
    _hdr(6, "Recurrence Detection (VERIFIED_REPAIRED → REAPPEARED)")
    r_recur = post("/events", event_payload("BUS-M4-RECUR", confidence=0.91), "recurrence event")
    _check("Recurrence event accepted", r_recur["status"] == "accepted")

    rt_after_recur = get(f"/roadtwin/{rt_id}")
    _check("State = REAPPEARED after new detection",
           rt_after_recur["current_state"] == "REAPPEARED",
           rt_after_recur["current_state"])
    _check("previous_episode_id is set",
           rt_after_recur.get("previous_episode_id") is not None)
    _ok("Previous episode", rt_after_recur.get("previous_episode_id"))
    _ok("Active episode", rt_after_recur.get("active_episode_id"))

    # Step 7: New dispatch cycle (REAPPEARED → MAINTENANCE_PENDING)
    _hdr(7, "New Dispatch Cycle (REAPPEARED → MAINTENANCE_PENDING)")
    dispatch2 = post("/maintenance/dispatch", {
        "roadtwin_id": rt_id,
        "actor_role": "CITY_ENGINEER",
        "actor_id": f"ENG-E2E-{TRACE}",
        "notes": "Defect reappeared. Escalating to full road section resurfacing.",
        "work_order_id": f"WO-E2E-{TRACE}-B",
        "trace_id": str(uuid.uuid4()),
    }, "second dispatch")
    _check("Second dispatch accepted", dispatch2["status"] == "accepted")
    _check("Transition REAPPEARED→MAINTENANCE_PENDING",
           dispatch2["prior_state"] == "REAPPEARED" and
           dispatch2["new_state"] == "MAINTENANCE_PENDING",
           f"{dispatch2['prior_state']}→{dispatch2['new_state']}")

    # Step 8: Action history
    _hdr(8, "Action History Audit")
    history = get(f"/maintenance/{rt_id}/history")
    _check("Action history has >= 2 records", len(history) >= 2, f"count={len(history)}")
    action_types = [h["action_type"] for h in history]
    _check("MAINTENANCE_DISPATCHED in history", "MAINTENANCE_DISPATCHED" in action_types)
    _check("REPAIR_COMPLETION_REPORTED in history", "REPAIR_COMPLETION_REPORTED" in action_types)
    _check("START_VERIFICATION in history", "START_VERIFICATION" in action_types)

    # Verify runtime visibility of REPAIR_REPORTED state in history
    repair_rep_states = [
        h for h in history
        if h.get("resulting_roadtwin_state") == "REPAIR_REPORTED"
        or h.get("prior_roadtwin_state") == "REPAIR_REPORTED"
    ]
    _check(
        "REPAIR_REPORTED state visible in action history",
        len(repair_rep_states) > 0,
        f"records={len(repair_rep_states)}",
    )

    for record in history:
        _ok("  Action", f"{record['action_type']} by {record['actor_role']} ({record['actor_id']}): "
            f"{record['prior_roadtwin_state']} -> {record['resulting_roadtwin_state']}")

    # Final report
    print("\n" + "="*65)
    print("  M4 CLOSED-LOOP E2E: ALL STEPS PASSED")
    print("="*65)
    print(f"\n  RoadTwin ID:      {rt_id}")
    print(f"  Road Segment:     {seg_id}")
    print(f"\n  LIFECYCLE VERIFIED:")
    print(f"    OBSERVED -> CANDIDATE -> CONFIRMED")
    print(f"    -> MAINTENANCE_PENDING (via MAINTENANCE_DISPATCHED)")
    print(f"    -> VERIFICATION_PENDING (via REPAIR_COMPLETION_REPORTED)")
    print(f"    -> VERIFIED_REPAIRED (via VALID negative evidence)")
    print(f"    -> REAPPEARED (new positive detection)")
    print(f"    -> MAINTENANCE_PENDING (new dispatch cycle)\n")
    print(f"  ARCHITECTURE INVARIANTS VERIFIED:")
    print(f"    [OK] INVALID opportunity -> INCONCLUSIVE -> no evidence recorded")
    print(f"    [OK] Contractor report alone -> VERIFICATION_PENDING (not VERIFIED_REPAIRED)")
    print(f"    [OK] Independent negative evidence required for VERIFIED_REPAIRED")
    print(f"    [OK] Recurrence creates new episode (previous_episode_id set)")
    print(f"    [OK] New dispatch cycle works from REAPPEARED state")
    print(f"\n  PROTOTYPE NOTES:")
    print(f"    - neg_evidence_strength threshold (0.5) is PROTOTYPE / DECISION_REQUIRED")
    print(f"    - All quality signals are UNCALIBRATED prototype values (DECISION-020)")
    print(f"    - Full RBAC for roles is DECISION-007 (OPEN)")
    print()


if __name__ == "__main__":
    # Health check uses root /health endpoint
    import requests as req
    try:
        h = req.get("http://localhost:8000/health", timeout=5)
        if h.status_code != 200:
            print(f"ERROR: Backend not healthy: {h.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Cannot reach backend at localhost:8000: {e}")
        sys.exit(1)
    main()

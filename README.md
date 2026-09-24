# UrbanSense AI

**Turning Public Transport Buses into a Continuous Urban Intelligence Network**

[![Smart India Hackathon 2026](https://img.shields.io/badge/SIH-2026-orange)](#)
[![Problem Statement](https://img.shields.io/badge/PS%20ID-26124-blue)](#)
[![Theme](https://img.shields.io/badge/Theme-Smart%20Automation-green)](#)
[![Category](https://img.shields.io/badge/Category-Software-informational)](#)
[![Team](https://img.shields.io/badge/Team-Coding%20Wizards%20(135094)-purple)](#)
[![Status](https://img.shields.io/badge/Status-Prototype%20%2F%20MVP-yellow)](#)

> Every bus journey becomes an observation opportunity. UrbanSense determines **what can be trusted**, **what remains uncertain**, and **which bus should observe next.**

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Our Solution](#our-solution)
- [What Makes UrbanSense Different](#what-makes-urbansense-different)
- [System Architecture](#system-architecture)
- [Requirement Coverage (R01–R29)](#requirement-coverage-r01r29)
- [Evidence Fusion & the 8-State RoadTwin](#evidence-fusion--the-8-state-roadtwin)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [MVP vs. Full Problem Statement](#mvp-vs-full-problem-statement)
- [Feasibility, Risks & Architectural Responses](#feasibility-risks--architectural-responses)
- [Datasets & References](#datasets--references)
- [Impact & Stakeholders](#impact--stakeholders)
- [Roadmap](#roadmap)
- [Team](#team)
- [License](#license)

---

## Problem Statement

**SIH Problem Statement ID:** 26124
**Title:** AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet
**Theme:** Smart Automation · **Category:** Software

Urban roads suffer from potholes, damaged infrastructure, waterlogging, traffic congestion, accidents, hit-and-run incidents, rash driving, and risks to vulnerable pedestrians. Authorities largely depend on fixed CCTV, manual inspections, and citizen complaints — all of which are slow, incomplete, and reactive. Meanwhile, city buses already carry cameras that traverse nearly every road daily but remain almost entirely underused as sensing infrastructure.

**Core problem:** Cities lack an intelligent system that turns continuously moving buses into real-time, reliable road, traffic, and safety intelligence for timely action and prevention.

## Our Solution

UrbanSense AI equips existing public bus fleets with an edge-AI sensing layer (cameras + GPS/GNSS + IMU) that continuously observes road and traffic conditions. Instead of streaming raw video, each bus converts observations into lightweight, GPS-tagged, quality- and confidence-scored **evidence**. A backend backend fuses evidence from multiple buses over time to build and maintain a persistent **RoadTwin** — a living, per-road-segment digital state that tracks each issue through its full lifecycle, from first detection to independently verified repair.

The system addresses **29 authoritative Problem Statement requirements** spanning perception, infrastructure intelligence, traffic analytics, safety/incidents, mobility analytics, alerting, GIS, and authority workflows.

### End-to-End Example: A Pothole's Life in UrbanSense

1. Bus A detects a pothole → Edge creates an **Observation**.
2. Quality is evaluated → Event sent to backend.
3. Road segment identified → RoadTwin = `Observed`.
4. Validation passes → RoadTwin = `Candidate`.
5. Bus B independently detects the same defect → Fusion Engine aggregates independent evidence.
6. Confidence threshold met → RoadTwin = `Confirmed`.
7. Maintenance workflow triggered → priority scored → `Maintenance Pending`.
8. Authority reports the repair via the dashboard → `Repair Reported`.
9. Verification triggered → fleet actively re-observes the segment → `Verification Pending`.
10. Multiple healthy buses pass with no pothole detected → **Negative Evidence** accumulates.
11. Threshold met → `Verified Repaired`.
12. Months later, a new detection at the same site → `Reappeared` (a new evidence chain is created, full history retained).

## What Makes UrbanSense Different

UrbanSense is explicit that **existing technologies are not being claimed as novel** (YOLO, OCR, GPS, PostGIS, MQTT, ONNX are established tools). The engineering and research contribution lies in the architecture around them:

| # | Principle | Description |
|---|-----------|-------------|
| 01 | **Observation-Aware Evidence** | Trust a detection only when the road was actually observable — poor-quality passes remain `Inconclusive`, never a false negative. |
| 02 | **Evidence-Driven Fleet Fusion** | Combine observations from multiple buses using quality, confidence, time, and spatial-temporal consistency. |
| 03 | **Evidence Debt → Next-Best Bus** | When evidence is insufficient, the system identifies the next valuable bus observation to reduce uncertainty, instead of blind repeated sensing. |
| 04 | **Lifecycle-Aware RoadTwin** | Every road issue is tracked through Detect → Confirm → Repair → Verify → Reappear. |
| 05 | **Closed-Loop Verification** | Subsequent fleet observations independently verify repairs and detect recurring defects. |

**Detection → Trusted Evidence → Action → Verification.**

## System Architecture

```
EDGE (On-Board, per bus)
  1. Mobile Sensing      — Camera + GPS/GNSS + IMU on existing buses
  2. Edge AI             — Perception + Tracking + OCR (YOLO, segmentation, MOT, ANPR)
  3. Observation → Event — AI outputs become evidence-rich candidate events
                           (location, timestamp, confidence, quality, evidence crop)
        │  MQTT / HTTPS (priority-routed, store-and-forward on connectivity loss)
        ▼
backend INTELLIGENCE (Cloud / Server)
  4. Multi-Bus Evidence Fusion — spatial + temporal + semantic match,
                                  source reliability + quality + confidence,
                                  historical consistency → Trusted Urban Event
  5. Persistent Urban State    — Live GIS map, 8-state RoadTwin, historical trends
        │
        ▼
ACTION & FEEDBACK
  6. Prioritization       — severity × impact × exposure × confidence
  7. Decision Support     — grounded, actionable outputs; human decision → work order
  8. Verify & Monitor     — repair → re-observe → verify → reopen if recurs (closed loop)
```

**Edge pipeline:** `Camera/GPS/IMU → HAL → Inference → Object Tracking → Quality/Uncertainty Evaluation → Canonical Event Generation → MQTT Transport`

**backend pipeline:** `Secure Ingestion → Deduplication → Spatial Map Matching → Evidence Fusion Engine → 8-State RoadTwin (PostGIS) → Analytics → GIS / Copilot`

**Prototype vs. Deployment:** The SIH prototype runs on a laptop with recorded video and simulated GNSS/IMU, using the *same* Edge Agent and Event API planned for a future deployment on RTSP/MIPI cameras with real GNSS/IMU on edge-AI hardware (e.g., Jetson).

## Requirement Coverage (R01–R29)

The system implements exactly 29 authoritative Problem Statement requirements, grouped into four capability areas:

<details>
<summary><strong>Group 1 — Road & Infrastructure Intelligence (R01–R08)</strong></summary>

| ID | Requirement | Module | Edge/backend |
|----|-------------|--------|---------------|
| R01 | Pothole detection | Road Defect AI | Edge → backend |
| R02 | Damaged road detection | Road Defect AI | Edge → backend |
| R03 | Missing road dividers | Infrastructure AI | Edge → backend |
| R04 | Missing zebra crossings | Infrastructure AI | Edge → backend |
| R05 | Damaged traffic signs | Infrastructure AI | Edge → backend |
| R06 | Missing traffic signs | Infrastructure AI | Edge → backend |
| R07 | Waterlogging detection | Road Defect AI | Edge → backend |
| R08 | Other road hazards | Road Defect AI | Edge → backend |

Detects road/infrastructure defects via YOLO detection + segmentation; missing-infrastructure checks compare a GIS Expected-Asset DB against observed reality, gated by Negative Evidence rules.
</details>

<details>
<summary><strong>Group 2 — Traffic & Fleet Mobility OD Proxy (R09–R15)</strong></summary>

| ID | Requirement | Module | Edge/backend |
|----|-------------|--------|---------------|
| R09 | Vehicle detection | Vehicle AI | Edge |
| R10 | Vehicle classification | Vehicle AI | Edge |
| R11 | Vehicle counting | Vehicle AI | Edge → backend |
| R12 | Traffic density estimation | Traffic AI | backend |
| R13 | Bottleneck detection | Traffic AI | backend |
| R14 | Route delay estimation | Traffic AI | backend |
| R15 | Fleet Mobility OD Proxy | OD Analytics | backend |

- **R12 (Density):** vehicle counts per segment ÷ segment length over a time window.
- **R13 (Bottleneck):** flags a segment when density exceeds a high threshold **and** average fleet speed drops below a low threshold across a rolling 3-window period.
- **R14 (Route Delay):** compares observed segment traversal time against a scheduled/historical baseline.
- **R15 (OD Proxy):** map-matches bus trajectories to route segments/zones, identifies origin→destination zone transitions, and aggregates them by time window, normalized by coverage.

> ⚠️ **Important scope note:** UrbanSense does **not** infer individual passenger trips or a true passenger OD matrix — passenger-level OD data is explicitly out of scope. What is implemented is a **Fleet Mobility OD Proxy**, estimating traffic flow using only bus trajectory and route progression. This disclaimer is intentionally kept visible in the UI.
</details>

<details>
<summary><strong>Group 3 — Safety, Incidents & ANPR (R16–R22)</strong></summary>

| ID | Requirement | Module | Edge/backend |
|----|-------------|--------|---------------|
| R16 | Vulnerable pedestrian risk | VRU AI | Edge |
| R17 | School child crossing risk | VRU AI | Edge |
| R18 | Rash driving detection | Incident AI | Edge |
| R19 | Hit-and-run detection | Incident AI | Edge |
| R20 | Offending vehicle tracking | Tracking AI | Edge |
| R21 | ANPR plate extraction | ANPR/OCR | Edge |
| R22 | ANPR metadata (score/GPS) | Event Engine | Edge → backend |

- **R20 (Tracking):** multi-object tracking (Kalman filter / IoU) assigns a persistent ID across frames, surviving occlusion.
- **R16 (VRU Risk):** compares pedestrian and vehicle trajectory vectors; a Time-To-Collision (TTC) below threshold raises an alert.
- **R17 (School Zone):** inside a GIS school geofence, the VRU risk score is multiplied by 1.5 and the TTC threshold is lowered.
- **R18 (Rash Driving):** triggered by IMU lateral/longitudinal acceleration above threshold, or erratic lane-change tracking.
- **R19 (Hit-and-Run):** a kinematic collision signature (sudden deceleration + impact) followed by the offending vehicle leaving frame.
- **R21–R22 (ANPR):** triggered only on incident — crop → OCR, with three separately maintained confidences (vehicle detection, plate localization, OCR confidence).
</details>

<details>
<summary><strong>Group 4 — Platform, GIS, Authority & Edge Efficiency (R23–R29)</strong></summary>

| ID | Requirement | Module | Edge/backend |
|----|-------------|--------|---------------|
| R23 | Secure alerting | Transport/Alerting | Edge → backend |
| R24 | backend fleet aggregation | Evidence Fusion | backend |
| R25 | GIS visualization | GIS | backend |
| R26 | Congestion heat maps | GIS + Traffic AI | backend |
| R27 | Infra deficiency analysis | Maintenance AI | backend |
| R28 | Authority insights/workflows | Copilot/Workflows | backend |
| R29 | Edge bandwidth minimization | HAL/Transport | Edge |

- **R23:** RBAC-secured routing with automatic retry and audit logging, based on P0–P3 event priority.
- **R27:** compares observed asset evidence against the GIS Expected Asset DB; a Negative Evidence gate raises `deficiency_score` when an expected asset is missing across a minimum number of independent passes.
- **R28:** NLP intent parsing → deterministic SQL tool call → grounded Copilot explanation (no free-form hallucinated answers).
- **R29:** event classification separates P0 (instant cellular) from P3 (buffered batch sync); small evidence crops are transmitted instead of continuous raw video.
</details>

## Evidence Fusion & the 8-State RoadTwin

### Evidence Model

```
Sensor Health (Camera Status, GPS Accuracy)
        → Observation Quality (Visibility, Blur)
        → Evidence Weight
        → RoadTwin Confidence
```

### Evidence Fusion Algorithm (MVP)

1. **Spatial Association** — map-match coordinates to `road_segment_id`; match entities by segment, geographic distance, time window, and object class.
2. **Evidence Weight** (deterministic, isolates AI confidence from physical reality):
   ```
   evidence_weight = detector_confidence × observation_quality × gps_quality
   ```
3. **Independence** — duplicate frames from the same bus pass are rejected; unique bus counts and temporal separation are required.
4. **Aggregate Evidence** (probabilistic OR across independent observations):
   ```
   aggregate_confidence = 1 − Π(1 − evidence_weight_i)
   ```
5. **Lifecycle Decision** — state transitions are evaluated against configurable thresholds.

```python
def on_observation(event):
    validate(event)
    segment = map_match(event.location)
    entity = associate(event, segment)
    if not entity.exists():
        entity = create_entity(event)

    weight = calculate_evidence_weight(event)
    if is_independent(event, entity):
        add_positive_evidence(entity, event, weight)
        update_aggregate_confidence(entity)
        evaluate_lifecycle_transition(entity)

    persist(entity)
```

### Negative Evidence

A **missing** detection is only informative if all physical conditions would have allowed a detection to occur:

```
NegativeEvidence = Coverage × Visibility × SensorHealth × DetectionReliability
```

Gate logic (any "No" discards the pass):
1. Did the bus pass the expected road location?
2. Was the location inside the camera field of view?
3. Was visibility adequate?
4. Was occlusion acceptable?
5. Was the sensor healthy?
6. If all pass and no defect is detected → add Negative Evidence.

### The 8-State RoadTwin Lifecycle

```
Observed → Candidate → Confirmed → Maintenance Pending → Repair Reported
   → Verification Pending → Verified Repaired → Reappeared ⤳ (Candidate / Confirmed)
```

| Transition | Trigger | Action |
|---|---|---|
| Observed → Candidate | Initial detection passes validation and quality > threshold | — |
| Candidate → Confirmed | `unique_bus_count ≥ 2` **and** `aggregate_confidence ≥ threshold` | Enter maintenance queue |
| Confirmed → Maintenance Pending | Authority priority scoring | — |
| Maintenance Pending → Repair Reported | Manual authority input via UI | Flag for verification |
| Repair Reported → Verification Pending | Automatic | Fleet prioritizes negative-evidence collection |
| Verification Pending → Verified Repaired | Cumulative Negative Evidence meets thresholds (below) | Close record |
| Verified Repaired → Reappeared | New high-quality positive evidence at the exact site | Retain history, return to active defect state |

**Repair verification thresholds:**
- `min_independent_passes ≥ 3`
- `min_coverage_per_pass ≥ 80%`
- `sensor_health == OK`
- `negative_evidence_score ≥ 0.85`
- `new_positive_evidence == 0` over a 72-hour window

## Tech Stack

| Layer | Technologies |
|---|---|
| **Edge Sensing & AI** | Cameras + OpenCV, YOLO + Segmentation, Multi-object Tracking, OCR/ANPR, GPS/GNSS + IMU, PyTorch → ONNX/TensorRT |
| **Edge Evidence & Communication** | Event Engine, Quality + Confidence Engine, Evidence Manager, Priority Manager (P0–P4), Local Queue (store-and-forward), MQTT / HTTPS |
| **backend Intelligence** | FastAPI, PostgreSQL + PostGIS, Fusion Engine, RoadTwin Engine, Analytics Engine, Maintenance + Alert Engine |
| **GIS, Authority & GenAI** | React + TypeScript, MapLibre / Leaflet, LLM + RAG / tool retrieval (Copilot), RBAC + Authentication, Docker |

**Hardware Abstraction Layer (HAL):** abstracts Camera, GNSS, and Inference so the same Edge Agent runs unmodified on a dev laptop (SIH prototype) or on Jetson-class edge hardware (future deployment). Sensor health (camera availability, frame rate, GPS accuracy) is tracked continuously and directly suppresses false Negative Evidence from unhealthy nodes.

## Project Structure

> Illustrative layout reflecting the architecture above — adjust to match the actual repository.

```
urbansense-ai/
├── edge/
│   ├── hal/                # Camera / GNSS / Inference abstraction (laptop ↔ Jetson)
│   ├── perception/         # YOLO, segmentation, MOT, ANPR/OCR
│   ├── evidence/           # Event Engine, Quality/Confidence Engine, Evidence Manager
│   ├── transport/          # Priority Manager, local queue, MQTT/HTTPS client
│   └── edge_agent.py
├── backend/
│   ├── api/                # FastAPI routes (events, roadtwin, traffic, incidents, gis, copilot)
│   ├── fusion/              # Spatial association, evidence weighting, lifecycle engine
│   ├── analytics/           # Traffic density, bottleneck, route delay, OD proxy
│   ├── maintenance/         # Prioritization, alerting, workflow routing
│   ├── copilot/             # NLP intent parsing → SQL tool calls
│   └── db/                  # PostgreSQL/PostGIS models & migrations
├── frontend/           # React + TypeScript + MapLibre/Leaflet frontend
├── datasets/                # IDD, BDD100K, RDD2022 pointers + custom capture
├── tests/                   # Acceptance tests (AT-01 … AT-29)
├── docker-compose.yml
└── README.md
```

## Getting Started

> The SIH prototype is designed to run entirely on a laptop using recorded video and simulated GNSS/IMU, sharing the same Edge Agent and Event API as the future live deployment.

### Prerequisites

- Docker & Docker Compose
- Python 3.10+
- Node.js 18+ (for the GIS dashboard)
- PostgreSQL with PostGIS extension

### Setup

```bash
# Clone the repository
git clone https://github.com/<org>/urbansense-ai.git
cd urbansense-ai

# Start core services (PostgreSQL/PostGIS, FastAPI backend, MQTT broker)
docker-compose up -d

# Install and run the edge agent (recorded-video / simulated GNSS mode)
cd edge
pip install -r requirements.txt
python edge_agent.py --source recorded --video ./samples/demo_route.mp4 --simulate-gnss

# Install and run the GIS dashboard
cd ../frontend
npm install
npm run dev
```

## API Reference

| Endpoint | Method | Purpose / Payload |
|---|---|---|
| `/events` | `POST` | Ingest a standardized evidence event |
| `/roadtwin/{id}` | `GET` | Retrieve the current 8-state RoadTwin status |
| `/road-defects` | `GET` | Query defects for GIS and dashboards |
| `/traffic` | `GET` | Traffic density and route-delay analytics |
| `/od-proxy` | `GET` | Fleet Mobility OD Proxy matrix data |
| `/incidents` | `GET` | Incident evidence and ANPR (RBAC restricted) |
| `/maintenance/{id}/repair` | `POST` | Authority triggers `Repair Reported` state |
| `/gis/layers` | `GET` | Fetch GeoJSON layer data for visualization |
| `/alerts` | `GET` | Authority P0/P1 alerts |
| `/copilot/query` | `POST` | Natural-language query → deterministic SQL tool call |

**Core data entities:** `EVENT`, `ROAD_DEFECT`, `INFRA_ASSET`, `TRAFFIC_OBS`, `INCIDENT`, `PLATE`, `ROADTWIN_STATE`, `MAINTENANCE` (see the full ER structure in the technical specification).

## MVP vs. Full Problem Statement

| Capability | MVP | Full PS |
|---|---|---|
| Road Defects | Core YOLO detector | Complete defect classes & persistence filters |
| Infrastructure | Missing-sign vertical slice | Complete expected-asset reasoning |
| Traffic | Vehicle counting | Density + bottleneck + route delay |
| Mobility OD | Fleet OD Proxy | Expanded fleet mobility analytics |
| VRU / Risk | Core risk detection | Full trajectory-based risk analytics |
| Incidents | Simulated kinematic incident | Full incident rolling-buffer workflow |
| ANPR | Incident-triggered OCR | Complete multi-frame ANPR workflow |
| RoadTwin | Core 8-state lifecycle | Full lifecycle analytics & recurrence history |
| GIS | Core spatial layers | Complete 20-layer GIS map set |
| Maintenance | Basic prioritization | Full configurable authority workflow |
| Copilot | Deterministic SQL queries | Full authority NLP assistant |
| Edge | Laptop / HAL abstraction | Jetson deployment & dynamic scheduling |

**Incremental deployment path:** Prototype → Pilot Routes → Fleet → City → Multi-City.

## Feasibility, Risks & Architectural Responses

| # | Risk | Architectural Response |
|---|------|--------------------------|
| 01 — Observation Reliability | Visibility, blur & occlusion can make detections unreliable | Quality + observability scoring → Observation-Qualification Gate → poor passes remain `Inconclusive`, not false negatives |
| 02 — Location Reliability | GNSS drift or temporary signal loss can misplace events | GNSS + IMU + heading + map matching → location confidence + multi-pass consistency |
| 03 — Evidence Integrity | Observations can be false, duplicated, or insufficient | Spatial-temporal fusion + multi-bus corroboration → explicit `Insufficient Evidence` state → Next-Best Bus |
| 04 — Communication Resilience | Connectivity issues can disrupt evidence delivery | Edge filtering + priority routing → durable local queue → retry/backoff + depot synchronization |
| 05 — Data Security | ANPR and incident evidence require controlled access | RBAC + TLS-secured HTTPS + MQTT → role-scoped access + evidence provenance |

**Design properties:** retrofit-friendly · bandwidth-aware · modular · human-in-the-loop.

## Datasets & References

**Datasets & benchmarks**

| Module / Requirement | Primary Data Source | Type |
|---|---|---|
| Indian vehicles & road scenes | IDD (India Driving Dataset) | Public |
| Vehicle detection & tracking | IDD + BDD100K (MOT) | Public |
| Pedestrian detection | IDD + BDD100K | Public |
| Road segmentation | IDD | Public |
| Potholes & road damage | Road Damage Dataset (RDD2022) + custom capture | Hybrid |
| Traffic signs | Public sign dataset + custom India data | Hybrid |
| Waterlogging & ANPR | Public plate/image data + custom footage | Hybrid |
| Fleet GPS, incidents & GIS | Own recorded GPS, video & route/event logs | Custom |

**Research foundations**
- BusEdge — Edge Video Analytics for Transit Buses (Canbo Ye, CMU, 2021)
- Road Condition Monitoring via Bus Trajectories (Multimodal Transportation, 2022)
- Reliability-Aware Crowdsensing for Pothole Profiling (Zhong et al., ACM IMWUT, 2020)
- Truth Discovery in Crowdsourced Spatial Events (Ouyang, IEEE TKDE)
- Edge Intelligence + Digital Twin for Pothole Detection (IEEE IoT, 2025)
- RDD2022 — Multi-National Road Damage Dataset

**Related existing systems:** iRASTE (IIIT-H, Intel & Nagpur Municipal Corp.), VIOLA (IIIT-H / INAI), Netradyne Driver-i, City ITMS/ANPR networks, RoadBotics. UrbanSense's differentiation is **persistent defect lifecycle (RoadTwin)** and **evidence fusion with negative-evidence-based repair verification**, capabilities largely absent from these systems.

**Established vs. engineering vs. research contribution**
- *Established technology (not claimed as novel):* YOLO detection, OCR, GPS, PostGIS, MQTT, ONNX.
- *Engineering contribution:* bus-fleet sensing architecture, HAL portability, canonical event integration, 20-layer GIS visualization, Copilot authority workflows.
- *Research contribution:* lifecycle-aware evidence fusion, negative-evidence mathematics for repair verification, coverage-aware confidence, reappearance tracking.

## Impact & Stakeholders

| Stakeholder | Key Benefit | Impact |
|---|---|---|
| Bus Operators | Early detection of severe hazards/waterlogging; bandwidth-optimized priority-aware communication | Smarter fleet operations |
| Urban Authorities | Automatic issue ranking (severity × traffic impact × exposure × confidence); grounded GenAI Copilot | Evidence-driven action |
| Road/Maintenance Depts. | Full RoadTwin lifecycle tracking; flags unresolved/recurring defects | Closed-loop maintenance |
| Traffic / Police | Cross-bus ANPR/OCR correlation; compact, traceable evidence packages | Corroborated incident evidence |
| Citizens & Commuters | Earlier hazard/VRU-risk awareness; congestion and route-delay intelligence | Safer, more predictable travel |

**Secondary environmental benefits:** less unnecessary data transmission, fewer dedicated inspection journeys, data-informed traffic management.

## Roadmap

- [x] Problem identification & requirement analysis
- [x] Study of existing systems (iRASTE, VIOLA, Netradyne, ITMS/ANPR, RoadBotics)
- [x] Solution & architecture design (edge pipeline, fusion engine, 8-state RoadTwin)
- [ ] Prototype development (laptop + recorded video + simulated GNSS/IMU)
- [ ] Validation against AT-01–AT-29 acceptance tests
- [ ] Pilot deployment on selected bus routes with real GNSS/IMU + edge hardware
- [ ] Fleet-wide rollout → city-wide → multi-city expansion

## Team

**Team Name:** Coding Wizards
**Team ID:** 135094
**Event:** Smart India Hackathon 2026
**Problem Statement:** 26124 — AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet

## License

*Add your chosen license here (e.g., MIT, Apache 2.0) prior to publishing this repository.*

---

<p align="center"><em>UrbanSense AI — From reactive monitoring to continuous urban intelligence.</em></p>

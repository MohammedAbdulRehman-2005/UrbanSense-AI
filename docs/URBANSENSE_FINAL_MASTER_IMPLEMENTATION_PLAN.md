# UrbanSense AI — Final Master Implementation & AI Coding-Assistant Plan

**Project:** UrbanSense AI  
**SIH Problem Statement:** 26124 — AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet  
**Team:** Coding Wizards  
**Execution model:** 2 members  
**Document status:** FINAL IMPLEMENTATION BASELINE (R4)  
**Purpose:** single source of truth for implementation, integration, testing, demo, and coding-assistant work.

---

# 0. Finalization Rules

This document replaces all earlier planning drafts for implementation decisions. Earlier documents may be retained for history, but coding work must follow this R4 plan.

The source basis is:

1. UrbanSense v3.1 Team Master Specification.
2. Detailed Technical Reference — Read When Working on Your Module.
3. Existing UrbanSense design material and repository constraints.
4. The R3 Revision Audit and its 31 contradiction fixes.

The R3 audit identified and patched architecture ambiguities involving opportunity units, map-matching ownership, target references, quality-signal ownership, evidence semantics, transport envelopes, RoadTwin identity, lifecycle episodes, RBAC timing, evaluation ground truth, independence, freshness, event-time processing, map-match status, database relationships, append-only history, API/read-model boundaries, cross-references, requirement naming, verification thresholds, negative-evidence gates, endpoint structure, schedule/tier conflicts, delayed opportunities, and subject attachment. Those fixes are incorporated below as final implementation rules.

Where the source material itself uses `[PROPOSED]`, `OPEN DECISION`, or `DECISION_REQUIRED`, this plan preserves that status rather than inventing a value.

## 0.1 Status vocabulary

Use exactly these implementation-status labels:

- **IMPLEMENTED** — implemented and tested in the repository.
- **SIMULATED** — implemented using simulated inputs or demo-scale data.
- **PROPOSED** — architecture or rule defined for implementation, but not empirically validated.
- **PLANNED** — implementation intentionally scheduled later.
- **FUTURE** — intentionally outside the current SIH build.
- **RESEARCH** — experimental track requiring evaluation.
- **SOURCE-VERIFIED** — directly supported by an UrbanSense source already supplied to the team.
- **SOURCE-CLAIMED** — present in a source but still needs final traceability confirmation before public claims.
- **DECISION_REQUIRED** — must be decided and recorded before the dependent implementation is frozen.

## 0.2 Final rule for unresolved decisions

A coding assistant must never silently convert `DECISION_REQUIRED` into a guessed constant.

The correct sequence is:

```text
DECISION_REQUIRED
      ↓
Decision logged in docs/decision-log.md
      ↓
Architecture/contract updated
      ↓
Tests updated
      ↓
Implementation uses the recorded decision
```

---

# 1. Mission

UrbanSense is an end-to-end urban evidence and decision-support system, not a YOLO demo and not a frontend dashboard.

```text
Camera / GNSS / IMU
        ↓
HAL
        ↓
AI Perception
        ↓
Tracking
        ↓
Observation Quality / Sensor Health
        ↓
Observation Opportunity
        ↓
Canonical Event
        ↓
MQTT / HTTPS
        ↓
Backend
        ↓
Validation / Idempotency / Deduplication / Map Matching
        ↓
Evidence Feature Construction
        ↓
Evidence Fusion
        ↓
RoadTwin / Urban Memory
        ↓
Traffic / Infrastructure / Safety / Incident / Maintenance Analytics
        ↓
GIS / Authority UI / Copilot
        ↓
Authority Action
        ↓
Re-observation
        ↓
Repair Verification
        ↓
Reappearance
```

## 1.1 Core principles

> AI observations are evidence, not automatically truth.

> A non-detection only means something when there was a valid opportunity to detect.

> Repeated frames from one bus pass are not independent corroboration.

> Backend state is derived from evidence; detector confidence is not itself RoadTwin truth.

> Historical lineage must remain inspectable after every state transition.

---

# 2. System Layers

UrbanSense uses four clean architectural layers.

## Layer 1 — Sensor Layer

```text
Front Camera
Rear Camera
Side Cameras
Cabin Camera
GNSS
IMU
```

## Layer 2 — Edge Intelligence Layer

```text
HAL
Calibration
Frame ingestion
Perception
Tracking
Quality
Sensor health
Observation Opportunity
Event construction
Transport
```

## Layer 3 — Backend Intelligence Layer

```text
Secure ingestion
Validation
Idempotency
Deduplication
Map matching
Evidence
Fusion
Negative evidence
RoadTwin
Urban Memory
Traffic
Infrastructure
Maintenance
Alerts
Analytics
```

## Layer 4 — Application Layer

```text
React + TypeScript
GIS
Dashboards
Authority actions
Copilot
RAG
Reports
```

The laptop prototype must use the same interfaces that a future physical edge device would use. Hardware changes must be absorbed by HAL/providers rather than forcing a redesign of the Backend contracts.

---

# 3. Non-Negotiable Engineering Rules

1. Canonical Event is the Edge → Backend domain contract.
2. API/OpenAPI is the Backend → Frontend/Copilot contract.
3. Shared contracts contain data shapes, not business logic.
4. Frontend never queries PostgreSQL directly.
5. Frontend never implements RoadTwin transitions.
6. No hard-coded final demo state.
7. No fake analytics in the final demo.
8. No raw credentials, raw videos, raw datasets, or model weights in Git.
9. No unsupported accuracy, latency, bandwidth, cost, deployment, or novelty claims.
10. One non-detection is not automatically Negative Evidence.
11. Repeated frames from one sensing pass are not independent evidence.
12. Prefer deterministic logic over unnecessary LLM calls.
13. Baseline first; research second.
14. A module is not complete until tests and integration pass.
15. Only the FusionEngine calculates `evidence_weight`.
16. Observation Opportunity can exist with zero Observations.
17. Negative Evidence requires a `VALID` Observation Opportunity.
18. Exactly one FusionEngine exists in `backend/app/fusion/engine.py`.
19. Exactly one RoadTwin state machine exists in `backend/app/roadtwin/`.
20. Exactly one Negative Evidence implementation exists in `backend/app/fusion/negative_evidence/`.
21. Exactly one Opportunity evaluator exists in `edge/app/opportunity/`.
22. Backend map matching is authoritative; Edge hints are advisory.
23. A bare `confidence` field is forbidden. Use semantic confidence/quality names.
24. No coding assistant may invent a lifecycle threshold, physical speed/TTC assumption, or deployment vendor choice.
25. Historical domain records and audit records are append-only; current state is a projection/snapshot.
26. State transitions must be explainable through trigger + evidence + transition reason + history.
27. Event-time semantics take precedence over network arrival order for historical processing.
28. No API response may imply `pothole=true`, `road=repaired`, or another world-state fact unless that state has been produced by the authoritative Backend lifecycle.
29. Every public claim must have either measured evidence or an explicit prototype/simulation qualifier.
30. Every research claim must have an experiment and baseline.

---

# 4. Semantic Model — Five Distinct Layers

UrbanSense must never conflate these objects.

```text
AI Observation
    = detector belief about what a frame/track contains

Observation Opportunity
    = evidence that the system had a valid chance to observe a target

Evidence
    = value assigned to a positive or negative observation after quality,
      opportunity, independence, and correlation handling

RoadTwin / defect subject
    = current system assertion about the physical urban state

Urban Memory / history
    = persistent historical record of how that assertion evolved
```

## 4.1 Naming rules

Use:

```text
detector_confidence
observation_quality
opportunity_score
gps_quality
evidence_weight
aggregate_confidence
ocr_confidence
plate_localization_confidence
map_match_confidence
```

Do not introduce:

```text
confidence
truth_confidence
road_confidence
final_confidence
```

unless a semantic definition is added and approved in the decision log.

---

# 5. Repository Standard

```text
D:/UrbanSense AI
│
├── contracts/                    # shared schemas/data shapes only
│   ├── observation.py
│   ├── opportunity.py
│   ├── canonical_event.py
│   ├── evidence.py
│   └── roadtwin_state.py
│
├── edge/
│   └── app/
│       ├── hal/
│       ├── calibration/
│       ├── perception/
│       ├── tracking/
│       ├── quality/
│       ├── opportunity/
│       │   ├── opportunity_evaluator.py
│       │   ├── visibility.py
│       │   ├── fov.py
│       │   └── validity.py
│       ├── events/
│       └── transport/
│
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── db/
│       ├── models/
│       ├── schemas/
│       ├── services/
│       ├── mapmatching/
│       ├── fusion/
│       │   ├── engine.py
│       │   ├── feature_builder.py
│       │   ├── strategies/
│       │   │   ├── base.py
│       │   │   ├── mvp.py
│       │   │   └── research.py
│       │   ├── independence/
│       │   │   ├── duplicate.py
│       │   │   ├── correlated.py
│       │   │   └── independent.py
│       │   └── negative_evidence/
│       │       ├── eligibility.py
│       │       └── scoring.py
│       ├── roadtwin/
│       ├── maintenance/
│       └── analytics/
│
├── frontend/
├── gis/
├── copilot/
├── rag/
├── simulation/
├── sensing/
├── evaluation/
│   ├── scenarios/
│   ├── ground_truth/
│   ├── runners/
│   ├── metrics/
│   └── reports/
├── database/                     # migrations + schema documentation only
├── model_artifacts/              # weights/exports, not runtime Python logic
├── datasets/
├── configs/
├── tests/
├── docker/
│   └── mosquitto/
├── docs/
│   ├── decision-log.md
│   ├── architecture.md
│   ├── api-contract.md
│   └── traceability.md
└── scripts/
```

## 5.1 Runtime ownership

### Edge owns

```text
camera providers
GNSS/IMU providers
frame acquisition
perception
tracking
quality
sensor health
Opportunity evaluation
Canonical Event construction
transport
offline buffering
```

### Backend owns

```text
validation
idempotency
deduplication
map matching
evidence
fusion
negative evidence
RoadTwin
Urban Memory
maintenance
repair verification
traffic aggregation
infrastructure state
alerts
RBAC
analytics
```

### Frontend owns

```text
presentation
GIS rendering
filters
charts
forms
authority interaction
API client integration
Copilot presentation
```

It does not own system truth.

---

# 6. Development Strategy — Vertical Slices

Do not implement all models first and all APIs later.

## Slice A — System proof

```text
Simulated bus
→ Canonical Event
→ Backend
→ PostGIS
→ RoadTwin
→ API
→ Frontend map
```

## Slice B — Real visual perception

```text
Recorded video
→ pothole detector
→ tracking/temporal grouping
→ GPS
→ quality
→ Opportunity
→ Event
→ MQTT
→ Backend
→ RoadTwin
→ GIS
```

## Slice C — Cooperative evidence

```text
BUS-001
+
BUS-002
→ independence classification
→ evidence
→ fusion
→ CONFIRMED
```

## Slice D — Closed-loop maintenance

```text
CONFIRMED
→ MAINTENANCE_PENDING
→ REPAIR_REPORTED
→ VERIFICATION_PENDING
→ valid negative evidence
→ VERIFIED_REPAIRED
→ later positive evidence
→ new reappearance episode
```

These four slices are the highest-priority integration objectives.

---

# 7. PHASE 0 — Repository, Docker, Environment

## Objective

Make the environment reproducible before feature work.

## Infrastructure

```text
PostgreSQL + PostGIS
Redis
MinIO / S3-compatible object storage
Mosquitto MQTT
```

## Required Compose path standard

Use:

```text
backend/
frontend/
docker/mosquitto/
```

Do not retain obsolete:

```text
central/
gis-dashboard/
infra/mosquitto/
```

references unless they are intentionally reintroduced and documented.

## DoD

```text
[ ] docker compose config succeeds
[ ] postgres starts
[ ] PostGIS extension enabled
[ ] redis responds
[ ] MinIO reachable
[ ] MQTT publish/subscribe works
[ ] .env works locally
[ ] .env.example is safe
[ ] .gitignore blocks secrets/data/weights
[ ] health checks pass
```

---

# 8. PHASE 1 — Contract Freeze

Contracts are frozen before large parallel implementation.

## 8.1 AI Observation contract

```text
observation_id
frame_id
bus_id
device_id
camera_id
timestamp
object_type
detector_confidence
bbox
mask_reference (optional)
track_id (optional)
trajectory_reference (optional)
model_name
model_version
evidence_hint (optional)
```

`detector_confidence` is the model's output only.

## 8.2 Observation Opportunity contract

```text
opportunity_id
sensing_pass_id
bus_id
device_id
camera_id
window_start
window_end
target_scope
target_type
target_id (only where target scope permits/needs one)
edge_road_segment_hint (optional, advisory)
fov_valid
visibility_score
illumination_score
blur_score
occlusion_score
viewing_angle_score
distance_score
sensor_health_score
gps_quality_score
opportunity_score
validity_status
invalid_reasons[]
coverage_fraction (when used for verification)
trace_id
```

### Target scopes

| Scope | Meaning | Target identity |
|---|---|---|
| `SEGMENT` | unknown road-condition sensing over a road segment | no pre-existing defect required |
| `ASSET` | known GIS asset expected at a location | `target_id` references the expected asset |
| `REGION` | area/geofence observation | region/geofence reference |
| `TRACK` | specific tracked object | `target_id` references `track_id` or equivalent |

### Opportunity semantics

```text
VALID + no Observation
    → eligible for Negative Evidence evaluation

INVALID + no Observation
    → inconclusive; never Negative Evidence

VALID + Observation
    → positive evidence path
```

Opportunity is a sibling concept to Observation, not a parent row containing every observation frame.

## 8.3 Canonical Event contract

```text
event_id
schema_version
bus_id
device_id
camera_id
event_timestamp
ingestion_timestamp
location
edge_road_segment_hint
matched_road_segment_id
map_match_confidence
map_match_status
event_type
observation_id
opportunity_id
evidence_ref
detector_confidence
observation_quality
gps_quality
model_name
model_version
priority
trace_id
producer_sequence
payload_hash
```

Backend-owned fields cannot be falsely populated as Edge truth.

## 8.4 Evidence contract

```text
evidence_id
event_id (nullable for negative evidence)
observation_id (nullable for negative evidence)
opportunity_id
polarity: POSITIVE | NEGATIVE
source_type
source_id
bus_id
camera_id
timestamp
matched_road_segment_id
map_match_status
detector_confidence (null/not applicable for negative)
observation_quality
opportunity_score
gps_quality
source_reliability
temporal_consistency
spatial_consistency
historical_consistency
independence_score
correlation_group_id
sensor_health
negative_evidence_strength (negative path)
evidence_weight
fusion_strategy
fusion_version
lineage
```

## 8.5 RoadTwin state contract

```text
roadtwin_id
road_segment_id
subject_id (when subject-linked)
subject_type
current_state
aggregate_confidence
positive_evidence_count
negative_evidence_count
independent_bus_count
first_seen_at
last_seen_at
last_validated_at
freshness_status
maintenance_status
verification_status
active_episode_id
previous_episode_id (when applicable)
history_ref
```

---

# 9. PHASE 2 — Edge HAL and Calibration

## 9.1 HAL providers

Interfaces:

```text
CameraProvider
GNSSProvider
IMUProvider
InferenceProvider
ClockProvider
StorageProvider
TransportProvider
```

Every provider must have:

```text
real implementation
simulated implementation
```

where practical.

## 9.2 Camera calibration

Entity:

```text
CAMERA_CALIBRATION
├── camera_id
├── calibration_version
├── intrinsics
├── extrinsics
├── mounting_height
├── orientation
├── horizontal_fov
└── vertical_fov
```

Prototype:

```text
approximate/assumed values
```

Production:

```text
hardware-specific measured calibration
```

Research:

```text
sensitivity of Opportunity validity to calibration error
```

No assistant may invent camera geometry and label it production-grade.

---

# 10. PHASE 3 — AI Perception Baseline

The implementation does **not** require one neural model per PS feature.

Use the smallest model set that covers the capability contract.

## 10.1 Road defects

Primary custom/task-specific model:

```text
pothole / road-surface defect model
```

Possible initial classes depend on available training data, but final class mapping must be documented.

Required PS road-condition scope includes:

```text
potholes
road damage
missing/damaged dividers
missing zebra crossings
missing/damaged traffic signs
waterlogging
other hazards
```

Not every class requires a separate neural network.

## 10.2 General object detection

Use a pretrained detector as the baseline for:

```text
car
bus
truck
motorcycle / 2W
bicycle
pedestrian
traffic sign
other required objects
```

Exact model variant is `DECISION_REQUIRED` until selected and benchmarked.

## 10.3 Tracking

Use a standard MOT tracker behind the detector.

Candidates may include ByteTrack or BoT-SORT, but the selected implementation must be recorded in the decision log.

## 10.4 Incident-specific perception

Do not create an unnecessary incident-specific deep model for every rule.

Prefer:

```text
perception
→ tracks
→ trajectories
→ IMU features
→ deterministic event logic
```

## 10.5 ANPR/OCR

ANPR is incident-triggered, not continuous raw-video transmission.

Maintain separate scores:

```text
vehicle_detection_confidence
plate_localization_confidence
ocr_confidence
```

Do not collapse these into one generic confidence value.

---

# 11. PHASE 4 — Tracking

Tracking must provide:

```text
track_id
first_seen
last_seen
class
bbox sequence
trajectory
camera_id
bus_id
track_quality
```

## 11.1 Tracking responsibilities

Tracking feeds:

```text
vehicle counting
traffic density
flow
trajectory analysis
TTC
rash-driving features
hit-and-run reconstruction
incident evidence
ANPR association
```

## 11.2 Cross-camera/cross-bus continuity

Prototype:

```text
same-camera temporal tracking
```

Advanced/research:

```text
probabilistic continuity across cameras/buses
```

Do not describe visual similarity alone as proof that two vehicles are the same physical vehicle.

---

# 12. PHASE 5 — Observation Quality and Sensor Health

Observation Quality answers:

> Was the observation itself visually usable?

Sensor Health answers:

> Was the sensing system functioning adequately?

Opportunity answers:

> Did the target have a valid opportunity to be observed?

These are separate signals.

## 12.1 Quality signals

```text
blur
illumination
visibility
occlusion
frame quality
viewing angle
distance
```

## 12.2 Sensor health

```text
camera availability
frame rate
GNSS health / accuracy
IMU health
storage health
transport health
```

Low sensor health must reduce evidence usefulness and can invalidate Negative Evidence.

## 12.3 Signal ownership

No signal should be silently multiplied twice.

Example:

```text
visibility → Opportunity
blur → Opportunity / quality path as explicitly defined
GPS quality → explicit GPS feature
sensor health → explicit health feature
```

The final implementation must follow the signal ownership table in the contract rather than recomputing the same factor inside multiple modules.

---

# 13. PHASE 6 — Observation Opportunity / Sensing Pass

## 13.1 SENSING_PASS

A sensing pass is a bounded observation window for a bus/camera/route traversal.

Conceptually:

```text
SENSING_PASS
├── pass_id
├── bus_id
├── device_id
├── route_id
├── camera set
├── start_time
├── end_time
├── trajectory reference
└── operating condition metadata
```

One `SENSING_PASS` can generate multiple Opportunities, but one Opportunity must represent a meaningful observation window rather than every frame.

## 13.2 Opportunity evaluator ownership

The only implementation is:

```text
edge/app/opportunity/opportunity_evaluator.py
```

It evaluates:

```text
FOV
visibility
illumination
blur
occlusion
viewing angle
distance
sensor health
GPS quality
```

It does not:

```text
calculate evidence_weight
change RoadTwin state
confirm a defect
```

## 13.3 Opportunity lifecycle

```text
created
→ evaluated
→ VALID / INVALID / UNCERTAIN
→ transported
→ persisted in Backend
```

The Opportunity can arrive before or after the Event because a sensing window may close after an Observation is generated.

Therefore Backend ingestion supports pending association.

---

# 14. PHASE 7 — Event Transport and Reliability

Transport:

```text
MQTT primary
HTTPS fallback
```

Delivery semantics:

```text
at-least-once transport
+
idempotent Backend ingestion
```

## 14.1 TransportEnvelope

Transport envelope fields:

```text
message_id
message_type
schema_version
producer_id
producer_sequence
created_at
retry_count
payload_hash
trace_id
```

Domain IDs remain in the domain payload:

```text
event_id
opportunity_id
heartbeat_id
telemetry_id
```

Do not require every message to carry an `event_id` when the message is not an Event.

## 14.2 Priority classes

```text
P0 = immediate safety/incident priority
P1 = high priority actionable event
P2 = normal actionable evidence
P3 = routine/batch telemetry or low-priority evidence
```

Exact routing policy is implementation-configurable, but high-priority events must bypass long batch delays.

## 14.3 Offline operation

When Backend is unavailable:

```text
Edge event
→ local durable queue
→ retry
→ acknowledgement
→ delete acknowledged item
```

The same `event_id` must remain stable across retries.

---

# 15. PHASE 8 — Backend Ingestion

Pipeline:

```text
receive
→ authenticate
→ schema validate
→ hash/duplicate check
→ persist transport receipt
→ map match
→ associate opportunity/observation
→ downstream processing
```

## 15.1 Idempotency

Repeated submission of the same `event_id` must not create duplicate business records.

Use unique constraints where appropriate.

## 15.2 Event-time semantics

```text
event_timestamp
    = when sensing happened

ingestion_timestamp
    = when Backend received it
```

Historical processing, lifecycle windows, 72-hour verification windows, persistence windows, and chronology must use `event_timestamp`.

`ingestion_timestamp` is operational telemetry.

Late-arriving events must be reconciled against historical state without silently changing the meaning of later events merely because the packet arrived late.

---

# 16. PHASE 9 — Authoritative Map Matching

Backend owns final spatial association.

Input:

```text
GPS
Edge hint
route context
road network
historical trajectory
```

Output:

```text
matched_road_segment_id
map_match_confidence
map_match_status
```

Statuses:

```text
MATCHED
AMBIGUOUS
UNMATCHED
```

## 16.1 Rules

`edge_road_segment_hint` is advisory.

`matched_road_segment_id` is the authoritative Backend association.

A low-confidence/ambiguous match must not be silently treated as a precise location.

Threshold for acceptance is `DECISION_REQUIRED` unless explicitly fixed in the decision log.

---

# 17. PHASE 10 — Deduplication and Spatial/Temporal Association

Purpose:

```text
100 repeated frames
≠
100 defects
```

## 17.1 Deduplication stages

```text
same observation window
→ temporal grouping
→ track grouping
→ spatial grouping
→ event-type grouping
→ duplicate classification
```

## 17.2 Correlation classification

Each candidate evidence contribution is classified as:

```text
DUPLICATE
CORRELATED
INDEPENDENT
```

and carries:

```text
correlation_group_id
```

Examples:

```text
same bus + same sensing pass + repeated frames
    → DUPLICATE/CORRELATED

same bus + different time pass
    → potentially independent, subject to policy

different buses + different times + valid conditions
    → stronger independence

different buses + same model failure/weather condition
    → partially correlated
```

---

# 18. PHASE 11 — Evidence Model and Fusion

## 18.1 Evidence feature vector

```text
polarity

detector_confidence
observation_quality
opportunity_score
gps_quality
source_reliability
temporal_consistency
spatial_consistency
historical_consistency
independence_score
correlation_penalty
sensor_health
negative_evidence_strength
```

## 18.2 MVP Fusion

Only `backend/app/fusion/engine.py` computes `evidence_weight`.

For positive evidence:

```text
evidence_weight_i
=
detector_confidence_i
× observation_quality_i
× gps_quality_i
```

After duplicate/correlation filtering:

```text
aggregate_confidence
=
1 − Π(1 − evidence_weight_i)
```

This is the MVP baseline, not the claimed final research model.

## 18.3 Negative evidence distinction

For negative evidence:

```text
detector_confidence
= not applicable
```

Instead:

```text
negative_evidence_strength_i
= per-pass derived evidence feature
```

Its exact formula must remain aligned to the documented negative-evidence model.

The cumulative:

```text
negative_evidence_score
```

is a separate aggregation concept.

Both the per-pass formula and cumulative aggregation must be explicitly defined in code/docs before being treated as finalized research logic.

## 18.4 Fusion strategy interface

```text
FusionStrategy
├── MVPFusionStrategy
└── ResearchFusionStrategy
```

`ResearchFusionStrategy` consumes the full EvidenceFeatures vector.

Possible research factors:

```text
quality awareness
opportunity awareness
correlation awareness
lifecycle awareness
uncertainty calibration
```

Do not hard-code a research formula before experiments.

---

# 19. PHASE 12 — Database Model

Core entities:

```text
BUS
EDGE_DEVICE
CAMERA
CAMERA_CALIBRATION
ROUTE
ROAD
ROAD_SEGMENT
SENSING_PASS
OBSERVATION_OPPORTUNITY
OBSERVATION
EVENT
EVIDENCE
ROAD_DEFECT
ROADTWIN_STATE
ROADTWIN_HISTORY
DEFECT_EPISODE
MAINTENANCE_TASK
REPAIR
VERIFICATION
AUTHORITY_ACTION
TRAFFIC_OBSERVATION
ROUTE_TRAVEL_TIME
INCIDENT
VEHICLE_TRACK
PLATE
INFRASTRUCTURE_ASSET
GEOFENCE_REGION
ALERT
SENSOR_HEALTH
COVERAGE
MODEL
MODEL_VERSION
USER
DEPARTMENT
```

## 19.1 Relationship model

```text
BUS 1—N EDGE_DEVICE
EDGE_DEVICE 1—N CAMERA
CAMERA 1—N CAMERA_CALIBRATION
BUS 1—N SENSING_PASS
SENSING_PASS 1—N OBSERVATION_OPPORTUNITY
OBSERVATION_OPPORTUNITY 0—N OBSERVATION
OBSERVATION 0—N EVIDENCE
EVENT N—1 MODEL_VERSION
EVENT 0..1—1 OBSERVATION
EVENT 0..1—1 OBSERVATION_OPPORTUNITY
ROAD 1—N ROAD_SEGMENT
ROUTE N—N ROAD_SEGMENT
ROAD_SEGMENT 1—N OBSERVATION/EVENT/COVERAGE/TRAFFIC_OBSERVATION
ROAD_SEGMENT 1—N ROAD_DEFECT / DEFECT_EPISODE
ROAD_SEGMENT 1—1 current ROADTWIN_STATE
ROADTWIN_STATE 1—N ROADTWIN_HISTORY
DEFECT_EPISODE 1—N EVIDENCE
DEFECT_EPISODE 0..N MAINTENANCE_TASK
MAINTENANCE_TASK 0..1—1 REPAIR
REPAIR 1—1 VERIFICATION (when verification record exists)
AUTHORITY_ACTION N—1 USER
INFRASTRUCTURE_ASSET N—1 ROAD_SEGMENT
GEOFENCE_REGION 1—N targetable events/opportunities
INCIDENT 1—N VEHICLE_TRACK
INCIDENT 0..N—1 PLATE
```

Exact foreign-key cardinality may be tightened during implementation, but relationship ownership must not contradict this model.

## 19.2 Append-only history

Append-only domains:

```text
EVENT
EVIDENCE
ROADTWIN_HISTORY
AUTHORITY_ACTION
REPAIR audit records
VERIFICATION audit records
transport receipt/audit records
```

Current-state tables may update, but historical transitions are never overwritten without a history record.

---

# 20. PHASE 13 — RoadTwin Identity and Defect Episodes

This is a final architectural rule.

## 20.1 RoadTwin is segment-level

RoadTwin is the canonical **per-road-segment urban state layer**.

It is not a single pothole object.

A road segment can contain multiple physical issue subjects.

```text
ROAD_SEGMENT
   │
   └── ROADTWIN_STATE
         ├── road condition
         ├── traffic state
         ├── infrastructure state
         ├── incident state
         ├── freshness
         └── active issue references
               ├── defect episode A
               ├── defect episode B
               └── infrastructure issue C
```

## 20.2 Defect episode

A defect/issue subject represents a persistent physical problem/episode.

```text
defect_episode_id
road_segment_id
issue_type
site_reference
geometry / location
first_observed_at
last_observed_at
current_lifecycle_state
previous_episode_id
repair_reference
verification_reference
reappearance_of_episode_id (when applicable)
```

This separation resolves the previous ambiguity between:

```text
segment
roadtwin
road defect
```

---

# 21. PHASE 14 — RoadTwin Lifecycle

States:

```text
OBSERVED
CANDIDATE
CONFIRMED
MAINTENANCE_PENDING
REPAIR_REPORTED
VERIFICATION_PENDING
VERIFIED_REPAIRED
REAPPEARED
```

Exactly one state machine exists under:

```text
backend/app/roadtwin/
```

## 21.1 Subject creation

A qualifying positive observation creates or associates with an issue subject.

If the association is uncertain, retain the observation without falsely attaching it to an existing subject.

## 21.2 Transition matrix

| Transition | Trigger | Evidence | Notes |
|---|---|---|---|
| OBSERVED → CANDIDATE | basic validation passes | qualifying positive observation | threshold `DECISION_REQUIRED` unless source-fixed |
| CANDIDATE → CONFIRMED | corroboration/persistence rule met | independent high-quality evidence | unique bus/pass policy + aggregate threshold |
| CONFIRMED → MAINTENANCE_PENDING | authority prioritization | existing confirmed evidence | priority is operational, not model confidence |
| MAINTENANCE_PENDING → REPAIR_REPORTED | authority reports repair | authenticated authority action | audit required |
| REPAIR_REPORTED → VERIFICATION_PENDING | automatic | none additional | starts prioritized re-observation |
| VERIFICATION_PENDING → VERIFIED_REPAIRED | negative-evidence criteria satisfied | multiple valid independent passes | repair verification |
| VERIFIED_REPAIRED → REAPPEARED | qualifying new positive evidence | site/subject association | creates a new active defect episode while preserving history |

## 21.3 Confirmation thresholds

The source establishes the concept of independent corroboration and configurable lifecycle thresholds.

Unless the final source configuration fixes the exact numbers:

```text
OBSERVED → CANDIDATE quality threshold = DECISION_REQUIRED
CANDIDATE → CONFIRMED aggregate threshold = DECISION_REQUIRED
corroboration time window = DECISION_REQUIRED
```

Do not guess them.

## 21.4 Maintenance priority

Priority remains distinct from:

```text
AI detector confidence
raw defect severity
```

The source proposes factors including:

```text
severity
traffic exposure
pedestrian vulnerability
school proximity
persistence
road importance
recurrence
independent corroboration
observation quality
```

Exact weights are `PROPOSED` / `DECISION_REQUIRED` until authority policy is selected.

## 21.5 Failure paths

Every transition must have a rejection/failure result.

Example:

```text
low-quality evidence
→ no transition

insufficient independence
→ remain CANDIDATE

ambiguous map match
→ no spatial confirmation

unauthorized repair report
→ no transition + audit
```

---

# 22. PHASE 15 — Freshness and Staleness

RoadTwin must expose freshness separately from state.

Required fields:

```text
last_validated_at
freshness_status
```

Suggested status vocabulary:

```text
CURRENT
AGING
STALE
```

The exact decay/freshness function is `DECISION_REQUIRED`.

Important semantic rule:

```text
STALE CONFIRMED
≠
CURRENT CONFIRMED
```

A stale state means the system has not recently revalidated the state; it does not mean the defect has disappeared.

GIS/API/Copilot must be able to distinguish these conditions.

---

# 23. PHASE 16 — Negative Evidence

Negative Evidence exists to answer:

> Was there a sufficiently good opportunity to look and not detect the target?

## 23.1 Ordered gate logic

For absence-based reasoning:

```text
1. Expected target/site is relevant to this pass
2. Bus traversed the expected spatial region
3. GPS/time alignment is usable
4. Target entered the camera's observable region
5. FOV condition valid
6. Visibility adequate
7. Illumination adequate
8. Occlusion acceptable
9. Motion blur acceptable
10. Sensor health acceptable
11. Map match acceptable
12. No qualifying positive observation exists
13. Only then can the pass contribute Negative Evidence
```

Any failed gate:

```text
INCONCLUSIVE
```

not:

```text
ABSENT
```

## 23.2 Negative Evidence formula status

The source material gives the conceptual per-pass formulation:

```text
Negative Evidence
=
Coverage × Visibility × SensorHealth × DetectionReliability
```

The implementation should preserve this as the baseline conceptual model, while the exact named fields and aggregation must be frozen before claims are made.

## 23.3 Segment-scope negative evidence

A valid `SEGMENT` Opportunity can exist before a particular defect subject exists.

Its spatial observation coverage is stored as:

```text
observed_extent
```

or the equivalent approved coverage representation.

When a defect subject is later associated to that spatial site, qualifying historical Opportunities may be linked only if their timestamps, spatial extent, target scope, and sensing conditions satisfy the association policy.

Do not retroactively label every historical non-detection as evidence against a newly discovered defect.

---

# 24. PHASE 17 — Repair Verification and Reappearance

## 24.1 Verification inputs

Source-supported verification criteria include:

```text
min_independent_passes >= 3
min_coverage_per_pass >= 80%
sensor_health == OK
negative_evidence_score >= 0.85
new_positive_evidence == 0 over a 72-hour window
```

These values are preserved because they are explicitly present in the supplied UrbanSense v3.1 source. The exact implementation fields for `coverage_fraction`, sensor-health pass criteria, and the aggregation formula for `negative_evidence_score` must remain traceable in code/tests.

## 24.2 Independent pass definition

A pass counts as independent only when it satisfies the approved independence policy.

Minimum conceptual dimensions:

```text
distinct bus/pass identity
sufficient temporal separation
valid sensing conditions
not a duplicate camera/frame sequence
```

Common failure mode:

```text
BUS-001 frame 001
BUS-001 frame 002
BUS-001 frame 003

≠ 3 independent passes
```

## 24.3 Verification failure

A new qualifying positive observation during verification:

```text
resets the clean verification window
```

and may keep the subject in:

```text
VERIFICATION_PENDING
```

or move it back toward an active lifecycle state according to the approved transition policy.

## 24.4 Reappearance

Reappearance must not overwrite the historical repaired episode.

```text
Old episode
     ↓
VERIFIED_REPAIRED
     ↓
new positive evidence
     ↓
site/subject association
     ↓
NEW active defect episode
     ↓
CANDIDATE
     ↓
normal confirmation process
```

The new episode references the historical episode:

```text
reappearance_of_episode_id
```

This preserves recurrence history.

Exact spatial/temporal association thresholds are `DECISION_REQUIRED`.

---

# 25. PHASE 18 — Maintenance and Authority Actions

The platform needs an auditable action record, not only a repair table.

## AuthorityAction

```text
action_id
actor_user_id
role
department
action_type
target_type
target_id
timestamp
reason
previous_state
result_state
audit_reference
```

Examples:

```text
ACKNOWLEDGE_DEFECT
CREATE_MAINTENANCE_TASK
ASSIGN_TASK
REPORT_REPAIR
REOPEN_REVIEW
ACKNOWLEDGE_ALERT
```

## 25.1 RBAC

Minimum roles:

```text
TRANSPORT_AUTHORITY
ROADS_AUTHORITY
POLICE/INCIDENT_AUTHORITY
ADMIN
VIEWER/ANALYST
```

Exact role mapping is `DECISION_REQUIRED` if not already frozen.

Backend enforcement is authoritative.

Frontend hiding alone is never sufficient security.

---

# 26. PHASE 19 — Traffic Intelligence

Traffic intelligence is primarily an aggregation/reasoning problem, not another giant neural network.

Pipeline:

```text
vehicle detection
→ tracking
→ trajectories
→ counts
→ segment aggregation
→ density / flow / congestion
→ bottleneck
→ route delay
→ OD proxy
```

## 26.1 Vehicle counting

Aggregate tracked vehicles by:

```text
segment
window
vehicle class
camera/bus/pass
```

## 26.2 Density

Compute the documented segment/time-window density representation.

Exact threshold definitions must be traceable to configuration.

## 26.3 Bottleneck

Source-supported logic:

```text
density high
AND fleet speed low
AND persistence across rolling windows
→ bottleneck
```

The supplied v3.1 specification describes a rolling 3-window condition. Preserve that requirement and record exact high/low thresholds in configuration rather than hard-coding unexplained numbers.

## 26.4 Speed source

Prototype:

```text
GPS/telemetry-derived speed
```

Production:

```text
production-grade GNSS and possibly IMU fusion
```

Research:

```text
camera-geometry/homography validation against GPS
```

Do not turn raw pixel motion into physical speed without calibration.

## 26.5 Route delay

```text
observed segment traversal time
vs.
scheduled/historical baseline
```

Event-time timestamps are used.

## 26.6 OD proxy

Use bus trajectory transitions through configured geographic zones.

```text
clean GPS
→ map match route/zone
→ zone transition
→ time-window aggregation
→ coverage normalization
```

The system must clearly label this as a **fleet trajectory OD proxy**, not passenger-level OD truth.

---

# 27. PHASE 20 — Infrastructure Intelligence

Infrastructure targets:

```text
traffic signs
dividers
zebra crossings
other expected fixed assets
```

## 27.1 Expected-vs-observed model

```text
GIS Expected Asset
        ↓
Valid Observation Opportunities
        ↓
Observed presence/absence evidence
        ↓
Negative Evidence gates
        ↓
Infrastructure state
```

A missing asset is never inferred from one poor/occluded pass.

## 27.2 Infrastructure states

Use a documented vocabulary, for example:

```text
EXPECTED
OBSERVED
POTENTIAL_MISSING
DAMAGED
VERIFICATION_REQUIRED
```

The exact public API vocabulary must be synchronized across Backend and Frontend.

---

# 28. PHASE 21 — VRU / Safety Intelligence

Inputs:

```text
pedestrian tracks
vehicle tracks
trajectory geometry
GIS school zones
```

## 28.1 TTC

TTC is deterministic trajectory/geometric reasoning over tracking output.

Prototype:

```text
trajectory-based TTC with calibrated/simulated spatial units
```

No unvalidated physical assumptions.

If physical units are not reliable, label the output accordingly rather than claiming a physically calibrated TTC.

## 28.2 School-zone context

The supplied v3.1 specification defines a school-zone context that increases risk weighting and tightens the TTC criterion.

The exact production policy must be configuration-driven and traceable.

---

# 29. PHASE 22 — Incident Intelligence

Required incident capabilities include:

```text
rash/unsafe driving
hit-and-run
offending vehicle tracking
incident evidence
```

## 29.1 Rash driving

Possible deterministic features:

```text
IMU lateral acceleration
IMU longitudinal acceleration
erratic lane-change features
trajectory anomalies
```

The chosen trigger thresholds must be explicitly documented.

## 29.2 Hit-and-run

Source-supported conceptual sequence:

```text
collision/impact signature
→ sudden deceleration or impact evidence
→ vehicle track
→ vehicle leaves scene/frame
→ incident candidate
```

No single visual frame should be called a confirmed crime.

## 29.3 Human review

The system should present:

```text
AI detected event
→ evidence package
→ authority review
→ authority action
```

The AI does not autonomously adjudicate criminal responsibility.

---

# 30. PHASE 23 — ANPR / OCR

ANPR is restricted and incident-triggered.

Pipeline:

```text
incident trigger
→ targeted frame buffer
→ vehicle crop
→ plate localization
→ OCR
→ independent scores
→ evidence record
```

Persist:

```text
vehicle_detection_confidence
plate_localization_confidence
ocr_confidence
GPS/time
incident link
trace/evidence reference
```

ANPR access must be RBAC-restricted.

Unauthorized requests return `403`, not an empty result.

---

# 31. PHASE 24 — Coverage Intelligence

Coverage answers:

> Where have we observed, and where do we not have trustworthy recent observations?

Coverage must distinguish:

```text
no evidence
vs.
valid opportunity with no detection
vs.
invalid opportunity
vs.
stale historical coverage
```

This avoids turning sensing gaps into false safety claims.

Potential future extension:

```text
next-best bus / next-best sensing opportunity
```

This is an advanced/research extension unless explicitly promoted after the core build.

---

# 32. PHASE 25 — Alerting

Alert Engine consumes authoritative Backend state, not raw detector output alone.

Example semantic levels:

```text
P0 immediate incident/safety
P1 high-priority actionable issue
P2 standard authority action
P3 routine/nonurgent
```

Every alert should carry:

```text
alert_id
priority
target_type
target_id
trigger
supporting evidence refs
created_at
acknowledgement state
RBAC scope
```

Alert generation must be deterministic and explainable.

---

# 33. PHASE 26 — API Architecture

FastAPI is the source of truth for HTTP schemas.

```text
Pydantic/FastAPI schemas
        ↓
OpenAPI
        ↓
Generated/synchronized TypeScript client
        ↓
Frontend
```

## 33.1 Ingestion APIs

```text
POST /api/v1/events
POST /api/v1/opportunities
POST /api/v1/evidence
POST /api/v1/device/heartbeat
POST /api/v1/telemetry
```

## 33.2 Device APIs

```text
GET /api/v1/device/config
GET /api/v1/sensor-health
```

## 33.3 RoadTwin / defect APIs

```text
GET /api/v1/roadtwin
GET /api/v1/roadtwin/{id}
GET /api/v1/roadtwin/history/{id}
GET /api/v1/road-segments/{id}
GET /api/v1/road-defects
GET /api/v1/road-defects/{id}
```

## 33.4 Traffic / coverage / infrastructure APIs

```text
GET /api/v1/traffic
GET /api/v1/bottlenecks
GET /api/v1/route-delay
GET /api/v1/od-analytics
GET /api/v1/coverage
GET /api/v1/infrastructure
```

## 33.5 Incidents / ANPR

```text
GET /api/v1/incidents
GET /api/v1/incidents/{id}/evidence
GET /api/v1/anpr/{plate_id}
```

Restricted data must enforce RBAC.

## 33.6 Maintenance / verification

```text
GET /api/v1/maintenance
POST /api/v1/maintenance/{id}/repair
GET /api/v1/verification
```

## 33.7 Analytics / Copilot / GIS

```text
GET /api/v1/analytics
GET /api/v1/alerts
GET /api/v1/gis/layers
POST /api/v1/copilot/query
```

## 33.8 Error envelope

All APIs use one consistent machine-readable error structure.

RBAC failure:

```text
403 Forbidden
```

not:

```text
200 + empty list
```

---

# 34. PHASE 27 — Backend Read Models and Explainability

The frontend must not need to understand fusion internals.

Backend should expose explanation/read-model data such as:

```text
state
state_reason
contributing_evidence_count
independent_bus_count
opportunity_status
invalid_opportunity_reasons
last_validated_at
freshness_status
maintenance status
repair/verification status
history references
```

This lets the UI explain:

```text
Why is this CANDIDATE?
Why did it become CONFIRMED?
Why was a pass excluded from Negative Evidence?
Why is a state STALE?
Why did repair verification not complete?
```

The Frontend should render the explanation supplied by the Backend rather than recomputing the rules.

---

# 35. PHASE 28 — GIS

GIS is an application/read layer over authoritative Backend data.

The supplied v3.1 specification requires a complete 20-layer GIS capability set for the final build. The exact layer matrix must be reconciled against the authoritative GIS source before the layer names are frozen.

At minimum the platform must cover the source-defined domains:

```text
Road Health
Traffic / Congestion
Incidents
Infrastructure
Fleet
Maintenance
Historical RoadTwin
Coverage
```

The implementation contract is:

```text
Backend query
→ GeoJSON/typed response
→ Frontend map layer
```

The Frontend does not reconstruct spatial truth from raw events.

---

# 36. PHASE 29 — GenAI Copilot

Architecture:

```text
Authority user
      ↓
Natural-language input
      ↓
Intent parsing
      ↓
RBAC check
      ↓
Authorized Backend tool/query
      ↓
Structured result
      ↓
LLM explanation
```

The LLM must not:

```text
directly query PostgreSQL
directly change RoadTwin state
bypass RBAC
invent traffic values
invent maintenance status
invent incidents
invent fleet statistics
```

## 36.1 Copilot examples

```text
Show recurrent potholes.
Which roads need maintenance attention?
What changed on this road after repair?
Show recent serious incidents on Route X.
Why is this road marked stale?
```

Every answer must be traceable to a Backend query result.

---

# 37. PHASE 30 — RAG

RAG is a knowledge-support layer, not the source of RoadTwin truth.

Use RAG for:

```text
SOPs
authority procedures
safety procedures
policy documents
operational guidance
```

Do not use RAG as the source of:

```text
current RoadTwin state
current traffic counts
fleet status
route delay values
detector confidence
maintenance state
```

---

# 38. PHASE 31 — Simulation and Demo Engine

The demo must be reproducible without manually editing the database.

Simulation identities:

```text
BUS-001
BUS-002
BUS-003
```

Each simulated bus needs:

```text
route
video source
GPS trace
IMU trace
camera identity
device identity
timestamp policy
```

## 38.1 Demo commands

Conceptually:

```text
reset
seed
run
verify
```

No manual DB state manipulation is acceptable for the primary demo.

---

# 39. PHASE 32 — Evaluation Harness

Evaluation is a first-class repository subsystem.

```text
evaluation/
├── scenarios/
├── ground_truth/
├── runners/
├── metrics/
└── reports/
```

## 39.1 GroundTruth schema

```text
scenario_id
subject_id
true_state
true_observation_windows
true_positive_events
true_valid_opportunities
repair_timestamp
reappearance_timestamp
expected_state_transitions
expected_independent_passes
expected_map_match_class
```

## 39.2 Core scenarios

```text
A — Single positive bus
B — Two independent buses
C — Repeated same-bus observations
D — Camera failure
E — Bad GPS
F — Valid healthy pass with no detection
G — Repair + valid negative evidence
H — Repair + later reappearance
I — Conflicting observations
J — Stale / delayed / out-of-order event
```

## 39.3 Metrics

### Perception

```text
precision
recall
F1
mAP where applicable
```

### Tracking

```text
ID consistency
ID switches
track accuracy metrics appropriate to selected tracker
```

### Fusion/RoadTwin

```text
confirmation precision
false confirmation rate
missed confirmation rate
reappearance detection correctness
transition correctness
negative-evidence false-absence rate
```

### Traffic

```text
count error / MAE
speed/travel-time error
bottleneck classification correctness
```

### System

```text
FPS
frame-to-event latency
event-to-ingestion latency
end-to-end latency
CPU/memory utilization
network payload size
retry rate
queue depth
```

Never publish an unmeasured number.

---

# 40. PHASE 33 — Failure Handling

Test explicitly:

```text
network loss
Backend outage
MQTT duplication
late events
out-of-order events
invalid schema
bad GPS
ambiguous map match
camera failure
low-light frames
motion blur
heavy occlusion
missing Opportunity
Opportunity delayed relative to Event
conflicting buses
model failure
stale events
unauthorized ANPR access
unauthorized repair action
Copilot failure
object storage failure
```

Expected system behavior must be defined for each failure.

---

# 41. PHASE 34 — Observability

Every end-to-end path must be traceable:

```text
frame
→ model inference
→ observation
→ opportunity
→ event
→ transport
→ ingestion
→ DB
→ evidence
→ fusion
→ RoadTwin
→ API
→ GIS
```

Use:

```text
trace_id
producer_sequence
event_id
observation_id
opportunity_id
evidence_id
roadtwin_id
```

Log:

```text
processing latency
retries
duplicate rate
map-match status
fusion decisions
state transitions
health failures
```

---

# 42. PHASE 35 — Security

Required:

```text
device credentials
user authentication
RBAC
TLS in production
secret management
audit logging
least-privilege data access
restricted evidence/ANPR access
```

Security principle:

```text
Backend enforcement > Frontend visibility rules
```

Sensitive artifacts should be stored in controlled object storage, not Git.

---

# 43. PHASE 36 — Deployment Architecture

Prototype target:

```text
Vercel
    ↓
HTTPS
    ↓
FastAPI Backend
    ↓
PostgreSQL/PostGIS
    ↓
Object storage
MQTT broker
Redis
```

Exact vendors/hosting services remain `DECISION_REQUIRED` until recorded in `docs/decision-log.md`.

## 43.1 Deployment separation

```text
Frontend hosting
Backend hosting
Database hosting
Object storage
MQTT
secrets
observability
```

must be independently replaceable.

## 43.2 Laptop-to-edge migration

Prototype:

```text
laptop
```

Future:

```text
appropriate Jetson-class / edge accelerator
```

The architecture must not assume that the laptop's compute profile is the final hardware profile.

---

# 44. Core PS Capability Map

The current UrbanSense v3.1 Team Master Specification internally organizes its capability contract as R01–R29. These are **internal traceability identifiers** and must not be presented as an official PS requirement count without the final requirement reconciliation.

## Group 1 — Road & Infrastructure

```text
R01–R08 internal capability references
```

Coverage:

```text
potholes
road damage
missing/damaged dividers
missing zebra crossings
missing/damaged signs
waterlogging
other road hazards
infrastructure deficiency
```

## Group 2 — Traffic / Fleet / OD Proxy

```text
R09–R15 internal capability references
```

Coverage:

```text
vehicle detection/classification
vehicle counting
density
bottleneck
route delay
fleet mobility
OD proxy
```

## Group 3 — Safety / Incidents / ANPR

```text
R16–R22 internal capability references
```

Coverage:

```text
VRU risk
school-zone context
rash driving
hit-and-run
incident tracking
vehicle tracking
ANPR/OCR
```

## Group 4 — Platform / GIS / Authority / Edge Efficiency

```text
R23–R29 internal capability references
```

Coverage:

```text
secure alerting
aggregation/fusion
GIS
heatmaps
infrastructure deficiency
Copilot / insights
bandwidth-aware event transport
```

This group structure is source-derived from the supplied v3.1 capability contract.

---

# 45. Delivery Tiers

Tiering controls depth, not whether a required capability is silently removed.

## Tier A — Core lifecycle

```text
Edge
Observation
Opportunity
Transport
Backend
Map matching
Evidence
Fusion
RoadTwin
Maintenance
Repair
Verification
Negative evidence
Reappearance
```

Tier A must be deeply integrated and reliable.

## Tier B — Supporting PS breadth

```text
road-defect breadth
infrastructure
traffic
bottleneck
route delay
OD proxy
VRU
incidents
coverage
alerts
GIS breadth
```

## Tier C — Advanced extensions

```text
ANPR depth
Copilot depth
RAG
advanced uncertainty
research fusion
active sensing
cross-bus continuity research
```

Tier C may be shallower than Tier A without invalidating the Tier A architecture.

---

# 46. Milestone-Driven Execution Plan

This replaces the old interpretation that every feature must be complete inside a calendar week.

## Milestone 0 — Foundation

```text
repo cleanup
Docker
PostGIS
Redis
MinIO
MQTT
configuration
health checks
```

Exit condition:

```text
infrastructure green
```

## Milestone 1 — First End-to-End Slice

```text
contracts
HAL
simulated GNSS/IMU
Opportunity stub/evaluator
Canonical Event
POST /events
POST /opportunities
DB persistence
minimal RoadTwin
generated API client
frontend map
```

Exit condition:

> A simulated observation enters the real Backend and appears in the real Frontend.

## Milestone 2 — Real Perception

```text
recorded video
pothole baseline
vehicle detector
tracking
quality
camera calibration
Opportunity evaluator
Evidence crop/reference
```

Exit condition:

```text
real video → Backend → GIS
```

## Milestone 3 — Cooperative Evidence

```text
dedup
independence classification
map matching
MVP fusion
OBSERVED/CANDIDATE/CONFIRMED
```

Exit condition:

```text
BUS-001 + BUS-002
→ CONFIRMED
```

## Milestone 4 — Closed Loop

```text
maintenance
RBAC
AuthorityAction
repair report
verification priority
negative evidence
repair verification
freshness
reappearance episodes
```

Exit condition:

```text
CONFIRMED
→ repair
→ VERIFIED_REPAIRED
→ REAPPEARED
```

## Milestone 5 — PS Breadth

```text
infrastructure
traffic
bottleneck
route delay
OD proxy
VRU
incidents
alerts
coverage
GIS breadth
```

## Milestone 6 — Restricted/Advanced Functions

```text
ANPR
Copilot
RAG
advanced analytics
```

Only after core integration is stable.

## Milestone 7 — Hardening

```text
failure injection
security
observability
performance benchmarks
API consistency
data retention
deployment
```

## Milestone 8 — Demo Lock

```text
seed/reset/run/verify
rehearsal
PPT claims audit
deployment audit
```

---

# 47. Practical Daily Execution Order

When overloaded:

```text
1. correctness
2. integration
3. Tier A lifecycle
4. required PS breadth
5. tests
6. reliability
7. security
8. performance
9. UI polish
10. research extensions
```

Never reverse this order merely because a dashboard looks visually incomplete.

---

# 48. Developer Ownership

## You — AI / Backend / Fusion / RoadTwin

Own:

```text
AI/CV
tracking
HAL
quality
sensor health
Opportunity
Canonical Event
transport
Backend
PostGIS
map matching
dedup
Evidence
Fusion
Negative Evidence
RoadTwin
Urban Memory
maintenance
repair verification
RBAC backend
security
integration
deployment
research evaluation
```

## Teammate — Frontend / GIS / Analytics / Copilot

Own:

```text
React + TypeScript
API client
application shell
GIS
maps
charts
dashboards
RoadTwin presentation
fleet UI
traffic UI
infrastructure UI
incident UI
maintenance UI
coverage UI
alerts UI
Copilot UI
demo workflow
Vercel
```

Interface:

```text
OpenAPI-generated client
+
RoadTwin response contract
+
read-model explanation contract
```

---

# 49. API Change Protocol

Any endpoint change requires:

```text
route
HTTP method
request schema
response schema
auth
RBAC
validation
errors
status codes
tests
example
OpenAPI update
frontend client regeneration
```

Never hand-patch generated TypeScript to compensate for a Backend schema change.

---

# 50. Coding-Assistant Architectural Preflight

Before changing code, a coding assistant must answer:

```text
1. Which module owns this concern?
2. What is the input contract?
3. What is the output contract?
4. Which upstream modules feed it?
5. Which downstream modules consume it?
6. Which semantic confidence/quality fields apply?
7. Does this require Observation Opportunity?
8. Does this affect Evidence lineage?
9. Does this affect RoadTwin state?
10. Does an implementation already exist elsewhere?
11. Does OpenAPI change?
12. What tests must change?
```

The assistant must inspect the repository before editing.

---

# 51. Master Coding Prompt

Use this prompt for bounded implementation tasks.

```text
You are a senior production engineer working on UrbanSense AI,
SIH Problem Statement 26124.

Repository:
D:/UrbanSense AI

TASK:
[ONE bounded task]

FIRST:
Inspect the repository, contracts, existing implementations, tests,
configuration and dependencies before changing anything.

RUN THE ARCHITECTURAL PREFLIGHT:
1. ownership
2. input contract
3. output contract
4. upstream/downstream dependencies
5. semantic meaning of quality/confidence fields
6. Observation Opportunity requirement
7. Evidence lineage impact
8. RoadTwin impact
9. duplicate logic search
10. API/OpenAPI/test impact

HARD RULES:
- Do not create a second FusionEngine.
- FusionEngine is backend/app/fusion/engine.py.
- Do not create a second RoadTwin state machine.
- RoadTwin lives under backend/app/roadtwin/.
- Do not create a second Opportunity evaluator.
- Opportunity evaluation lives under edge/app/opportunity/.
- Do not compute evidence_weight outside the FusionEngine.
- Do not treat an Observation without a VALID Opportunity as Negative Evidence.
- Do not treat an Edge road-segment hint as authoritative.
- Do not use a bare confidence field.
- Do not invent lifecycle thresholds.
- Do not invent physical speed/TTC assumptions.
- Do not invent deployment architecture choices.
- Do not silently change public contracts.
- Do not create root-level runtime duplicates of Edge/Backend concerns.
- Do not implement RoadTwin transitions in the Frontend.
- Do not bypass RBAC.
- Do not replace deterministic Backend analytics with an LLM.
- Do not claim completion when tests fail.

IMPLEMENTATION:
Make the smallest clean change satisfying the approved contract.

AFTER:
1. list changed files
2. explain the design
3. run relevant tests
4. report exact pass/fail
5. report limitations
6. identify any DECISION_REQUIRED item
```

---

# 52. Repository Inspection Prompt

```text
Inspect UrbanSense without modifying it.

Report:
1. directory structure
2. Edge entrypoints
3. Backend entrypoints
4. Frontend entrypoints
5. Docker services
6. contract definitions
7. database models/migrations
8. API routes
9. tests
10. TODOs
11. broken imports/paths/configuration
12. duplicate business logic
13. duplicate Fusion/RoadTwin/Opportunity implementations
14. unresolved DECISION_REQUIRED items

Do not propose a large rewrite.
Recommend the smallest next task.
```

---

# 53. Debugging Prompt

```text
Debug this UrbanSense problem.

ERROR:
[paste]

EXPECTED:
[paste]

ACTUAL:
[paste]

Inspect traceback, code, contract, tests, configuration,
dependencies and upstream/downstream interfaces.

Do not blindly patch.

Find the root cause.

Then:
1. explain root cause
2. propose minimal fix
3. implement
4. add regression test
5. run relevant tests
6. report exact results
```

---

# 54. Code Review Prompt

```text
Review this UrbanSense change as a principal engineer.

Check:
- contract violations
- architecture violations
- duplicate logic
- semantic confidence mistakes
- Opportunity mistakes
- Evidence lineage mistakes
- incorrect state transitions
- event-time bugs
- map-match mistakes
- security/RBAC problems
- race conditions
- append-only/history violations
- performance risks
- observability gaps
- test gaps

Return:
Critical
Major
Minor
Recommended fixes
Required tests
```

---

# 55. RoadTwin Review Checklist

Every transition review must include:

```text
source state
target state
trigger
required evidence
independence rule
time condition
negative-evidence requirement
transition reason
history record
failure/rejection path
freshness impact
```

No transition may be introduced outside the authoritative state machine.

---

# 56. Fusion Review Checklist

Every fusion decision should be inspectable through:

```text
source observations
source opportunities
validity status
invalid reasons
detector_confidence
observation_quality
gps_quality
independence classification
correlation group
evidence_weight
aggregate_confidence
fusion strategy/version
transition reason
```

---

# 57. Database Change Checklist

Every database change requires:

```text
migration
model
constraints
foreign keys
indexes
query path
seed/demo data if necessary
test
rollback consideration
```

History tables must not become mutable scratchpads.

---

# 58. Frontend Contract Rules

Frontend may render:

```text
current state
freshness
confidence/evidence metadata
history
maps
analytics
alerts
maintenance actions permitted by RBAC
```

Frontend may not calculate:

```text
RoadTwin transition
Evidence weight
Negative Evidence eligibility
map-match authority
maintenance priority truth
```

It may perform UI-only formatting and filtering over Backend responses.

---

# 59. Primary Demo Scenario

The primary demo is the closed lifecycle.

```text
BUS-001
  ↓
pothole observation
  ↓
VALID Opportunity
  ↓
Canonical Event
  ↓
Backend map match
  ↓
Evidence
  ↓
CANDIDATE
  ↓
BUS-002 independent pass
  ↓
Evidence Fusion
  ↓
CONFIRMED
  ↓
Maintenance priority
  ↓
Authority reports repair
  ↓
REPAIR_REPORTED
  ↓
VERIFICATION_PENDING
  ↓
BUS-003 and future valid passes
  ↓
Negative Evidence
  ↓
VERIFIED_REPAIRED
  ↓
later positive observation at associated site
  ↓
new reappearance episode
  ↓
REAPPEARED
```

The demo must be executed from the real system, not by preloading the final state.

---

# 60. Secondary Demo Beats

Only after the primary lifecycle is stable:

```text
traffic congestion
bottleneck
route delay
infrastructure deficiency
VRU risk
incident with evidence timeline
ANPR restricted view
coverage map
historical RoadTwin
Copilot query
```

The primary lifecycle must not be compromised to demonstrate breadth.

---

# 61. Final Judge Experience

The judge should be able to follow this story:

```text
Mobile fleet sensing
        ↓
On-edge perception
        ↓
Quality-aware observation
        ↓
Backend spatial association
        ↓
Independent multi-bus evidence
        ↓
Trusted RoadTwin state
        ↓
Authority action
        ↓
Fleet-based repair verification
        ↓
Persistent historical memory
        ↓
Reappearance detection
```

The technical differentiator presented in the demo is the lifecycle and evidence chain, not the mere existence of an object detector.

---

# 62. Research Track

Research stays isolated from the SIH baseline.

## Research question

```text
Can lifecycle-aware, opportunity-aware and correlation-aware
probabilistic evidence fusion improve urban road-state estimation
and repair verification compared with simpler baselines?
```

## Baselines

```text
Baseline 1 — raw detector
Baseline 2 — temporal smoothing
Baseline 3 — simple cross-bus corroboration
Baseline 4 — classical truth discovery
Candidate — ResearchFusionStrategy
```

## Evaluation dimensions

```text
state estimation accuracy
false confirmation
missed confirmation
repair verification error
false absence
reappearance detection
calibration
robustness under correlated evidence
```

No research conclusion is written into the product claims before experiments are complete.

---

# 63. Advanced Research Extensions

Only after baseline measurement:

```text
uncertainty calibration
conformal prediction
active sensing
coverage-aware inference
probabilistic cross-camera continuity
learned maintenance prioritization
```

These are research extensions, not prerequisites for the core system.

---

# 64. Decision Register

Maintain `docs/decision-log.md`.

Required entries include:

```text
exact road-defect model
exact detector model/version
exact tracker
exact OCR model
GIS library
map-match acceptance threshold
OBSERVED → CANDIDATE threshold
CANDIDATE → CONFIRMED threshold
corroboration window
maintenance priority formula/weights
negative_evidence_strength formula
negative_evidence_score aggregation
verification coverage field mapping
sensor-health verification rule
freshness/decay function
reappearance association rule
evidence retention
camera calibration approach
OpenAPI client generator
speed source beyond GPS
TTC policy
LLM provider
RAG/vector store
edge hardware target
observability stack
backend hosting
PostGIS hosting
object storage
MQTT location
TLS termination
secret management
backup strategy
CORS policy
production environment variables
```

Each accepted decision should have:

```text
Decision ID
Date
Owner
Context
Decision
Alternatives considered
Reason
Impact
Tests affected
```

---

# 65. Source/Requirement Traceability

The final repository must contain:

```text
docs/traceability.md
```

with the chain:

```text
Source requirement/capability
        ↓
Backend/Edge contract
        ↓
Implementation module
        ↓
API/event/data entity
        ↓
Acceptance scenario
        ↓
Test
        ↓
Demo beat (if applicable)
```

Internal R01–R29 identifiers from the current v3.1 Team Master Specification must be clearly marked as internal traceability IDs.

If another internal document uses 31 references, do not create duplicate requirements. Reconcile whether those are additional internal sub-requirements, acceptance tests, or a different grouping, then record the relationship in `docs/traceability.md`.

---

# 66. GIS Traceability

The supplied source requires 20 GIS layers for the full build.

Before public demo/PPT claims:

```text
source GIS matrix
→ canonical layer list
→ Backend endpoint/read model
→ Frontend renderer
→ test data
→ rendered acceptance test
```

No layer may be claimed as complete merely because a navigation tab exists.

---

# 67. Evidence Lineage Contract

A judge or developer should be able to trace:

```text
RoadTwin state
   ↓
subject/episode
   ↓
Evidence records
   ↓
Observation / Negative Evidence
   ↓
Opportunity
   ↓
Sensing Pass
   ↓
Bus / camera / device
   ↓
Model version
   ↓
raw evidence reference
```

The chain must survive retries, state transitions, repair, and reappearance.

---

# 68. Data Retention and Sensitive Evidence

Retention policy is `DECISION_REQUIRED`.

Separate:

```text
structured metadata
large media
sensitive ANPR artifacts
operational logs
```

Object storage is for large evidence/media.
PostgreSQL/PostGIS stores searchable structured metadata and relationships.

---

# 69. Acceptance Gates

## Gate 0 — Foundation

```text
repo
Docker
PostGIS
Redis
MinIO
MQTT
```

## Gate 1 — Contract

```text
Observation
Opportunity
Event
Evidence
API
DB
RoadTwin
```

## Gate 2 — First E2E

```text
simulated bus
→ Backend
→ RoadTwin
→ Frontend
```

## Gate 3 — Real AI

```text
video
→ detector
→ event
→ Backend
→ GIS
```

## Gate 4 — Cooperative Evidence

```text
BUS-001 + BUS-002
→ CONFIRMED
```

## Gate 5 — Closed Loop

```text
repair
→ verification
→ negative evidence
→ VERIFIED_REPAIRED
→ REAPPEARED
```

## Gate 6 — PS Breadth

```text
traffic
infrastructure
VRU
incidents
coverage
alerts
GIS
```

## Gate 7 — Advanced

```text
ANPR
Copilot
RAG
advanced analytics
```

## Gate 8 — Hardening

```text
tests
security
observability
performance
failure handling
```

## Gate 9 — Demo Lock

```text
repeatable seed/reset/run/verify
stable deployment
no manual DB edits
rehearsed lifecycle
PPT claims verified

```
## Note :

'''text
At any point, implementation must maintain one working end-to-end path.

The team may not expand breadth if the current critical path is broken.

Critical path:

Edge
→ Observation
→ Opportunity
→ Event
→ Transport
→ Backend
→ Map Match
→ Evidence
→ Fusion
→ RoadTwin
→ API
→ GIS

'''
---

# 70. Module Definition of Done

A module is complete only when:

```text
implementation
→ input validation
→ correct output contract
→ integration
→ persistence where applicable
→ API/Event contract
→ failure handling
→ tests
→ evaluation scenario
→ demo scenario where applicable
→ observability
```

## Example — road-defect path

```text
model
→ detector_confidence
→ tracking/temporal grouping
→ observation quality
→ Observation Opportunity
→ Evidence
→ Canonical Event
→ Edge transport
→ Backend ingestion
→ authoritative map match
→ dedup
→ fusion
→ RoadTwin
→ GIS
→ tests
```

---

# 71. Final Technical Honesty Rules

Never claim:

```text
government deployment
real government-bus CCTV access
live fleet telemetry
measured performance without benchmark
official authority integration without integration evidence
validated cost savings
validated novelty
production hardware deployment from a laptop-only prototype
```

Correct phrasing:

```text
prototype
simulated fleet
simulated GNSS
recorded-video evaluation
proposed architecture
research extension
benchmark pending
```

---

# 72. Final Implementation Checklist

Before calling UrbanSense implementation complete:

```text
[ ] repository has no runtime duplicates
[ ] Docker infrastructure is reproducible
[ ] contracts are versioned
[ ] OpenAPI is generated from Backend schemas
[ ] Frontend client synchronized
[ ] HAL providers work
[ ] camera calibration is represented
[ ] AI Observation works
[ ] Opportunity evaluator works
[ ] Canonical Event works
[ ] transport retry/idempotency works
[ ] Backend map matching works
[ ] deduplication works
[ ] Evidence persists
[ ] FusionEngine is singular
[ ] MVP fusion works
[ ] negative evidence works
[ ] RoadTwin state machine is singular
[ ] freshness is queryable
[ ] AuthorityAction is auditable
[ ] maintenance workflow works
[ ] repair verification works
[ ] reappearance episode works
[ ] traffic analytics works
[ ] infrastructure comparison works
[ ] VRU/safety path works
[ ] incident path works
[ ] ANPR RBAC works
[ ] coverage works
[ ] alerts work
[ ] GIS scope is reconciled
[ ] Copilot is grounded in Backend tools
[ ] RAG is restricted to approved knowledge domains
[ ] evaluation scenarios pass
[ ] failure injection tests pass
[ ] observability is usable
[ ] security checks pass
[ ] measured benchmarks exist
[ ] deployment is reproducible
[ ] demo reset/seed/run/verify works
[ ] final PPT claims have evidence
```

---

# 73. Final Definition of UrbanSense

UrbanSense is complete when a real or simulated bus observation:

```text
is captured at the Edge
        ↓
is processed by perception/tracking
        ↓
is evaluated for observation quality and opportunity
        ↓
becomes a canonical event
        ↓
reaches the Backend reliably
        ↓
is spatially associated and deduplicated
        ↓
becomes auditable Evidence
        ↓
is fused with independent evidence
        ↓
updates an authoritative RoadTwin/defect lifecycle
        ↓
is visible through the real API/GIS
        ↓
can trigger an auditable authority action
        ↓
can be re-observed under valid sensing conditions
        ↓
can support repair verification through negative evidence
        ↓
can preserve history and detect reappearance
```

## Final architecture statement

> **UrbanSense = Edge Perception → Opportunity-Aware Evidence → Backend Fusion → RoadTwin → Authority Action → Fleet Verification → Historical Reappearance.**

The system is designed so that the detector is only the beginning of the intelligence chain; the core engineering contribution is converting uncertain mobile observations into traceable, spatially grounded, lifecycle-aware urban evidence.

---

# 74. Final Rule for Coding Assistants

When a coding assistant is uncertain, it must stop at the architecture boundary and report:

```text
WHAT I KNOW
WHAT THE CONTRACT SAYS
WHAT IS UNDECIDED
WHAT FILES ARE AFFECTED
WHAT TEST WOULD RESOLVE IT
```

It must **not guess**.

That rule is part of the UrbanSense architecture.

---

# Appendix A — Quick Reference

```text
Edge
  HAL
  Perception
  Tracking
  Quality
  Sensor Health
  Opportunity
  Event
  Transport

Backend
  Ingestion
  Map Matching
  Dedup
  Evidence
  Fusion
  Negative Evidence
  RoadTwin
  Urban Memory
  Maintenance
  Analytics
  Alerts
  RBAC

Frontend
  GIS
  Dashboards
  Authority UI
  Copilot UI

Core lifecycle
  OBSERVED
  → CANDIDATE
  → CONFIRMED
  → MAINTENANCE_PENDING
  → REPAIR_REPORTED
  → VERIFICATION_PENDING
  → VERIFIED_REPAIRED
  → REAPPEARED

Core formulas
  positive evidence weight
  = detector_confidence × observation_quality × gps_quality

  aggregate confidence
  = 1 − Π(1 − evidence_weight_i)

Negative evidence
  = valid sensing opportunity + adequate conditions + no qualifying detection

Primary demo
  BUS-001 → Candidate
  BUS-002 → Confirmed
  Authority → Repair
  Future buses → Verified Repaired
  Later positive → Reappeared
```

---

**END OF R4 FINAL MASTER IMPLEMENTATION PLAN**

# UrbanSense AI — Decision Log

> Unresolved architectural decisions are recorded here.
> A guess is never silently substituted for a DECISION_REQUIRED item.

---

## DECISION-001: Opportunity Score Weighting

**Status:** OPEN  
**Milestone:** 1 (prototype uses simple mean)  
**Question:** What is the production weighting formula for `opportunity_score` from individual sub-scores (visibility, illumination, blur, etc.)?  
**Impact:** Determines which sensing windows are VALID vs INVALID.  
**Owner:** Domain expert + sensor engineering team.  
**Prototype behaviour:** Simple arithmetic mean of all score dimensions.

---

## DECISION-002: Map-Match Acceptance Threshold

**Status:** OPEN  
**Milestone:** 1 (prototype uses 100m radius)  
**Question:** What is the minimum map-match confidence / maximum distance to accept a MATCHED result?  
**Impact:** Determines whether events contribute to a RoadTwin or are marked UNMATCHED.  
**Owner:** GIS/mapping team.  
**Prototype behaviour:** Linear confidence decay over 100m radius.

---

## DECISION-003: RoadTwin Confidence Aggregation

**Status:** OPEN  
**Milestone:** 1 (prototype uses running average of detector_confidence)  
**Question:** What is the production formula for aggregating `aggregate_confidence` from multiple observations across independent buses?  
**Impact:** Determines when a segment transitions from OBSERVED → CANDIDATE → CONFIRMED.  
**Owner:** Sensor fusion team.  
**Prototype behaviour:** Simple running arithmetic mean.

---

## DECISION-004: OBSERVED → CANDIDATE Threshold

**Status:** OPEN  
**Milestone:** 1 (not implemented; only OBSERVED state in M1)  
**Question:** What minimum independent bus count and confidence level is required to transition OBSERVED → CANDIDATE?  
**Impact:** Core RoadTwin lifecycle.  
**Owner:** Domain expert + product team.

---

## DECISION-005: MQTT Auth in Production

**Status:** OPEN  
**Milestone:** 0 (prototype uses `allow_anonymous true`)  
**Question:** What authentication scheme (password file, TLS client certs, JWT) is used for MQTT in production?  
**Impact:** Security of Edge → Backend event transport.  
**Owner:** Security team.

---

## DECISION-006: Frontend Map Tile Provider

**Status:** OPEN  
**Milestone:** 1 (prototype uses OpenStreetMap)  
**Question:** Which map tile provider is approved for production? OSM, MapLibre with self-hosted tiles, or commercial provider?  
**Impact:** Licensing, offline capability, and map quality.  
**Owner:** Product + legal team.

---

## DECISION-007: Production Authentication / RBAC

**Status:** OPEN  
**Milestone:** 1 (no auth implemented)  
**Question:** What identity provider and RBAC scheme is used? JWT with internal IdP, OAuth2, Keycloak?  
**Impact:** API security for all Milestone 2+ endpoints.  
**Owner:** Security + product team.

---

## DECISION-008: Pothole Detection Model Architecture

**Status:** PROPOSED  
**Milestone:** 2  
**Question:** Which deep learning model architecture (YOLOv8-nano, RT-DETR, custom MobileNet-SSD) should be deployed to Edge devices for road surface distress detection?  
**Impact:** Edge compute consumption, latency, and detection recall on embedded hardware.  
**Owner:** CV / Perception team.  
**Prototype behaviour:** Baseline morphological gradient depression detector (`BaselinePotholeDetector`) running behind the replaceable `BaseDetector` interface.

---

## DECISION-009: Vehicle Detection Model Architecture

**Status:** PROPOSED  
**Milestone:** 2  
**Question:** Which multi-class object detection model should be selected for vehicle category identification (car, bus, truck, motorcycle, bicycle)?  
**Impact:** Detection precision across varying weather/lighting, frame throughput.  
**Owner:** CV / Perception team.  
**Prototype behaviour:** Baseline roadway morphology and aspect-ratio classifier (`BaselineVehicleDetector`) running behind `BaseDetector`.

---

## DECISION-010: Object Tracking Engine Selection

**Status:** PROPOSED  
**Milestone:** 2  
**Question:** Which tracking algorithm (ByteTrack, BoT-SORT, DeepSORT) should be integrated for high-speed same-camera object tracking?  
**Impact:** Track ID persistence under occlusion; computational overhead.  
**Owner:** CV / Perception team.  
**Prototype behaviour:** Same-camera temporal IoU and centroid association tracker (`SameCameraTracker`) behind `BaseTracker`.

---

## DECISION-011: Physical Camera Calibration & Extrinsics

**Status:** PROTOTYPE / ASSUMED  
**Milestone:** 2  
**Question:** What are the exact physical mounting heights, lens distortion coefficients, and camera angles across different transit bus chassis models?  
**Impact:** Accuracy of inverse perspective mapping and real-world defect sizing in later milestones.  
**Owner:** Hardware deployment team.  
**Prototype behaviour:** Standardized assumed transit front mount: height 2.5m, pitch 0.0°, H-FOV 85.0°, V-FOV 54.0°.

---

## DECISION-012: Evidence Media Persistence Strategy

**Status:** OPEN  
**Milestone:** 2  
**Question:** Should edge evidence crops be buffered on device local storage and synced lazily, or uploaded directly to MinIO / S3 on event generation?  
**Impact:** Cellular bandwidth costs, upload latency, edge storage budget.  
**Owner:** Systems architecture & infrastructure team.  
**Prototype behaviour:** Stored in local evidence directory (`data/evidence/`) with stable `evidence://` URIs recorded in canonical event metadata.

---

## DECISION-013: Heuristic Detector Confidence Calibration vs Probability Scoring

**Status:** DOCUMENTED / OPEN  
**Milestone:** 2.1  
**Question:** How should raw detector confidence values from computer vision models (classical heuristic contour scores in prototype, Softmax probabilities in deep models) be calibrated into formal statistical likelihoods for evidence fusion?  
**Impact:** Downstream sensor fusion in Milestone 3 must not mistake uncalibrated heuristics or raw Softmax overconfidence for calibrated truth probabilities.  
**Owner:** AI/Perception team & Sensor Fusion team.  
**Hardened Semantic Rule (M2.1):**  
In Milestone 2 / 2.1, `detector_confidence` represents an **uncalibrated prototype detector score** derived from geometric contour features (aspect ratio, circularity, solidity). It is strictly NOT a Bayesian probability, truth confidence, or calibrated evidence weight. No downstream module in M2/M2.1 treats this score as a calibrated probability.

---

## DECISION-014: Opportunity Window Duration and Multi-Frame Aggregation Policy

**Status:** PROTOTYPE / CONFIGURABLE  
**Milestone:** 2.1  
**Question:** What is the authoritative sensing window duration for grouping consecutive camera frames under an `ObservationOpportunity`, and how should multi-frame quality signals within the window be aggregated?  
**Impact:** Frame-to-opportunity cardinality, edge event generation rate, database record volume, and opportunity validity stability.  
**Owner:** Edge systems architecture team.  
**Hardened Semantic Rule (M2.1):**  
An `ObservationOpportunity` is a meaningful sensing window (default 1.0 second prototype window), NOT a 1:1 per-frame parent object. Multiple consecutive frames and detections within that window reference the same authoritative `opportunity_id`.  
**Snapshot Semantics (Option A):**  
The active Opportunity's quality and validity score fields are a **snapshot** of conditions evaluated at the start of the window (first frame). Later frames within that 1.0s window reuse the existing window-start Opportunity context without mutating its scores. Frame-level optical variations continue to flow directly into each result's `quality_signals` and the crop's `observation_quality`. Full multi-frame temporal window score aggregation remains a future design consideration.

---

## DECISION-015: Remote Object Storage Synchronization (MinIO / S3)

**Status:** OPEN  
**Milestone:** 2.1  
**Question:** At what frequency and protocol should edge evidence artifacts stored at `data/evidence/` with `evidence://local/...` references be synced to centralized MinIO/S3 object storage?  
**Impact:** Edge retention policy, network upload queue management, and frontend media viewing latency.  
**Owner:** Cloud Infrastructure team.  
**Hardened Prototype Semantics (M2.1):**  
Milestone 2.1 uses a local filesystem evidence store (`data/evidence/`) generating local URIs (`evidence://local/...`). Lineage is verified end-to-end (Observation → Event → Backend payload). Remote object synchronization to MinIO/S3 remains an open infrastructure integration.

---

## DECISION-016: Alembic Migration Logical Reference Alignment (No Foreign Keys on Logical Cross-References)

**Status:** ADOPTED / RESOLVED  
**Milestone:** 2.1  
**Question:** Should the `events` table enforce hard SQL foreign-key constraints on `observation_id` and `opportunity_id`?  
**Impact:** Order of ingestion, network decoupling, schema migrations.  
**Owner:** Backend Architecture Team.  
**Resolution:**  
Removed foreign-key constraints on `events.observation_id` and `events.opportunity_id` in migration `m1_001_initial.py` to match the ORM model definition in `backend/app/models/event.py`.  
Rationale:
1. R4 §33.1 defines no edge observation ingestion REST endpoint; raw edge observations stay on the edge device and are not stored as rows in a backend `observations` table during routine event delivery.
2. Under R4 §14.3, opportunities and events travel via independent network channels and may arrive out of order (e.g. event before opportunity). Enforcing a hard database foreign key on `events.opportunity_id` would reject legitimate edge events arriving before their opportunity record.
3. Cross-references remain tracked as logical reference strings and indexed for fast lookup without blocking independent ingestion.

---

## DECISION-017: Deterministic ID Namespace Coexistence

**Status:** DOCUMENTED  
**Milestone:** 2.1  
**Question:** The M1 simulator and M2 video perception pipeline both generate deterministic IDs using the sequence templates `EVT-000001`, `OPP-BUS-001-000001`, etc. Should they have segregated prefixes?  
**Impact:** Potential event ID collisions if both M1 demo and M2 demo are run deterministically against the same backend without resetting the database.  
**Owner:** QA / AI Systems team.  
**Prototype Behaviour:**  
Under R4 §14.3, backend event ingestion is strictly idempotent. When an event with `EVT-000001` is received again, the backend recognizes it and returns HTTP 200 with `status="duplicate"` without creating a duplicate record or corrupting state. For production test suites requiring fresh records, non-deterministic UUID generation or timestamp-based sensing pass prefixes are supported via the pipeline's `deterministic=False` argument.

---

## DECISION-018: GNSS Accuracy Semantic Guard — GPS Quality vs FOV Validity Separation

**Status:** ADOPTED / PROTOTYPE GUARD  
**Milestone:** 2.1 (refined in M2.1 micro-fix)  
**Question:** How should the Opportunity Evaluator handle a GNSS sensor reading where `fix_quality > 0` but `accuracy_m is None`? Should GPS quality failure propagate to `fov_valid`?  
**Impact:** Geo-spatial reliability of opportunities; semantic correctness of multi-dimensional quality scoring.  
**Owner:** AI Systems & Edge Navigation Team.  
**Hardened Semantic Rule (M2.1 micro-fix):**  
GPS quality and FOV validity are **independent sensing dimensions** and must not be conflated:
- When `accuracy_m is None`: `gps_quality_score = 0.0`, Opportunity is `INVALID`, reason `"GNSS accuracy unavailable"` is appended.
- **`fov_valid` is NOT set to `False` due to GPS accuracy unavailability alone.** `fov_valid` reflects camera field-of-view position assessment — a separate physical measurement from GPS accuracy reporting.
- `fov_valid` is set to `False` only when: GNSS sensor data is entirely absent (`gnss is None`), or `fix_quality <= 0` (no GPS fix at all, meaning location itself is unknown).
- A real fix with unreported accuracy means position is known but quality is uncertifiable — the Opportunity is INVALID for evidence-weight purposes, but the FOV assessment stands.

---

## DECISION-019: Performance Instrumentation Discrepancy Reporting

**Status:** ADOPTED  
**Milestone:** 2.1 (refined in M2.1 micro-fix)  
**Question:** How should perception pipeline performance be accounted for, and what happens when measured component times sum to more than the measured total?  
**Impact:** Performance transparency, benchmark credibility, profiling precision.  
**Owner:** QA & AI Systems Architecture Team.  
**Hardened Semantic Rule (M2.1 micro-fix):**  
1. All component stages are measured using monotonic high-resolution wall-clock timers (`time.perf_counter()`): acquisition, quality eval, opportunity eval, inference, tracking, evidence/event building.
2. Total execution time (`total_time_seconds`) is the true end-to-end wall-clock duration of the run.
3. Average end-to-end latency per frame: `(total_time_seconds * 1000.0) / frames_processed`.
4. Processed throughput (`average_processed_fps`): `1000.0 / avg_e2e_ms` — strictly distinct from source capture FPS.
5. Residual overhead is **explicitly reported** as `discrepancy_ms = total_ms - sum(components)` (can be positive or negative):
   - Positive: expected inter-step overhead (Python loop, scheduling). Normal operating condition.
   - Negative (magnitude > 1 ms): indicates timer overlap or measurement error. A `WARNING` log is emitted describing the component sum, measured total, and magnitude of discrepancy. This surfaces instrumentation bugs rather than silently concealing them with `max(0, ...)`.
6. The pipeline does NOT guarantee `sum(components) + residual == total` when timers overlap. The discrepancy IS the signal.

---

## DECISION-020: Negative Evidence Gating and Strength Formulation

**Status:** PROTOTYPE ADOPTED / DECISION_REQUIRED FOR PRODUCTION CALIBRATION  
**Milestone:** 4  
**Question:** How should negative sensing evidence (absence of detection during a valid sensing opportunity) be gated, formulated, and weighted to verify road defect repair?  
**Impact:** Prevents poor camera passes, missing GPS fixes, or obstructed sensors from being falsely certified as repairs.  
**Owner:** Sensor Fusion & QA Engineering Team.  
**Hardened Semantic Rules (M4):**  
1. **Strict Opportunity Gating:**  
   - `VALID` opportunity + no defect observation → Candidate negative evidence (recorded with `polarity='NEGATIVE'`, `detector_confidence=None`).  
   - `INVALID` opportunity + no observation → **INCONCLUSIVE** (strictly rejected; zero evidence recorded).  
   - A poor-quality pass is NOT evidence of repair. A missing camera frame is NOT evidence of repair. A missing GPS fix is NOT evidence of repair.  
2. **Strength Formulation (FusionEngine exclusive):**  
   - `negative_evidence_strength = opportunity_score * gps_quality`.  
   - Computed exclusively inside `backend/app/fusion/engine.py`.  
   - `evidence_weight = 0.0` (does not dilute or contaminate positive Noisy-OR formula).  
3. **Verification Transition Threshold:**  
   - Prototype threshold: `negative_evidence_strength >= 0.5` triggers `VERIFICATION_PENDING → VERIFIED_REPAIRED`.  
   - Explicitly marked `PROTOTYPE / UNCALIBRATED`: production deployment requires formal statistical field calibration.

---

## DECISION-021: Independent Verification Guarantee — Contractor Report Non-Equivalence

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** 4  
**Question:** Does an authority dispatch or contractor self-report of completion certify defect repair?  
**Impact:** Integrity of the UrbanSense closed-loop maintenance system; prevention of unverified municipal ticket closure.  
**Owner:** Systems Architecture Team.  
**Hardened Invariant (M4):**  
1. Submitting `POST /api/v1/maintenance/report-completion` transitions RoadTwin from `MAINTENANCE_PENDING` to `VERIFICATION_PENDING`.  
2. It **NEVER** transitions directly to `VERIFIED_REPAIRED`.  
3. A RoadTwin reaches `VERIFIED_REPAIRED` only when subsequent, independent negative sensing evidence meets the verification threshold.  
4. Authority action records are maintained append-only in `authority_actions` with full audit trace (`actor_role`, `actor_id`, `prior_roadtwin_state`, `resulting_roadtwin_state`, `trace_id`).

---

## DECISION-022: Defect Recurrence Episode Boundary & Evidence Isolation

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** 4  
**Question:** When a new positive observation occurs on a previously `VERIFIED_REPAIRED` road segment, how is recurrence handled without leaking prior-episode evidence into the new lifecycle?  
**Impact:** Avoids instantaneous false re-confirmation using historical observations from before the repair was executed.  
**Owner:** Backend & Sensor Fusion Architecture Team.  
**Hardened Invariant (M4):**  
1. A new positive defect detection on a `VERIFIED_REPAIRED` segment transitions state to `REAPPEARED`.  
2. A new `active_episode_id` is generated (UUID), and the prior episode ID is linked to `previous_episode_id`.  
3. `positive_evidence_count` resets to 1, `negative_evidence_count` resets to 0, and `first_seen_at` is set to the recurrence event timestamp.  
4. `FusionEngine` scopes evidence collection and Noisy-OR aggregation to `timestamp >= first_seen_at` for the active episode, strictly isolating pre-repair historical evidence.  
5. A `REAPPEARED` defect is eligible for immediate maintenance re-dispatch (`REAPPEARED → MAINTENANCE_PENDING`).

---

## DECISION-023: Historical Evidence Lineage Persistence (Spatial/Temporal Grounding)

**Status:** ADOPTED / RESOLVED  
**Milestone:** M3/M4 Hardening  
**Question:** Should historical evidence reconstruction rely on synthetic coordinates (`lat=0.0, lon=0.0`) and null pass IDs, or persist full spatio-temporal provenance?  
**Impact:** Prevents 8,000 km Gulf-of-Guinea coordinate anomalies when evaluating same-bus spatial correlation across passes.  
**Owner:** Backend Architecture & Fusion Team.  
**Resolution:**  
1. Added `latitude`, `longitude`, `sensing_pass_id`, and `trace_id` columns to `EvidenceModel` (migration `m4_002_evidence_lineage`).  
2. Positive and negative evidence construction in `FusionEngine` strictly populates these fields.  
3. `_load_existing_contributions()` reconstructs candidate history with genuine persisted coordinates and pass identifiers, enabling spatial proximity evaluation (`_SPATIAL_INDEPENDENCE_RADIUS_M = 50.0m`).  
4. `IndependenceInput` tolerates `Optional[float]` coordinates gracefully, falling back to segment-level temporal correlation when physical coordinates are absent.

---

## DECISION-024: Negative Evidence Independence Classification & Verification Gating

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M4 Hardening  
**Question:** Should negative evidence passes automatically receive `independence_class=INDEPENDENT`, or undergo multi-pass independence classification?  
**Impact:** Prevents rapid consecutive passes from the same vehicle or camera pass from being miscounted as independent negative verifications.  
**Owner:** Sensor Fusion & Validation Engineering.  
**Resolution:**  
1. Candidate negative passes undergo formal independence classification via `classify_independence()`.  
2. Repeated frames from the same vehicle within 300s / 50m are classified as `CORRELATED` or `DUPLICATE`.  
3. Transition guard: Only negative evidence classified as `INDEPENDENT` with `negative_evidence_strength >= 0.5` can trigger `VERIFICATION_PENDING → VERIFIED_REPAIRED`. Correlated or duplicate negative passes are recorded for telemetry but cannot certify repair.

---

## DECISION-025: RoadTwin State Machine Ownership Enforcement

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M4 Hardening  
**Question:** Where in the system is `RoadTwinStateModel.current_state` permitted to be mutated?  
**Impact:** Eliminates split-brain state machine logic and unauthorized mutations across subsystem boundaries.  
**Owner:** Backend Systems Architecture.  
**Resolution:**  
1. Direct assignment `rt.current_state = new_state` outside `backend/app/roadtwin/engine.py` is strictly prohibited.  
2. `FusionEngine` delegates evidence-driven state transitions to `apply_positive_evidence_transition(rt, new_state, reason)` in `roadtwin/engine.py`.  
3. Negative evidence transitions are handled exclusively through `apply_negative_evidence_transition()`.  
4. Authority maintenance transitions are handled exclusively through `apply_maintenance_action()`.

---

## DECISION-026: REPAIR_REPORTED Lifecycle Semantics & Authoritative Episode Lineage

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M4 Hardening  
**Question:** How are contractor completion reports represented in the lifecycle, and what is the authoritative source of truth for recurrence tracking?  
**Impact:** Faithful compliance with Master Plan Section 13/20/22; avoidance of redundant recurrence counters.  
**Owner:** Principal AI Systems Architect.  
**Resolution:**  
1. In accordance with Master Plan Section 13, contractor self-reports trigger `REPAIR_REPORTED`, which immediately and automatically advances to `VERIFICATION_PENDING` to initiate prioritized re-observation. Both explicit `START_VERIFICATION` and atomic auto-transition paths are supported.  
2. Recurrence is authoritatively proven and tracked via episode lineage (`active_episode_id`, `previous_episode_id`), not by an auxiliary integer count. A non-null `previous_episode_id` formally denotes a recurrent defect episode.

---

## DECISION-027: Traffic Window Duration and Deduplicated Vehicle Count Semantics

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M5 Vertical Slice 1  
**Question:** How should continuous vehicle sightings be aggregated into road segment traffic observations without double-counting multi-frame sightings of the same vehicle?  
**Impact:** Prevents 30 FPS video detections of a single stationary or slow vehicle from artificially inflating segment traffic volume into thousands of phantom vehicles.  
**Owner:** Traffic Intelligence & Perception Engineering.  
**Resolution:**  
1. Time-bucket aggregation utilizes a fixed UTC rolling window duration (`traffic_window_duration_seconds = 60s`), aligned deterministically to epoch second boundaries (`floor(epoch / 60) * 60`).  
2. Within any single `(road_segment_id, window_start, window_end)` bucket, vehicle observations are deduplicated by `track_id`. A single physical vehicle (`track_id`) contributes at most one unit (`deduped_vehicle_count += 1`) to the window volume.  
3. Sightings lacking a `track_id` default to conservative single-sighting increments. The database enforces uniqueness on `(road_segment_id, window_start)`.

---

## DECISION-028: Speed Derivation Strategy (Approach A — GPS Displacement)

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M5 Vertical Slice 1  
**Question:** How should vehicle speed be derived without calibrated optical extrinsic cameras?  
**Impact:** Optical pixel-flow velocity without extrinsic road calibration and homography is physically invalid and prohibited.  
**Owner:** AI Systems Architect & Sensor Validation.  
**Resolution:**  
1. Optical flow pixel motion is explicitly banned from being converted directly to physical speed (km/h) without extrinsic camera calibration.  
2. Approach A is adopted: vehicle fleet speed is derived from consecutive physical GNSS/GPS coordinate displacement over elapsed time ($\Delta d / \Delta t$) via the Haversine formula, clamped to realistic operational speed limits (0–160 km/h).  
3. Where explicit CAN-bus or vehicle telemetry speed (`telemetry_speed_kmh`) is supplied in the ingestion event, it takes precedence. Missing or uncomputable speeds remain `NULL` / `UNKNOWN` rather than fabricated values.

---

## DECISION-029: Density and Flow Prototype Formulations

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M5 Vertical Slice 1  
**Question:** How are road segment traffic density (veh/km) and hourly flow rate (veh/h) derived during the prototype stage?  
**Impact:** Provides normalized traffic indicators across segments of differing lengths for congestion and bottleneck determination.  
**Owner:** Data & Analytics Engineering.  
**Resolution:**  
1. Segment density is calculated as $\text{density} = (\text{deduped\_vehicle\_count} / \text{segment\_length\_km})$, where `segment_length_km` defaults to `traffic_default_segment_length_m / 1000` (0.5 km) if not explicitly provisioned in the road network GIS layer.  
2. Equivalent hourly flow is computed by scaling window volume to an hourly rate: $\text{flow\_rate\_vph} = \text{deduped\_vehicle\_count} \times (3600 / \text{window\_duration\_seconds})$.  
3. Congestion classification evaluates density thresholds (`FREE_FLOW` < 8 veh/km, `MODERATE` 8–15 veh/km, `HEAVY` > 15 veh/km, and `STOP_AND_GO` when heavy with speed < 10 km/h), documented as prototype heuristic thresholds subject to calibration in M6.

---

## DECISION-030: Rolling 3-Window Bottleneck Persistence Rule

**Status:** ADOPTED ARCHITECTURAL INVARIANT  
**Milestone:** M5 Vertical Slice 1  
**Question:** What constitutes a persistent traffic bottleneck versus a transient traffic stoppage or red-light queue?  
**Impact:** Prevents momentary transit bus stops or traffic signal cycles from triggering false municipal bottleneck alerts.  
**Owner:** Principal AI Systems Architect.  
**Resolution:**  
1. A bottleneck is confirmed only when high segment density ($\ge 15.0$ veh/km) AND low fleet speed ($\le 20.0$ km/h) persist across 3 consecutive aggregation windows ($T-2, T-1, T$).  
2. A single window or 2 consecutive windows are recorded as `MONITORING` and do not activate an active bottleneck. Any intervening window failing the condition immediately resets persistence.  
3. Every bottleneck record carries complete explainability metadata (`consecutive_windows_count`, `trigger_density_veh_km`, `trigger_avg_speed_kmh`, and `persistence_history`), enabling transparent municipal auditability in the frontend GIS layer.


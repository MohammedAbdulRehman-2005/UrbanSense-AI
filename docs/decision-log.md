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


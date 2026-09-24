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

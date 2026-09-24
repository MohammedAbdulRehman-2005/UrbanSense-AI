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

# UrbanSense AI — Milestone 1 Documentation

> **PROTOTYPE / SIMULATED — Milestone 1 foundation only.**
> This is not a production deployment. No real fleet data. No real sensor hardware.

---

## Overview

Milestone 1 delivers the **first end-to-end UrbanSense vertical slice**:

```
SIMULATED OBSERVATION (BUS-001)
  → Opportunity Evaluator
  → Canonical Event Builder
  → POST /api/v1/events (FastAPI backend)
  → Database (PostgreSQL/PostGIS)
  → RoadTwin Engine (OBSERVED state)
  → GET /api/v1/roadtwin (API read model)
  → React frontend map (Leaflet)
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop (for infrastructure — PostgreSQL, Redis, MinIO, MQTT)

---

## 1. Start Infrastructure

```bash
# From project root
docker compose up -d postgres redis minio mosquitto
```

Wait for health checks to pass:
```bash
docker compose ps
```

---

## 2. Run Database Migration

```bash
cd backend
alembic upgrade head
```

This will:
- Enable PostGIS extension
- Create all Milestone 1 tables
- Seed SEG-001 and SEG-002 demo road segments

---

## 3. Start Backend

```bash
# From project root
uvicorn backend.app.main:app --reload
```

Backend will be at: http://localhost:8000

Verify: http://localhost:8000/health  
OpenAPI docs: http://localhost:8000/docs

---

## 4. Run End-to-End Demo

```bash
# Requires backend running
python scripts/run_m1_demo.py
```

This will:
1. Generate a simulated sensing pass (BUS-001 on SEG-001)
2. POST the Opportunity to `/api/v1/opportunities`
3. POST the Canonical Event to `/api/v1/events`
4. Verify idempotency (duplicate rejection)
5. GET the RoadTwin state
6. Print the full traceability chain

---

## 5. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend will be at: http://localhost:5173

The map shows RoadTwin states for all monitored road segments.
Data is read via API — no direct DB access from frontend.

---

## 6. Regenerate Frontend API Client

When the backend OpenAPI schema changes:

```bash
cd frontend
npm run generate-client
```

This regenerates `src/client/schema.d.ts` from the live backend.
Do NOT manually duplicate Pydantic schemas in TypeScript.

---

## 7. Run Tests

```bash
# Unit tests only (no DB or backend required):
pytest tests/test_m1.py -k "not integration" -v

# All tests (requires backend running):
pytest tests/test_m1.py -v
```

---

## 8. Environment Variables

See `.env.example` for all configurable variables.

Key variables for Milestone 1:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgresql://... | PostgreSQL connection |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection |
| `MINIO_ENDPOINT` | localhost:9000 | MinIO object storage |
| `MQTT_BROKER_HOST` | localhost | Mosquitto MQTT |
| `API_PORT` | 8000 | Backend port |
| `BACKEND_URL` | http://localhost:8000 | Used by demo script |

---

## 9. API Endpoints (Milestone 1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Backend health check |
| POST | `/api/v1/events` | Ingest Canonical Event (idempotent) |
| POST | `/api/v1/opportunities` | Ingest Observation Opportunity (idempotent) |
| GET | `/api/v1/roadtwin` | List all RoadTwin states |
| GET | `/api/v1/roadtwin/{id}` | Get specific RoadTwin state |
| GET | `/docs` | OpenAPI interactive docs |
| GET | `/openapi.json` | OpenAPI schema (source of truth for frontend) |

---

## 10. Architecture Ownership

| Component | Owner | Note |
|-----------|-------|------|
| `detector_confidence` | Edge | Raw model output only |
| `observation_quality` | Edge | From Opportunity scores |
| `edge_road_segment_hint` | Edge | **ADVISORY ONLY** |
| `matched_road_segment_id` | **Backend** | Authoritative |
| `map_match_confidence` | **Backend** | Authoritative |
| `aggregate_confidence` | **Backend** | RoadTwin-level fusion |
| RoadTwin state transitions | **Backend** | Never in frontend |

---

## 11. Known Prototype Limitations

- Map matching uses a simple distance-based lookup, not a real routing engine. **DECISION_REQUIRED** for production.
- Opportunity scores use simple mean weighting. **DECISION_REQUIRED** for production.
- `aggregate_confidence` uses simple running average. **DECISION_REQUIRED** for production.
- No authentication or RBAC in Milestone 1. **DECISION_REQUIRED** for production.
- Frontend uses OpenStreetMap tiles — verify licensing for production.
- No Negative Evidence implemented (future milestone).
- No Evidence Fusion implemented (future milestone).
- Full RoadTwin 8-state lifecycle not implemented (future milestone).
- MQTT transport from Edge to Backend not wired in M1 (uses HTTP POST directly in demo).

---

## 12. Decision Log

See `docs/decision-log.md`.

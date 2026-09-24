# UrbanSense AI

> **SIH Problem Statement 26124** | Road condition monitoring using AI + IoT

**Status: Milestone 1 — First End-to-End Vertical Slice (PROTOTYPE / SIMULATED)**

---

## What is UrbanSense AI?

UrbanSense AI is an intelligent road condition monitoring system that uses sensor-equipped public buses to continuously observe and classify road defects. The system provides city authorities with near-real-time awareness of road conditions through a digital twin (RoadTwin) of the city's road network.

---

## Architecture

```
BUS-001 [Edge Device]
  ├── GNSS / IMU sensors
  ├── Camera (CAMERA-FRONT-01)
  ├── HAL (hardware abstraction)
  ├── Opportunity Evaluator     ← decides if sensing window is useful
  ├── Object Detection (YOLO)   ← Milestone 2+
  └── Event Builder → Canonical Event
           │
           │ HTTP POST
           ▼
BACKEND [FastAPI / PostgreSQL / PostGIS]
  ├── POST /api/v1/events       ← Event ingestion (idempotent)
  ├── POST /api/v1/opportunities ← Opportunity logging
  ├── Map Matcher               ← Backend-authoritative
  ├── RoadTwin Engine           ← The ONLY RoadTwin implementation
  │     └── roadtwin_states table
  └── GET /api/v1/roadtwin      ← Frontend read API
           │
           │ JSON API
           ▼
DASHBOARD [React / Leaflet]
  └── RoadTwin Map              ← Reads via API only
```

---

## Milestone Status

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M0: Foundation** | ✅ Complete | Docker, DB, infra, env |
| **M1: First E2E Slice** | 🚧 In Progress | Simulated data, backend APIs, map |
| M2: Real Detection | 📋 Planned | YOLO integration |
| M3: Evidence Fusion | 📋 Planned | Multi-bus aggregation |
| M4: Full Lifecycle | 📋 Planned | 8-state RoadTwin |
| M5: Production | 📋 Planned | RBAC, auth, scaling |

---

## Repository Structure

```
UrbanSense AI/
├── contracts/          # Shared Pydantic contracts (Edge ↔ Backend)
│   ├── observation.py
│   ├── opportunity.py
│   ├── canonical_event.py
│   └── roadtwin_state.py
├── edge/               # Edge device modules
│   └── app/
│       ├── hal/        # Hardware abstraction layer
│       ├── opportunity/ # Opportunity evaluator
│       └── simulation/ # Simulated sensing pass
├── backend/            # FastAPI backend
│   ├── app/
│   │   ├── api/v1/     # REST endpoints
│   │   ├── models/     # SQLAlchemy ORM
│   │   ├── schemas/    # Pydantic API schemas
│   │   ├── services/   # Map matcher, etc.
│   │   └── roadtwin/   # THE ONLY RoadTwin implementation
│   └── alembic/        # Database migrations
├── frontend/           # React + Leaflet dashboard
│   └── src/
│       ├── components/ # RoadTwinMap component
│       └── client/     # Backend API client
├── scripts/
│   └── run_m1_demo.py  # End-to-end demo script
├── tests/
│   └── test_m1.py      # Milestone 1 test suite
├── docker-compose.yml  # Infrastructure services
└── docs/               # Documentation
```

---

## Quick Start

```bash
# 1. Start infrastructure
docker compose up -d postgres redis minio mosquitto

# 2. Run database migration
cd backend && alembic upgrade head && cd ..

# 3. Start backend
uvicorn backend.app.main:app --reload

# 4. Run the demo
python scripts/run_m1_demo.py

# 5. Start frontend
cd frontend && npm install && npm run dev

# 6. Open dashboard
# http://localhost:5173

# 7. Run tests
pytest tests/test_m1.py -k "not integration" -v
```

---

## Key Semantic Rules

| Field | Owner | Description |
|-------|-------|-------------|
| `detector_confidence` | Edge | Raw model softmax output |
| `observation_quality` | Edge | Derived from opportunity scores |
| `gps_quality` | Edge | GPS fix quality |
| `aggregate_confidence` | **Backend** | RoadTwin-level fusion |
| `matched_road_segment_id` | **Backend** | Authoritative map-match |
| `edge_road_segment_hint` | Edge | ADVISORY ONLY |

> ⚠ NEVER create a field named just `confidence`. Always specify what kind.

---

## License

[To be determined — internal SIH project]

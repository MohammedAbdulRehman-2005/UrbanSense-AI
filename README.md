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
  ├── Camera (CAMERA-FRONT-01 / FileCameraProvider)
  ├── HAL (hardware abstraction layer)
  ├── Opportunity Evaluator     ← windowed sensing evaluation (Option A snapshot)
  ├── Object Detection          ← Baseline Heuristic Detectors (BaseDetector interface)
  ├── Same-Camera Tracking      ← SameCameraTracker (temporal IoU)
  ├── Quality Evaluator         ← Optical frame & crop quality signals
  ├── Evidence Store            ← Local crop storage (evidence://local/...)
  └── Event Builder             ← Canonical Event with SHA-256 payload_hash
           │
           │ HTTP POST
           ▼
BACKEND [FastAPI / PostgreSQL / PostGIS]
  ├── POST /api/v1/events       ← Event ingestion (idempotent, type-gated)
  ├── POST /api/v1/opportunities ← Opportunity logging
  ├── Map Matcher               ← Backend-authoritative
  ├── RoadTwin Engine           ← The ONLY RoadTwin implementation (OBSERVED state)
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
| **M0: Foundation** | ✅ Complete | Docker, DB, PostGIS, MinIO, Redis, Mosquitto |
| **M1: First E2E Slice** | ✅ Complete | Simulated sensing, backend APIs, map, OBSERVED RoadTwin |
| **M2 / M2.1: Perception & Hardening** | ✅ Complete | Video HAL, baseline CV detectors, tracking, quality, windowed opportunity, evidence lineage, runtime verification |
| M3: Evidence Fusion | 📋 Planned | Multi-bus aggregation, deduplication, lifecycle transitions |
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

# 4. Run the demos
python scripts/run_m1_demo.py       # Milestone 1 simulated sensing demo
python scripts/run_video_demo.py    # Milestone 2.1 video perception demo

# 5. Start frontend
cd frontend && npm install && npm run build && npm run dev

# 6. Open dashboard
# http://localhost:5173

# 7. Run test suite
pytest -v
```

---

## Key Semantic Rules

| Field | Owner | Description |
|-------|-------|-------------|
| `detector_confidence` | Edge | Heuristic detector baseline score (bounded [0.0, 1.0], DECISION-013; uncalibrated prototype score, not Bayesian probability or Softmax) |
| `observation_quality` | Edge | Optical quality signals for the crop (sharpness, contrast, exposure) |
| `gps_quality` | Edge | Normalized GNSS fix quality (0.0 when accuracy unavailable) |
| `aggregate_confidence` | **Backend** | RoadTwin-level fusion score |
| `matched_road_segment_id` | **Backend** | Authoritative map-match result |
| `edge_road_segment_hint` | Edge | ADVISORY ONLY |

> ⚠ NEVER create a field named just `confidence`. Always specify what kind.

---

## License

[To be determined — internal SIH project]

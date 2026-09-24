"""
UrbanSense AI — FastAPI Backend Main (Milestone 1)
===================================================
Modular-monolith structure. No microservices.
OpenAPI schema is generated automatically — this is the API source of truth.
PROTOTYPE / SIMULATED — not production-ready.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import router as api_v1_router
from backend.app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="UrbanSense AI Backend",
    version="1.0.0-M1",
    description=(
        "UrbanSense AI — Milestone 1 first vertical slice. "
        "PROTOTYPE / SIMULATED — not production-ready."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # PROTOTYPE — lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0-M1",
        "note": "PROTOTYPE / SIMULATED — Milestone 1 foundation only",
    }

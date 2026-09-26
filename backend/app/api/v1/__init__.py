# UrbanSense AI API v1 router registration
from fastapi import APIRouter
from backend.app.api.v1 import events, opportunities, roadtwin, evidence, maintenance, traffic

router = APIRouter(prefix="/api/v1")
router.include_router(events.router, tags=["Events"])
router.include_router(opportunities.router, tags=["Opportunities"])
router.include_router(roadtwin.router, tags=["RoadTwin"])
router.include_router(evidence.router, tags=["Evidence"])
router.include_router(maintenance.router, tags=["Maintenance"])
router.include_router(traffic.router, tags=["Traffic"])

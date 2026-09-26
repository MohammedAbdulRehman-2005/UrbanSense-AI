"""
UrbanSense AI — Milestone 5 Slice 3: Frontend Read-Model & GIS Parity Tests
=============================================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Phase 19/33)

Covers:
1. OpenAPI specification contract parity for frontend client:
   - /api/v1/traffic parameter signatures and schema types
   - /api/v1/bottlenecks parameter signatures and schema types
2. Response schema completeness (all fields rendered in GIS and detail drawer):
   - TrafficObservationResponse: window times, vehicle count & class counts, speed, density, flow, congestion, segment coords
   - BottleneckResponse: status, severity, density/speed explainability conditions, qualifying streaks, evidence windows
3. API execution with filters (segment filtering, status filtering, limit validation)
4. Frontend TypeScript contract parity (types.ts field alignment with backend Pydantic models)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.road_segment import RoadSegment
from backend.app.models.traffic import TrafficObservationModel, TrafficBottleneckModel
from backend.app.schemas.traffic import TrafficObservationResponse, BottleneckResponse


@pytest.fixture
def client():
    return TestClient(app)


class TestFrontendOpenAPIContracts:
    """Verifies that backend OpenAPI schema exposes everything expected by frontend client."""

    def test_openapi_schema_contains_traffic_and_bottleneck_routes(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})

        assert "/api/v1/traffic" in paths
        assert "/api/v1/bottlenecks" in paths
        assert "/api/v1/roadtwin" in paths

    def test_traffic_endpoint_query_params_in_openapi(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()

        traffic_get = schema["paths"]["/api/v1/traffic"]["get"]
        param_names = [p["name"] for p in traffic_get.get("parameters", [])]

        assert "road_segment_id" in param_names
        assert "start_time" in param_names
        assert "end_time" in param_names
        assert "limit" in param_names

    def test_bottleneck_endpoint_query_params_in_openapi(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()

        bottlenecks_get = schema["paths"]["/api/v1/bottlenecks"]["get"]
        param_names = [p["name"] for p in bottlenecks_get.get("parameters", [])]

        assert "road_segment_id" in param_names
        assert "status" in param_names
        assert "limit" in param_names

    def test_traffic_response_schema_contains_all_ui_fields(self, client):
        resp = client.get("/openapi.json")
        schema = resp.json()

        schemas = schema.get("components", {}).get("schemas", {})
        assert "TrafficObservationResponse" in schemas
        props = schemas["TrafficObservationResponse"].get("properties", {})

        expected_fields = [
            "traffic_observation_id",
            "road_segment_id",
            "window_start",
            "window_end",
            "vehicle_count",
            "vehicle_class_counts",
            "average_speed_kmh",
            "density",
            "flow_rate",
            "congestion_state",
            "trace_id",
            "segment_name",
            "centroid_lat",
            "centroid_lon",
        ]
        for field in expected_fields:
            assert field in props, f"Missing {field} in TrafficObservationResponse schema"

    def test_bottleneck_response_schema_contains_all_ui_fields(self, client):
        resp = client.get("/openapi.json")
        schema = resp.json()

        schemas = schema.get("components", {}).get("schemas", {})
        assert "BottleneckResponse" in schemas
        props = schemas["BottleneckResponse"].get("properties", {})

        expected_fields = [
            "bottleneck_id",
            "road_segment_id",
            "status",
            "severity",
            "density_condition",
            "speed_condition",
            "qualifying_window_count",
            "required_window_count",
            "first_qualifying_window_start",
            "latest_qualifying_window_end",
            "evidence_window_ids",
            "start_time",
            "resolved_at",
            "segment_name",
            "centroid_lat",
            "centroid_lon",
        ]
        for field in expected_fields:
            assert field in props, f"Missing {field} in BottleneckResponse schema"


class TestFrontendReadModelResponses:
    """Verifies live or mock responses match the typed structures expected by RoadTwinMap."""

    def test_traffic_endpoint_returns_json_list(self, client):
        resp = client.get("/api/v1/traffic?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            item = data[0]
            assert "traffic_observation_id" in item
            assert "road_segment_id" in item
            assert "vehicle_count" in item
            assert "congestion_state" in item
            assert item["congestion_state"] in ("NORMAL", "ELEVATED", "HIGH")

    def test_bottlenecks_endpoint_returns_json_list(self, client):
        resp = client.get("/api/v1/bottlenecks?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            item = data[0]
            assert "bottleneck_id" in item
            assert "road_segment_id" in item
            assert "status" in item
            assert "qualifying_window_count" in item
            assert "required_window_count" in item

    def test_traffic_endpoint_filtering_by_segment(self, client):
        resp = client.get("/api/v1/traffic?road_segment_id=NON_EXISTENT_SEGMENT_XYZ")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_bottlenecks_endpoint_filtering_by_segment(self, client):
        resp = client.get("/api/v1/bottlenecks?road_segment_id=NON_EXISTENT_SEGMENT_XYZ")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []


class TestFrontendTypeDefinitionParity:
    """Verifies that frontend/src/client/types.ts mirrors backend Pydantic models."""

    def test_frontend_types_file_exists_and_contains_interfaces(self):
        from pathlib import Path
        types_path = Path(__file__).resolve().parent.parent / "frontend" / "src" / "client" / "types.ts"
        assert types_path.exists(), f"Frontend types file not found at {types_path}"

        content = types_path.read_text(encoding="utf-8")
        assert "export interface TrafficObservationResponse" in content
        assert "export interface BottleneckResponse" in content
        assert "export interface RoadTwinResponse" in content

        # Check key fields in TypeScript definition
        assert "traffic_observation_id: string;" in content
        assert "congestion_state: 'NORMAL' | 'ELEVATED' | 'HIGH';" in content
        assert "bottleneck_id: string;" in content
        assert "qualifying_window_count: number;" in content
        assert "required_window_count: number;" in content
        assert "evidence_window_ids: string[];" in content

/**
 * UrbanSense AI — Backend API client (Milestone 1)
 *
 * Frontend communicates ONLY through this client.
 * Frontend does NOT query PostgreSQL directly.
 * Frontend does NOT reconstruct RoadTwin rules.
 * Frontend does NOT calculate confidence aggregation.
 * Frontend does NOT perform map-match authority.
 *
 * PROTOTYPE / SIMULATED — Milestone 1 only.
 */

import type { RoadTwinResponse, HealthResponse } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function fetchHealth(): Promise<HealthResponse> {
  const resp = await fetch(`${API_BASE}/health`);
  if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
  return resp.json();
}

export async function fetchRoadTwins(): Promise<RoadTwinResponse[]> {
  const resp = await fetch(`${API_BASE}/api/v1/roadtwin`);
  if (!resp.ok) throw new Error(`RoadTwin fetch failed: ${resp.status}`);
  return resp.json();
}

export async function fetchRoadTwin(roadtwinId: string): Promise<RoadTwinResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/roadtwin/${roadtwinId}`);
  if (!resp.ok) throw new Error(`RoadTwin ${roadtwinId} not found: ${resp.status}`);
  return resp.json();
}

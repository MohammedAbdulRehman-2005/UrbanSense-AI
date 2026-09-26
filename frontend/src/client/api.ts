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

import type {
  RoadTwinResponse,
  HealthResponse,
  TrafficObservationResponse,
  BottleneckResponse,
} from './types';

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

export interface TrafficQueryOptions {
  roadSegmentId?: string;
  startTime?: string;
  endTime?: string;
  limit?: number;
}

export async function fetchTraffic(
  optionsOrSegmentId?: string | TrafficQueryOptions
): Promise<TrafficObservationResponse[]> {
  const params = new URLSearchParams();
  if (typeof optionsOrSegmentId === 'string') {
    params.set('road_segment_id', optionsOrSegmentId);
  } else if (optionsOrSegmentId) {
    if (optionsOrSegmentId.roadSegmentId) params.set('road_segment_id', optionsOrSegmentId.roadSegmentId);
    if (optionsOrSegmentId.startTime) params.set('start_time', optionsOrSegmentId.startTime);
    if (optionsOrSegmentId.endTime) params.set('end_time', optionsOrSegmentId.endTime);
    if (optionsOrSegmentId.limit) params.set('limit', String(optionsOrSegmentId.limit));
  }
  const queryString = params.toString();
  const url = queryString ? `${API_BASE}/api/v1/traffic?${queryString}` : `${API_BASE}/api/v1/traffic`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Traffic fetch failed: ${resp.status}`);
  return resp.json();
}

export interface BottleneckQueryOptions {
  roadSegmentId?: string;
  status?: string;
  limit?: number;
}

export async function fetchBottlenecks(
  roadSegmentIdOrOptions?: string | BottleneckQueryOptions,
  status: string = 'ACTIVE'
): Promise<BottleneckResponse[]> {
  const params = new URLSearchParams();
  if (typeof roadSegmentIdOrOptions === 'string') {
    if (status) params.set('status', status);
    params.set('road_segment_id', roadSegmentIdOrOptions);
  } else if (roadSegmentIdOrOptions) {
    params.set('status', roadSegmentIdOrOptions.status || 'ACTIVE');
    if (roadSegmentIdOrOptions.roadSegmentId) params.set('road_segment_id', roadSegmentIdOrOptions.roadSegmentId);
    if (roadSegmentIdOrOptions.limit) params.set('limit', String(roadSegmentIdOrOptions.limit));
  } else {
    params.set('status', status);
  }
  const url = `${API_BASE}/api/v1/bottlenecks?${params.toString()}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Bottleneck fetch failed: ${resp.status}`);
  return resp.json();
}


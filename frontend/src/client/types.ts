/**
 * UrbanSense AI — API client types (Milestone 1)
 *
 * These types mirror the FastAPI backend schemas.
 * DO NOT hand-maintain these alongside Pydantic models.
 *
 * To regenerate from live backend:
 *   npm run generate-client
 *   (requires: npx openapi-typescript http://localhost:8000/openapi.json -o src/client/schema.d.ts)
 *
 * PROTOTYPE / SIMULATED — Milestone 1 only.
 */

export interface RoadTwinResponse {
  roadtwin_id: string;
  road_segment_id: string;
  subject_id?: string | null;
  subject_type?: string | null;
  current_state: string;
  /** Backend-fused aggregate confidence. DISTINCT from detector_confidence. */
  aggregate_confidence: number;
  positive_evidence_count: number;
  negative_evidence_count: number;
  independent_bus_count: number;
  first_seen_at: string;
  last_seen_at: string;
  last_validated_at?: string | null;
  freshness_status: string;
  maintenance_status: string;
  verification_status: string;
  active_episode_id?: string | null;
  previous_episode_id?: string | null;
  last_event_id?: string | null;
  last_observation_id?: string | null;
  segment_centroid_lat?: number | null;
  segment_centroid_lon?: number | null;
  segment_name?: string | null;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
  note: string;
}

export interface TrafficObservationResponse {
  traffic_observation_id: string;
  road_segment_id: string;
  window_start: string;
  window_end: string;
  bus_id?: string | null;
  device_id?: string | null;
  camera_id?: string | null;
  sensing_pass_id?: string | null;
  vehicle_count: number;
  vehicle_class_counts: Record<string, number>;
  average_speed_kmh?: number | null;
  density: number;
  flow_rate: number;
  congestion_state: 'NORMAL' | 'ELEVATED' | 'HIGH';
  trace_id: string;
  created_at?: string | null;
  segment_name?: string | null;
  centroid_lat?: number | null;
  centroid_lon?: number | null;
}

export interface BottleneckResponse {
  bottleneck_id: string;
  road_segment_id: string;
  status: 'ACTIVE' | 'RESOLVED' | string;
  severity: string;
  density_condition: string;
  speed_condition: string;
  qualifying_window_count: number;
  required_window_count: number;
  first_qualifying_window_start: string;
  latest_qualifying_window_end: string;
  evidence_window_ids: string[];
  start_time: string;
  resolved_at?: string | null;
  segment_name?: string | null;
  centroid_lat?: number | null;
  centroid_lon?: number | null;
}


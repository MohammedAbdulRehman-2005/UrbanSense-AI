/**
 * UrbanSense AI — RoadTwin & Traffic Intelligence GIS Map (Milestones 1–5)
 * ========================================================================
 * SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4)
 *
 * Renders:
 * - RoadTwin defect states (OBSERVED, CANDIDATE, CONFIRMED, MAINTENANCE_PENDING, etc.)
 * - Traffic Intelligence layer (vehicle counts, fleet speed, density, flow rate, congestion)
 * - Persistent Bottleneck layer (rolling 3-window condition: high density + low speed)
 *
 * ARCHITECTURAL INVARIANTS:
 * - Consumes data ONLY from the backend read API (never PostgreSQL directly).
 * - Does NOT calculate density, flow, congestion, or bottleneck persistence in React.
 * - Does NOT duplicate backend threshold constants in the frontend.
 * - Explicit layer toggles allow separating defect maintenance from traffic analytics.
 * - Multi-domain interactive selection surfaces complete backend telemetry.
 */

import React, { useEffect, useState, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import type { RoadTwinResponse, TrafficObservationResponse, BottleneckResponse } from '../client/types';
import { fetchRoadTwins, fetchTraffic, fetchBottlenecks } from '../client/api';
import 'leaflet/dist/leaflet.css';

const STATE_COLORS: Record<string, string> = {
  OBSERVED: '#f59e0b',            // amber
  CANDIDATE: '#3b82f6',           // blue
  CONFIRMED: '#ef4444',           // red
  MAINTENANCE_PENDING: '#8b5cf6', // purple
  REPAIR_REPORTED: '#ec4899',     // pink
  VERIFICATION_PENDING: '#6366f1',// indigo
  VERIFIED_REPAIRED: '#10b981',   // emerald green
  REAPPEARED: '#ea580c',          // deep orange
  ACTIVE: '#dc2626',              // dark red
};

const CONGESTION_COLORS: Record<string, string> = {
  NORMAL: '#22c55e',   // green
  ELEVATED: '#f97316', // orange
  HIGH: '#ef4444',     // red
};

function stateColor(state: string): string {
  return STATE_COLORS[state] ?? '#9ca3af';
}

function congestionColor(state: string): string {
  return CONGESTION_COLORS[state] ?? '#3b82f6';
}

function formatRelativeTime(isoString?: string | null): { text: string; color: string } {
  if (!isoString) return { text: 'N/A', color: '#64748b' };
  try {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 0) return { text: 'Just now', color: '#22c55e' };
    if (diffMin < 5) return { text: `Active (${diffMin === 0 ? 'just now' : `${diffMin}m ago`})`, color: '#22c55e' };
    if (diffMin < 60) return { text: `Recent (${diffMin}m ago)`, color: '#eab308' };
    const diffHours = Math.round(diffMin / 60);
    return { text: `Historical (${diffHours}h ago)`, color: '#94a3b8' };
  } catch {
    return { text: 'Invalid Date', color: '#64748b' };
  }
}

export type SelectedEntity =
  | { type: 'roadtwin'; data: RoadTwinResponse }
  | { type: 'traffic'; data: TrafficObservationResponse }
  | { type: 'bottleneck'; data: BottleneckResponse }
  | null;

function getEntityCoordinates(entity: SelectedEntity): { lat: number | null; lon: number | null } {
  if (!entity) return { lat: null, lon: null };
  if (entity.type === 'roadtwin') {
    return {
      lat: entity.data.segment_centroid_lat ?? null,
      lon: entity.data.segment_centroid_lon ?? null,
    };
  }
  return {
    lat: entity.data.centroid_lat ?? null,
    lon: entity.data.centroid_lon ?? null,
  };
}

// ============================================================================
// MAP MARKERS
// ============================================================================

function RoadTwinMarker({
  rt,
  onSelect,
}: {
  rt: RoadTwinResponse;
  onSelect: (rt: RoadTwinResponse) => void;
}) {
  if (!rt.segment_centroid_lat || !rt.segment_centroid_lon) return null;

  return (
    <CircleMarker
      center={[rt.segment_centroid_lat, rt.segment_centroid_lon]}
      radius={13}
      eventHandlers={{
        click: () => onSelect(rt),
      }}
      pathOptions={{
        color: stateColor(rt.current_state),
        fillColor: stateColor(rt.current_state),
        fillOpacity: 0.65,
        weight: 2,
      }}
    >
      <Popup>
        <div style={{ minWidth: '220px', fontFamily: 'monospace', fontSize: '12px' }}>
          <strong style={{ color: stateColor(rt.current_state) }}>
            🛑 Defect: {rt.current_state}
          </strong>
          <br />
          <b>Segment:</b> {rt.road_segment_id}
          <br />
          <b>Name:</b> {rt.segment_name ?? 'N/A'}
          <br />
          <hr style={{ margin: '4px 0', borderColor: '#334155' }} />
          <b>Confidence:</b> {(rt.aggregate_confidence * 100).toFixed(1)}%
          <br />
          <b>Evidence (+/-):</b> +{rt.positive_evidence_count} / -{rt.negative_evidence_count}
          <br />
          <b>Buses:</b> {rt.independent_bus_count}
          <br />
          <b>Maintenance:</b> {rt.maintenance_status}
          <br />
          <b>Verification:</b> {rt.verification_status}
          <div style={{ marginTop: '8px', textAlign: 'right' }}>
            <button
              onClick={() => onSelect(rt)}
              style={{
                background: '#1e3a8a',
                color: '#93c5fd',
                border: '1px solid #3b82f6',
                borderRadius: '4px',
                padding: '3px 8px',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              Open Detail Panel →
            </button>
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function TrafficMarker({
  obs,
  onSelect,
}: {
  obs: TrafficObservationResponse;
  onSelect: (obs: TrafficObservationResponse) => void;
}) {
  if (!obs.centroid_lat || !obs.centroid_lon) return null;

  // Spatial offset so traffic doesn't perfectly hide roadtwin
  const lat = obs.centroid_lat + 0.0005;
  const lon = obs.centroid_lon + 0.0005;

  return (
    <CircleMarker
      center={[lat, lon]}
      radius={16}
      eventHandlers={{
        click: () => onSelect(obs),
      }}
      pathOptions={{
        color: congestionColor(obs.congestion_state),
        fillColor: congestionColor(obs.congestion_state),
        fillOpacity: 0.5,
        weight: 2,
        dashArray: '4, 4',
      }}
    >
      <Popup>
        <div style={{ minWidth: '240px', fontFamily: 'monospace', fontSize: '12px' }}>
          <strong style={{ color: congestionColor(obs.congestion_state) }}>
            🚗 Traffic: {obs.congestion_state}
          </strong>
          <br />
          <b>Segment:</b> {obs.road_segment_id}
          <br />
          <b>Name:</b> {obs.segment_name ?? 'N/A'}
          <br />
          <hr style={{ margin: '4px 0', borderColor: '#334155' }} />
          <b>Unique Vehicles:</b> {obs.vehicle_count}
          <br />
          <b>Density:</b> {obs.density.toFixed(1)} veh/km
          <br />
          <b>Flow Rate:</b> {obs.flow_rate.toFixed(0)} veh/h
          <br />
          <b>Fleet Speed:</b>{' '}
          {obs.average_speed_kmh != null ? `${obs.average_speed_kmh.toFixed(1)} km/h` : 'UNKNOWN'}
          <br />
          <hr style={{ margin: '4px 0', borderColor: '#334155' }} />
          <b>Window:</b>{' '}
          {new Date(obs.window_start).toLocaleTimeString()} –{' '}
          {new Date(obs.window_end).toLocaleTimeString()}
          <div style={{ marginTop: '8px', textAlign: 'right' }}>
            <button
              onClick={() => onSelect(obs)}
              style={{
                background: '#7c2d12',
                color: '#fdba74',
                border: '1px solid #f97316',
                borderRadius: '4px',
                padding: '3px 8px',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              Open Detail Panel →
            </button>
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function BottleneckMarker({
  bn,
  onSelect,
}: {
  bn: BottleneckResponse;
  onSelect: (bn: BottleneckResponse) => void;
}) {
  if (!bn.centroid_lat || !bn.centroid_lon) return null;

  // Offset position to stand out distinctly
  const lat = bn.centroid_lat - 0.0006;
  const lon = bn.centroid_lon - 0.0006;

  return (
    <CircleMarker
      center={[lat, lon]}
      radius={21}
      eventHandlers={{
        click: () => onSelect(bn),
      }}
      pathOptions={{
        color: '#dc2626',
        fillColor: '#7c3aed',
        fillOpacity: 0.82,
        weight: 3,
      }}
    >
      <Popup>
        <div style={{ minWidth: '260px', fontFamily: 'monospace', fontSize: '12px' }}>
          <strong style={{ color: '#dc2626', fontSize: '13px' }}>
            🚨 BOTTLENECK ACTIVE
          </strong>
          <br />
          <b>Segment:</b> {bn.road_segment_id}
          <br />
          <b>Name:</b> {bn.segment_name ?? 'N/A'}
          <br />
          <b>Severity:</b> {bn.severity}
          <br />
          <hr style={{ margin: '4px 0', borderColor: '#334155' }} />
          <b>Streak:</b> {bn.qualifying_window_count} of {bn.required_window_count} windows
          <br />
          <b>Density Condition:</b>{' '}
          <span style={{ color: '#ef4444' }}>{bn.density_condition}</span>
          <br />
          <b>Speed Condition:</b>{' '}
          <span style={{ color: '#ef4444' }}>{bn.speed_condition}</span>
          <div style={{ marginTop: '8px', textAlign: 'right' }}>
            <button
              onClick={() => onSelect(bn)}
              style={{
                background: '#7f1d1d',
                color: '#fca5a5',
                border: '1px solid #dc2626',
                borderRadius: '4px',
                padding: '3px 8px',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              Open Detail Panel →
            </button>
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function AutoCenter({ coords }: { coords: Array<[number, number]> }) {
  const map = useMap();
  useEffect(() => {
    if (coords.length > 0) {
      map.setView(coords[0], 14);
    }
  }, [coords, map]);
  return null;
}

// ============================================================================
// DETAIL DRAWER / PANEL
// ============================================================================

function DetailPanel({
  entity,
  onClose,
  allBottlenecks,
}: {
  entity: SelectedEntity;
  onClose: () => void;
  allBottlenecks: BottleneckResponse[];
}) {
  if (!entity) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: '390px',
        height: '100%',
        backgroundColor: '#0f172a',
        borderLeft: '1px solid #334155',
        boxShadow: '-6px 0 20px rgba(0,0,0,0.6)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        color: '#f8fafc',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      {/* Panel Header */}
      <div
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid #334155',
          background: '#1e293b',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <span
            style={{
              fontSize: '10px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '4px',
              backgroundColor:
                entity.type === 'traffic'
                  ? '#7c2d12'
                  : entity.type === 'bottleneck'
                  ? '#7f1d1d'
                  : '#1e3a8a',
              color:
                entity.type === 'traffic'
                  ? '#fdba74'
                  : entity.type === 'bottleneck'
                  ? '#fca5a5'
                  : '#93c5fd',
            }}
          >
            {entity.type === 'traffic'
              ? 'Traffic Observation'
              : entity.type === 'bottleneck'
              ? 'Bottleneck Detection'
              : 'RoadTwin Defect'}
          </span>
          <h2 style={{ margin: '6px 0 0 0', fontSize: '16px', fontWeight: 600 }}>
            {entity.data.segment_name || entity.data.road_segment_id}
          </h2>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#94a3b8',
            fontSize: '18px',
            cursor: 'pointer',
            padding: '4px 8px',
          }}
          title="Close panel"
        >
          ✕
        </button>
      </div>

      {/* Panel Scrollable Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', fontSize: '13px' }}>
        {/* Spatial Information */}
        <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
          <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
            SPATIAL IDENTITY
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ color: '#64748b' }}>Segment ID:</span>
            <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{entity.data.road_segment_id}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ color: '#64748b' }}>Coordinates:</span>
            <span style={{ fontFamily: 'monospace' }}>
              {(() => {
                const coords = getEntityCoordinates(entity);
                return coords.lat != null && coords.lon != null
                  ? `${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`
                  : 'N/A';
              })()}
            </span>
          </div>
        </div>

        {/* Entity-specific Views */}
        {entity.type === 'traffic' && (
          <>
            {/* Freshness & Window */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                OBSERVATION WINDOW
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Freshness:</span>
                {(() => {
                  const badge = formatRelativeTime(entity.data.window_end);
                  return <span style={{ color: badge.color, fontWeight: 600 }}>{badge.text}</span>;
                })()}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Start:</span>
                <span style={{ fontFamily: 'monospace' }}>{new Date(entity.data.window_start).toLocaleTimeString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>End:</span>
                <span style={{ fontFamily: 'monospace' }}>{new Date(entity.data.window_end).toLocaleTimeString()}</span>
              </div>
            </div>

            {/* Metrics */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                TRAFFIC METRICS (BACKEND-COMPUTED)
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ color: '#64748b' }}>Congestion State:</span>
                <span
                  style={{
                    backgroundColor: congestionColor(entity.data.congestion_state),
                    color: '#fff',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontWeight: 700,
                    fontSize: '11px',
                  }}
                >
                  {entity.data.congestion_state}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Deduplicated Vehicles:</span>
                <span style={{ fontWeight: 700, color: '#f8fafc' }}>{entity.data.vehicle_count}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Density:</span>
                <span style={{ fontWeight: 600 }}>{entity.data.density.toFixed(2)} veh/km</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Flow Rate:</span>
                <span style={{ fontWeight: 600 }}>{entity.data.flow_rate.toFixed(0)} veh/h</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Fleet Average Speed:</span>
                <span style={{ fontWeight: 600 }}>
                  {entity.data.average_speed_kmh != null
                    ? `${entity.data.average_speed_kmh.toFixed(1)} km/h`
                    : 'UNKNOWN (telemetry sparse)'}
                </span>
              </div>
            </div>

            {/* Vehicle Classification Breakdown */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '8px' }}>
                CLASSIFICATION BREAKDOWN
              </div>
              {Object.keys(entity.data.vehicle_class_counts).length === 0 ? (
                <span style={{ color: '#64748b', fontStyle: 'italic' }}>No vehicle classes reported</span>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {Object.entries(entity.data.vehicle_class_counts).map(([cls, cnt]) => (
                    <div
                      key={cls}
                      style={{
                        background: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '4px',
                        padding: '4px 8px',
                        fontSize: '11px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <span style={{ color: '#94a3b8' }}>{cls}:</span>
                      <strong style={{ color: '#38bdf8' }}>{cnt}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Active Bottleneck Cross-Check */}
            {(() => {
              const activeBn = allBottlenecks.find(
                (b) => b.road_segment_id === entity.data.road_segment_id && b.status === 'ACTIVE'
              );
              if (activeBn) {
                return (
                  <div
                    style={{
                      marginBottom: '16px',
                      background: '#7f1d1d22',
                      border: '1px solid #dc2626',
                      borderRadius: '6px',
                      padding: '12px',
                    }}
                  >
                    <div style={{ color: '#f87171', fontWeight: 700, fontSize: '12px', marginBottom: '4px' }}>
                      🚨 Active Bottleneck Condition Detected
                    </div>
                    <div style={{ fontSize: '11px', color: '#fca5a5' }}>
                      This segment has satisfied bottleneck conditions for{' '}
                      <strong>{activeBn.qualifying_window_count} of {activeBn.required_window_count}</strong> consecutive
                      windows.
                    </div>
                  </div>
                );
              }
              return null;
            })()}

            {/* Sensing Lineage */}
            <div style={{ background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                SENSING LINEAGE
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Bus ID:</span>
                <span style={{ fontFamily: 'monospace' }}>{entity.data.bus_id || 'N/A'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Device / Camera:</span>
                <span style={{ fontFamily: 'monospace' }}>
                  {entity.data.device_id || 'N/A'} / {entity.data.camera_id || 'N/A'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Trace ID:</span>
                <span style={{ fontFamily: 'monospace', fontSize: '10px' }}>{entity.data.trace_id}</span>
              </div>
            </div>
          </>
        )}

        {entity.type === 'bottleneck' && (
          <>
            {/* Bottleneck Status */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                BOTTLENECK PERSISTENCE
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Status:</span>
                <span
                  style={{
                    backgroundColor: entity.data.status === 'ACTIVE' ? '#dc2626' : '#10b981',
                    color: '#fff',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontWeight: 700,
                    fontSize: '11px',
                  }}
                >
                  {entity.data.status}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Severity:</span>
                <span style={{ fontWeight: 600, color: '#f87171' }}>{entity.data.severity}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Persistence Streak:</span>
                <span style={{ fontWeight: 700, color: '#fca5a5' }}>
                  {entity.data.qualifying_window_count} of {entity.data.required_window_count} windows
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Started At:</span>
                <span style={{ fontFamily: 'monospace' }}>{new Date(entity.data.start_time).toLocaleTimeString()}</span>
              </div>
            </div>

            {/* Explainability Conditions */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                EXPLAINABILITY CRITERIA
              </div>
              <div style={{ marginBottom: '6px' }}>
                <span style={{ color: '#64748b', fontSize: '11px' }}>Density Threshold:</span>
                <div
                  style={{
                    color: '#f87171',
                    fontFamily: 'monospace',
                    marginTop: '2px',
                    padding: '4px 6px',
                    background: '#0f172a',
                    borderRadius: '4px',
                  }}
                >
                  {entity.data.density_condition}
                </div>
              </div>
              <div>
                <span style={{ color: '#64748b', fontSize: '11px' }}>Speed Condition:</span>
                <div
                  style={{
                    color: '#f87171',
                    fontFamily: 'monospace',
                    marginTop: '2px',
                    padding: '4px 6px',
                    background: '#0f172a',
                    borderRadius: '4px',
                  }}
                >
                  {entity.data.speed_condition}
                </div>
              </div>
            </div>

            {/* Supporting Windows */}
            <div style={{ background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                SUPPORTING EVIDENCE WINDOWS ({entity.data.evidence_window_ids.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {entity.data.evidence_window_ids.map((winId, idx) => (
                  <div
                    key={winId}
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      background: '#0f172a',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      color: '#94a3b8',
                    }}
                  >
                    Window #{idx + 1}: {winId}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {entity.type === 'roadtwin' && (
          <>
            {/* Defect Lifecycle */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                ROADTWIN DEFECT STATE
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ color: '#64748b' }}>Lifecycle State:</span>
                <span
                  style={{
                    backgroundColor: stateColor(entity.data.current_state),
                    color: '#fff',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontWeight: 700,
                    fontSize: '11px',
                  }}
                >
                  {entity.data.current_state}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Fused Confidence:</span>
                <span style={{ fontWeight: 700, color: '#38bdf8' }}>
                  {(entity.data.aggregate_confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Positive Evidence (+):</span>
                <span style={{ fontWeight: 600 }}>{entity.data.positive_evidence_count}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Negative Evidence (-):</span>
                <span style={{ fontWeight: 600 }}>{entity.data.negative_evidence_count}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Independent Sensing Buses:</span>
                <span style={{ fontWeight: 600 }}>{entity.data.independent_bus_count}</span>
              </div>
            </div>

            {/* Maintenance & Verification */}
            <div style={{ marginBottom: '16px', background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                CLOSED-LOOP MAINTENANCE
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Maintenance Status:</span>
                <span style={{ fontWeight: 600 }}>{entity.data.maintenance_status}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Verification Status:</span>
                <span style={{ fontWeight: 600 }}>{entity.data.verification_status}</span>
              </div>
              {entity.data.active_episode_id && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: '#64748b' }}>Active Episode:</span>
                  <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                    {entity.data.active_episode_id.substring(0, 12)}...
                  </span>
                </div>
              )}
            </div>

            {/* Timestamps */}
            <div style={{ background: '#1e293b', borderRadius: '6px', padding: '12px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '6px' }}>
                TIMESTAMPS
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>First Seen:</span>
                <span style={{ fontFamily: 'monospace' }}>{new Date(entity.data.first_seen_at).toLocaleTimeString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: '#64748b' }}>Last Seen:</span>
                <span style={{ fontFamily: 'monospace' }}>{new Date(entity.data.last_seen_at).toLocaleTimeString()}</span>
              </div>
              {entity.data.last_validated_at && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: '#64748b' }}>Last Validated:</span>
                  <span style={{ fontFamily: 'monospace' }}>
                    {new Date(entity.data.last_validated_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// ON-MAP COLLAPSIBLE GIS LEGEND
// ============================================================================

function MapLegend() {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '24px',
        left: '20px',
        zIndex: 990,
        backgroundColor: 'rgba(15, 23, 42, 0.94)',
        border: '1px solid #334155',
        borderRadius: '8px',
        color: '#f8fafc',
        boxShadow: '0 4px 14px rgba(0,0,0,0.5)',
        backdropFilter: 'blur(6px)',
        fontSize: '11px',
        maxWidth: '300px',
      }}
    >
      <div
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: '8px 12px',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontWeight: 600,
          borderBottom: isOpen ? '1px solid #334155' : 'none',
          userSelect: 'none',
        }}
      >
        <span>🗺️ GIS Semantics Legend</span>
        <span style={{ color: '#94a3b8' }}>{isOpen ? '▲' : '▼'}</span>
      </div>

      {isOpen && (
        <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {/* Defects */}
          <div>
            <div style={{ fontWeight: 600, color: '#93c5fd', marginBottom: '4px' }}>
              🛑 RoadTwin Defects (Solid Circle)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
                <span>Observed</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#3b82f6' }} />
                <span>Candidate</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#ef4444' }} />
                <span>Confirmed</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#8b5cf6' }} />
                <span>Maint. Pending</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#6366f1' }} />
                <span>Verif. Pending</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#10b981' }} />
                <span>Repaired</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#ea580c' }} />
                <span>Reappeared</span>
              </div>
            </div>
          </div>

          {/* Traffic Congestion */}
          <div style={{ borderTop: '1px solid #1e293b', paddingTop: '8px' }}>
            <div style={{ fontWeight: 600, color: '#fdba74', marginBottom: '4px' }}>
              🚗 Traffic Congestion (Dashed Circle)
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#22c55e' }} />
                <span>Normal</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#f97316' }} />
                <span>Elevated</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#ef4444' }} />
                <span>High</span>
              </div>
            </div>
          </div>

          {/* Bottlenecks */}
          <div style={{ borderTop: '1px solid #1e293b', paddingTop: '8px' }}>
            <div style={{ fontWeight: 600, color: '#fca5a5', marginBottom: '4px' }}>
              🚨 Persistent Bottleneck (Double Ring)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  backgroundColor: '#7c3aed',
                  border: '2px solid #dc2626',
                  display: 'inline-block',
                }}
              />
              <span>3-Window High Density + Low Speed Condition</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT: RoadTwinMap
// ============================================================================

export function RoadTwinMap() {
  const [roadtwins, setRoadtwins] = useState<RoadTwinResponse[]>([]);
  const [trafficObs, setTrafficObs] = useState<TrafficObservationResponse[]>([]);
  const [bottlenecks, setBottlenecks] = useState<BottleneckResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  // Layer toggles
  const [showDefects, setShowDefects] = useState(true);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showBottlenecks, setShowBottlenecks] = useState(true);

  // Selected Entity for Detail Panel
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity>(null);

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [rtData, trfData, bnData] = await Promise.all([
        fetchRoadTwins().catch((err) => {
          throw new Error(`Defects API error: ${err.message}`);
        }),
        fetchTraffic().catch((err) => {
          throw new Error(`Traffic API error: ${err.message}`);
        }),
        fetchBottlenecks().catch((err) => {
          throw new Error(`Bottlenecks API error: ${err.message}`);
        }),
      ]);
      setRoadtwins(rtData);
      setTrafficObs(trfData);
      setBottlenecks(bnData);
      setError(null);
      setLastRefreshedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch GIS intelligence');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Polling aligned with 60-second window aggregation cycle (30s interval)
  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(false), 30000);
    return () => clearInterval(interval);
  }, []);

  const allCoords = useMemo(() => {
    const coords: Array<[number, number]> = [];
    roadtwins.forEach((rt) => {
      if (rt.segment_centroid_lat && rt.segment_centroid_lon) {
        coords.push([rt.segment_centroid_lat, rt.segment_centroid_lon]);
      }
    });
    trafficObs.forEach((trf) => {
      if (trf.centroid_lat && trf.centroid_lon) {
        coords.push([trf.centroid_lat, trf.centroid_lon]);
      }
    });
    return coords;
  }, [roadtwins, trafficObs]);

  const isEmpty =
    !loading &&
    !error &&
    roadtwins.length === 0 &&
    trafficObs.length === 0 &&
    bottlenecks.length === 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' }}>
      {/* Top Navbar */}
      <div
        style={{
          background: '#0f172a',
          color: '#f8fafc',
          padding: '12px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid #334155',
          zIndex: 500,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
              UrbanSense AI — RoadTwin & Traffic Intelligence GIS
            </h1>
            {refreshing && (
              <span
                style={{
                  fontSize: '11px',
                  backgroundColor: '#0369a1',
                  color: '#e0f2fe',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                🔄 Syncing...
              </span>
            )}
          </div>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
            Multi-Domain Mobility Twin: Road Defects + Vehicle Tracking + Rolling 3-Window Bottlenecks
            {lastRefreshedAt && ` • Updated: ${lastRefreshedAt.toLocaleTimeString()}`}
          </span>
        </div>

        {/* Layer Controls & Refresh */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={() => setShowDefects(!showDefects)}
            style={{
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              border: showDefects ? '1px solid #3b82f6' : '1px solid #475569',
              background: showDefects ? '#1e3a8a' : '#1e293b',
              color: showDefects ? '#93c5fd' : '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            🛑 Defects ({roadtwins.length})
          </button>
          <button
            onClick={() => setShowTraffic(!showTraffic)}
            style={{
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              border: showTraffic ? '1px solid #f97316' : '1px solid #475569',
              background: showTraffic ? '#7c2d12' : '#1e293b',
              color: showTraffic ? '#fdba74' : '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            🚗 Traffic ({trafficObs.length})
          </button>
          <button
            onClick={() => setShowBottlenecks(!showBottlenecks)}
            style={{
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              border: showBottlenecks ? '1px solid #dc2626' : '1px solid #475569',
              background: showBottlenecks ? '#7f1d1d' : '#1e293b',
              color: showBottlenecks ? '#fca5a5' : '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            🚨 Bottlenecks ({bottlenecks.filter((b) => b.status === 'ACTIVE').length})
          </button>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            style={{
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              cursor: 'pointer',
              background: '#334155',
              color: '#f8fafc',
              border: 'none',
              fontWeight: 500,
            }}
          >
            {refreshing ? 'Syncing...' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div
          style={{
            backgroundColor: '#7f1d1d',
            color: '#fef2f2',
            padding: '10px 20px',
            fontSize: '12px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid #b91c1c',
          }}
        >
          <span>⚠️ {error}</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => loadData(true)}
              style={{
                background: '#dc2626',
                border: 'none',
                color: '#fff',
                padding: '4px 10px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Retry
            </button>
            <button
              onClick={() => setError(null)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#fca5a5',
                cursor: 'pointer',
                padding: '4px',
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Map Area */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {/* Loading Spinner Overlay */}
        {loading && (
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              padding: '20px 30px',
              borderRadius: '8px',
              zIndex: 1000,
              color: '#f8fafc',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ fontSize: '24px' }}>📡</div>
            <div style={{ fontSize: '14px', fontWeight: 600 }}>Loading UrbanSense GIS Telemetry...</div>
          </div>
        )}

        {/* Empty State Overlay */}
        {isEmpty && (
          <div
            style={{
              position: 'absolute',
              top: '20px',
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: 'rgba(15, 23, 42, 0.92)',
              border: '1px solid #334155',
              padding: '16px 24px',
              borderRadius: '8px',
              zIndex: 900,
              color: '#94a3b8',
              textAlign: 'center',
              maxWidth: '480px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ fontSize: '20px', marginBottom: '6px' }}>📭</div>
            <strong style={{ color: '#f8fafc', fontSize: '14px', display: 'block', marginBottom: '4px' }}>
              No GIS Telemetry Available Yet
            </strong>
            <span style={{ fontSize: '12px' }}>
              Stream road video or ingest bus sensing passes to populate road defect twins, real-time traffic
              aggregation, and 3-window persistent bottlenecks.
            </span>
          </div>
        )}

        {/* Leaflet Map */}
        <MapContainer center={[17.435, 78.37]} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AutoCenter coords={allCoords} />

          {/* Layer: RoadTwin Defects */}
          {showDefects &&
            roadtwins.map((rt) => (
              <RoadTwinMarker
                key={`rt-${rt.roadtwin_id}`}
                rt={rt}
                onSelect={(selected) => setSelectedEntity({ type: 'roadtwin', data: selected })}
              />
            ))}

          {/* Layer: Traffic Density & Flow */}
          {showTraffic &&
            trafficObs.map((obs) => (
              <TrafficMarker
                key={`trf-${obs.traffic_observation_id}`}
                obs={obs}
                onSelect={(selected) => setSelectedEntity({ type: 'traffic', data: selected })}
              />
            ))}

          {/* Layer: Active Bottlenecks */}
          {showBottlenecks &&
            bottlenecks
              .filter((b) => b.status === 'ACTIVE')
              .map((bn) => (
                <BottleneckMarker
                  key={`bn-${bn.bottleneck_id}`}
                  bn={bn}
                  onSelect={(selected) => setSelectedEntity({ type: 'bottleneck', data: selected })}
                />
              ))}
        </MapContainer>

        {/* Collapsible GIS Legend */}
        <MapLegend />

        {/* Interactive Detail Panel Drawer */}
        <DetailPanel
          entity={selectedEntity}
          onClose={() => setSelectedEntity(null)}
          allBottlenecks={bottlenecks}
        />
      </div>

      {/* Analytics & State Dashboard Panel */}
      <div
        style={{
          background: '#0f172a',
          color: '#f1f5f9',
          padding: '12px 16px',
          maxHeight: '220px',
          overflowY: 'auto',
          fontSize: '12px',
          borderTop: '1px solid #334155',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          {/* Left Table: RoadTwin Defects */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ color: '#93c5fd' }}>RoadTwin Distress Lifecycle</strong>
              <span style={{ fontSize: '10px', color: '#64748b' }}>Click row to inspect</span>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '6px' }}>
              <thead>
                <tr style={{ color: '#64748b', fontSize: '11px', textAlign: 'left' }}>
                  <th>Segment</th>
                  <th>State</th>
                  <th>Confidence</th>
                  <th>Evidence</th>
                  <th>Maintenance</th>
                </tr>
              </thead>
              <tbody>
                {roadtwins.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: '8px', color: '#64748b', textAlign: 'center' }}>
                      No defect twins registered
                    </td>
                  </tr>
                ) : (
                  roadtwins.map((rt) => (
                    <tr
                      key={rt.roadtwin_id}
                      onClick={() => setSelectedEntity({ type: 'roadtwin', data: rt })}
                      style={{
                        borderTop: '1px solid #1e293b',
                        cursor: 'pointer',
                        transition: 'background 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#1e293b')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <td style={{ padding: '3px 4px' }}>{rt.road_segment_id}</td>
                      <td style={{ padding: '3px 4px', color: stateColor(rt.current_state), fontWeight: 'bold' }}>
                        {rt.current_state}
                      </td>
                      <td style={{ padding: '3px 4px' }}>{(rt.aggregate_confidence * 100).toFixed(1)}%</td>
                      <td style={{ padding: '3px 4px' }}>
                        +{rt.positive_evidence_count} / -{rt.negative_evidence_count}
                      </td>
                      <td style={{ padding: '3px 4px' }}>{rt.maintenance_status}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Right Table: Traffic & Bottlenecks */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ color: '#fdba74' }}>Traffic Flow & Bottleneck Intelligence</strong>
              <span style={{ fontSize: '10px', color: '#64748b' }}>Click row to inspect</span>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '6px' }}>
              <thead>
                <tr style={{ color: '#64748b', fontSize: '11px', textAlign: 'left' }}>
                  <th>Segment</th>
                  <th>Density</th>
                  <th>Speed</th>
                  <th>Flow</th>
                  <th>Bottleneck</th>
                </tr>
              </thead>
              <tbody>
                {trafficObs.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: '8px', color: '#64748b', textAlign: 'center' }}>
                      No traffic observations recorded
                    </td>
                  </tr>
                ) : (
                  trafficObs.map((obs) => {
                    const bn = bottlenecks.find(
                      (b) => b.road_segment_id === obs.road_segment_id && b.status === 'ACTIVE'
                    );
                    return (
                      <tr
                        key={obs.traffic_observation_id}
                        onClick={() => setSelectedEntity({ type: 'traffic', data: obs })}
                        style={{
                          borderTop: '1px solid #1e293b',
                          cursor: 'pointer',
                          transition: 'background 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#1e293b')}
                        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                      >
                        <td style={{ padding: '3px 4px' }}>{obs.road_segment_id}</td>
                        <td style={{ padding: '3px 4px', color: congestionColor(obs.congestion_state) }}>
                          {obs.density.toFixed(1)} veh/km ({obs.congestion_state})
                        </td>
                        <td style={{ padding: '3px 4px' }}>
                          {obs.average_speed_kmh != null ? `${obs.average_speed_kmh.toFixed(1)} km/h` : 'UNKNOWN'}
                        </td>
                        <td style={{ padding: '3px 4px' }}>{obs.flow_rate.toFixed(0)} veh/h</td>
                        <td style={{ padding: '3px 4px' }}>
                          {bn ? (
                            <span
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedEntity({ type: 'bottleneck', data: bn });
                              }}
                              style={{ color: '#ef4444', fontWeight: 'bold' }}
                            >
                              🚨 ACTIVE ({bn.qualifying_window_count}/{bn.required_window_count})
                            </span>
                          ) : (
                            <span style={{ color: '#22c55e' }}>CLEAR</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

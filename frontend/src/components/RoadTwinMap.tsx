/**
 * UrbanSense AI — RoadTwin Map Component (Milestone 1)
 *
 * Renders road segments and their RoadTwin state on a Leaflet map.
 *
 * IMPORTANT:
 * - Reads data ONLY from the backend API (never PostgreSQL directly)
 * - Does NOT reconstruct RoadTwin rules
 * - Does NOT calculate confidence aggregation
 * - Does NOT perform map-match authority
 * - Does NOT implement RoadTwin state transitions
 *
 * PROTOTYPE / SIMULATED — showing Milestone 1 first vertical slice.
 */

import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import type { RoadTwinResponse } from '../client/types';
import { fetchRoadTwins } from '../client/api';
import 'leaflet/dist/leaflet.css';

const STATE_COLORS: Record<string, string> = {
  OBSERVED: '#f59e0b',      // amber — first observation
  CANDIDATE: '#3b82f6',     // blue — multiple observations
  CONFIRMED: '#ef4444',     // red — confirmed defect
  ACTIVE: '#dc2626',        // dark red
  UNDER_REPAIR: '#8b5cf6',  // purple
  REPAIRED: '#10b981',      // green
  CLOSED: '#6b7280',        // gray
};

function stateColor(state: string): string {
  return STATE_COLORS[state] ?? '#9ca3af';
}

function RoadTwinMarker({ rt }: { rt: RoadTwinResponse }) {
  if (!rt.segment_centroid_lat || !rt.segment_centroid_lon) return null;

  return (
    <CircleMarker
      center={[rt.segment_centroid_lat, rt.segment_centroid_lon]}
      radius={14}
      pathOptions={{
        color: stateColor(rt.current_state),
        fillColor: stateColor(rt.current_state),
        fillOpacity: 0.7,
        weight: 2,
      }}
    >
      <Popup>
        <div style={{ minWidth: '220px', fontFamily: 'monospace', fontSize: '12px' }}>
          <strong style={{ color: stateColor(rt.current_state) }}>
            🚦 {rt.current_state}
          </strong>
          <br />
          <b>Segment:</b> {rt.road_segment_id}
          <br />
          <b>Name:</b> {rt.segment_name ?? 'N/A'}
          <br />
          <hr style={{ margin: '4px 0' }} />
          <b>Aggregate Confidence:</b> {(rt.aggregate_confidence * 100).toFixed(1)}%
          <br />
          <b>Positive Evidence:</b> {rt.positive_evidence_count}
          <br />
          <b>Negative Evidence:</b> {rt.negative_evidence_count}
          <br />
          <hr style={{ margin: '4px 0' }} />
          <b>Freshness:</b> {rt.freshness_status}
          <br />
          <b>Verification:</b> {rt.verification_status}
          <br />
          <hr style={{ margin: '4px 0' }} />
          <b>First seen:</b>{' '}
          {new Date(rt.first_seen_at).toLocaleString()}
          <br />
          <b>Last seen:</b>{' '}
          {new Date(rt.last_seen_at).toLocaleString()}
          <br />
          <hr style={{ margin: '4px 0' }} />
          <small>
            <b>RoadTwin ID:</b>
            <br />
            {rt.roadtwin_id}
            <br />
            <b>Last Event:</b>
            <br />
            {rt.last_event_id ?? 'N/A'}
          </small>
          <hr style={{ margin: '4px 0' }} />
          <small style={{ color: '#f59e0b' }}>
            ⚠ PROTOTYPE / SIMULATED data (Milestone 1)
          </small>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function AutoCenter({ roadtwins }: { roadtwins: RoadTwinResponse[] }) {
  const map = useMap();
  useEffect(() => {
    const withCoords = roadtwins.filter(
      (rt) => rt.segment_centroid_lat && rt.segment_centroid_lon
    );
    if (withCoords.length > 0) {
      const lat = withCoords[0].segment_centroid_lat!;
      const lon = withCoords[0].segment_centroid_lon!;
      map.setView([lat, lon], 15);
    }
  }, [roadtwins, map]);
  return null;
}

export function RoadTwinMap() {
  const [roadtwins, setRoadtwins] = useState<RoadTwinResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const load = async () => {
    try {
      setLoading(true);
      const data = await fetchRoadTwins();
      setRoadtwins(data);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(`Failed to load RoadTwin data: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // Auto-refresh every 10 seconds
    const interval = setInterval(load, 10_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div
        style={{
          background: '#1e293b',
          color: '#f1f5f9',
          padding: '12px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <strong style={{ fontSize: '18px' }}>🛰 UrbanSense AI</strong>
          <span
            style={{
              marginLeft: '12px',
              background: '#f59e0b',
              color: '#000',
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '11px',
            }}
          >
            PROTOTYPE / SIMULATED — Milestone 1
          </span>
        </div>
        <div style={{ fontSize: '12px', color: '#94a3b8' }}>
          {loading ? '⟳ Loading...' : `${roadtwins.length} RoadTwin(s) · Refreshed: ${lastRefresh.toLocaleTimeString()}`}
          <button
            onClick={load}
            style={{
              marginLeft: '12px',
              background: '#334155',
              color: '#f1f5f9',
              border: 'none',
              padding: '4px 10px',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          style={{
            background: '#fee2e2',
            color: '#991b1b',
            padding: '8px 16px',
            fontSize: '13px',
          }}
        >
          ⚠ {error} — Is the backend running? (uvicorn backend.app.main:app)
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          background: '#0f172a',
          color: '#94a3b8',
          padding: '6px 16px',
          display: 'flex',
          gap: '16px',
          fontSize: '12px',
        }}
      >
        {Object.entries(STATE_COLORS).map(([state, color]) => (
          <span key={state}>
            <span style={{ color, marginRight: '4px' }}>●</span>
            {state}
          </span>
        ))}
      </div>

      {/* Map */}
      <div style={{ flex: 1 }}>
        <MapContainer
          center={[17.4435, 78.3772]}
          zoom={14}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AutoCenter roadtwins={roadtwins} />
          {roadtwins.map((rt) => (
            <RoadTwinMarker key={rt.roadtwin_id} rt={rt} />
          ))}
        </MapContainer>
      </div>

      {/* Table panel */}
      {roadtwins.length > 0 && (
        <div
          style={{
            background: '#1e293b',
            color: '#f1f5f9',
            padding: '12px 16px',
            maxHeight: '180px',
            overflowY: 'auto',
            fontSize: '12px',
          }}
        >
          <strong>RoadTwin States</strong>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '8px' }}>
            <thead>
              <tr style={{ color: '#64748b' }}>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Segment</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>State</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Confidence</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Evidence+</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Last Event</th>
              </tr>
            </thead>
            <tbody>
              {roadtwins.map((rt) => (
                <tr key={rt.roadtwin_id} style={{ borderTop: '1px solid #334155' }}>
                  <td style={{ padding: '4px 8px' }}>{rt.road_segment_id}</td>
                  <td style={{ padding: '4px 8px', color: stateColor(rt.current_state) }}>
                    {rt.current_state}
                  </td>
                  <td style={{ padding: '4px 8px' }}>
                    {(rt.aggregate_confidence * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: '4px 8px' }}>{rt.positive_evidence_count}</td>
                  <td style={{ padding: '4px 8px', fontFamily: 'monospace', fontSize: '10px' }}>
                    {rt.last_event_id?.substring(0, 16) ?? 'N/A'}...
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

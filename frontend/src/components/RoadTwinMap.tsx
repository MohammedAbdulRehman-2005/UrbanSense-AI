/**
 * UrbanSense AI — RoadTwin & Traffic Intelligence GIS Map (Milestones 1–5)
 *
 * Renders:
 * - RoadTwin defect states (OBSERVED, CANDIDATE, CONFIRMED, MAINTENANCE_PENDING, etc.)
 * - Traffic Intelligence layer (vehicle counts, fleet speed, density, flow rate, congestion)
 * - Persistent Bottleneck layer (rolling 3-window condition: high density + low speed)
 *
 * IMPORTANT ARCHITECTURAL RULES:
 * - Consumes data ONLY from the backend read API (never PostgreSQL directly)
 * - Does NOT calculate density, flow, congestion, or bottleneck persistence in React
 * - Does NOT duplicate backend threshold constants in the frontend
 * - Explicit layer toggles allow separating defect maintenance from traffic analytics
 */

import React, { useEffect, useState } from 'react';
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

function RoadTwinMarker({ rt }: { rt: RoadTwinResponse }) {
  if (!rt.segment_centroid_lat || !rt.segment_centroid_lon) return null;

  return (
    <CircleMarker
      center={[rt.segment_centroid_lat, rt.segment_centroid_lon]}
      radius={13}
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
          <hr style={{ margin: '4px 0' }} />
          <b>Confidence:</b> {(rt.aggregate_confidence * 100).toFixed(1)}%
          <br />
          <b>Evidence (+/-):</b> +{rt.positive_evidence_count} / -{rt.negative_evidence_count}
          <br />
          <b>Buses:</b> {rt.independent_bus_count}
          <br />
          <b>Maintenance:</b> {rt.maintenance_status}
          <br />
          <b>Verification:</b> {rt.verification_status}
          {rt.active_episode_id && (
            <>
              <br />
              <b>Episode:</b> {rt.active_episode_id.substring(0, 8)}...
            </>
          )}
        </div>
      </Popup>
    </CircleMarker>
  );
}

function TrafficMarker({ obs }: { obs: TrafficObservationResponse }) {
  if (!obs.centroid_lat || !obs.centroid_lon) return null;

  // Offset slightly so it does not perfectly overlap with defect marker
  const lat = obs.centroid_lat + 0.0005;
  const lon = obs.centroid_lon + 0.0005;

  return (
    <CircleMarker
      center={[lat, lon]}
      radius={16}
      pathOptions={{
        color: congestionColor(obs.congestion_state),
        fillColor: congestionColor(obs.congestion_state),
        fillOpacity: 0.5,
        weight: 2,
        dashArray: '3, 3',
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
          <hr style={{ margin: '4px 0' }} />
          <b>Unique Vehicles:</b> {obs.vehicle_count}
          <br />
          <b>Density:</b> {obs.density.toFixed(1)} veh/km
          <br />
          <b>Flow Rate:</b> {obs.flow_rate.toFixed(0)} veh/h
          <br />
          <b>Fleet Speed:</b>{' '}
          {obs.average_speed_kmh != null ? `${obs.average_speed_kmh.toFixed(1)} km/h` : 'UNKNOWN'}
          <br />
          <hr style={{ margin: '4px 0' }} />
          <b>Classes:</b>{' '}
          {Object.entries(obs.vehicle_class_counts)
            .map(([cls, count]) => `${cls}: ${count}`)
            .join(', ')}
          <br />
          <b>Window:</b>{' '}
          {new Date(obs.window_start).toLocaleTimeString()} –{' '}
          {new Date(obs.window_end).toLocaleTimeString()}
        </div>
      </Popup>
    </CircleMarker>
  );
}

function BottleneckMarker({ bn }: { bn: BottleneckResponse }) {
  if (!bn.centroid_lat || !bn.centroid_lon) return null;

  // Offset position to stand out prominently
  const lat = bn.centroid_lat - 0.0006;
  const lon = bn.centroid_lon - 0.0006;

  return (
    <CircleMarker
      center={[lat, lon]}
      radius={20}
      pathOptions={{
        color: '#dc2626',
        fillColor: '#7c3aed',
        fillOpacity: 0.8,
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
          <hr style={{ margin: '4px 0' }} />
          <b>Density Condition:</b>{' '}
          <span style={{ color: '#ef4444', fontWeight: 'bold' }}>{bn.density_condition}</span>
          <br />
          <b>Speed Condition:</b>{' '}
          <span style={{ color: '#ef4444', fontWeight: 'bold' }}>{bn.speed_condition}</span>
          <br />
          <b>Rolling Windows:</b>{' '}
          <span style={{ fontWeight: 'bold' }}>
            {bn.qualifying_window_count} of {bn.required_window_count} required
          </span>
          <br />
          <hr style={{ margin: '4px 0' }} />
          <b>Window Span:</b>
          <br />
          {new Date(bn.first_qualifying_window_start).toLocaleTimeString()} –{' '}
          {new Date(bn.latest_qualifying_window_end).toLocaleTimeString()}
          <br />
          <small>
            <b>Evidence IDs:</b> {bn.evidence_window_ids.length} windows
          </small>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function AutoCenter({
  coords,
}: {
  coords: Array<[number, number]>;
}) {
  const map = useMap();
  useEffect(() => {
    if (coords.length > 0) {
      map.setView(coords[0], 14);
    }
  }, [coords, map]);
  return null;
}

export function RoadTwinMap() {
  const [roadtwins, setRoadtwins] = useState<RoadTwinResponse[]>([]);
  const [trafficObs, setTrafficObs] = useState<TrafficObservationResponse[]>([]);
  const [bottlenecks, setBottlenecks] = useState<BottleneckResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Layer toggles
  const [showDefects, setShowDefects] = useState(true);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showBottlenecks, setShowBottlenecks] = useState(true);

  const loadData = async () => {
    try {
      const [rtData, trfData, bnData] = await Promise.all([
        fetchRoadTwins().catch(() => []),
        fetchTraffic().catch(() => []),
        fetchBottlenecks().catch(() => []),
      ]);
      setRoadtwins(rtData);
      setTrafficObs(trfData);
      setBottlenecks(bnData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const allCoords: Array<[number, number]> = [];
  roadtwins.forEach((rt) => {
    if (rt.segment_centroid_lat && rt.segment_centroid_lon) {
      allCoords.push([rt.segment_centroid_lat, rt.segment_centroid_lon]);
    }
  });
  trafficObs.forEach((trf) => {
    if (trf.centroid_lat && trf.centroid_lon) {
      allCoords.push([trf.centroid_lat, trf.centroid_lon]);
    }
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' }}>
      {/* Header bar */}
      <div
        style={{
          background: '#0f172a',
          color: '#f8fafc',
          padding: '12px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid #334155',
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
            UrbanSense AI — RoadTwin & Traffic Intelligence GIS
          </h1>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
            Multi-Domain Mobility Twin: Defects + Vehicle Tracking + Rolling 3-Window Bottlenecks
          </span>
        </div>

        {/* Layer Controls */}
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
            }}
          >
            🚨 Bottlenecks ({bottlenecks.filter((b) => b.status === 'ACTIVE').length})
          </button>
          <button
            onClick={loadData}
            style={{
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              cursor: 'pointer',
              background: '#334155',
              color: '#f8fafc',
              border: 'none',
            }}
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Map Area */}
      <div style={{ flex: 1, position: 'relative' }}>
        <MapContainer
          center={[17.4350, 78.3700]}
          zoom={13}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AutoCenter coords={allCoords} />

          {/* Layer: RoadTwin Defects */}
          {showDefects &&
            roadtwins.map((rt) => (
              <RoadTwinMarker key={`rt-${rt.roadtwin_id}`} rt={rt} />
            ))}

          {/* Layer: Traffic Density & Flow */}
          {showTraffic &&
            trafficObs.map((obs) => (
              <TrafficMarker key={`trf-${obs.traffic_observation_id}`} obs={obs} />
            ))}

          {/* Layer: Active Bottlenecks */}
          {showBottlenecks &&
            bottlenecks
              .filter((b) => b.status === 'ACTIVE')
              .map((bn) => (
                <BottleneckMarker key={`bn-${bn.bottleneck_id}`} bn={bn} />
              ))}
        </MapContainer>
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
            <strong style={{ color: '#93c5fd' }}>RoadTwin Distress Lifecycle</strong>
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
                {roadtwins.map((rt) => (
                  <tr key={rt.roadtwin_id} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={{ padding: '3px 4px' }}>{rt.road_segment_id}</td>
                    <td style={{ padding: '3px 4px', color: stateColor(rt.current_state), fontWeight: 'bold' }}>
                      {rt.current_state}
                    </td>
                    <td style={{ padding: '3px 4px' }}>{(rt.aggregate_confidence * 100).toFixed(1)}%</td>
                    <td style={{ padding: '3px 4px' }}>+{rt.positive_evidence_count} / -{rt.negative_evidence_count}</td>
                    <td style={{ padding: '3px 4px' }}>{rt.maintenance_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Right Table: Traffic & Bottlenecks */}
          <div>
            <strong style={{ color: '#fdba74' }}>Traffic Flow & Bottleneck Intelligence</strong>
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
                {trafficObs.map((obs) => {
                  const bn = bottlenecks.find(
                    (b) => b.road_segment_id === obs.road_segment_id && b.status === 'ACTIVE'
                  );
                  return (
                    <tr key={obs.traffic_observation_id} style={{ borderTop: '1px solid #1e293b' }}>
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
                          <span style={{ color: '#ef4444', fontWeight: 'bold' }}>
                            🚨 ACTIVE ({bn.qualifying_window_count}/{bn.required_window_count})
                          </span>
                        ) : (
                          <span style={{ color: '#22c55e' }}>CLEAR</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

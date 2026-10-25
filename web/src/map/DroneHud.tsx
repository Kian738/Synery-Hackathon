import { memo } from "react";
import "./DroneHud.css";

export interface GeoBuilding {
  building_id: string;
  name: string;
  lat: number;
  lon: number;
  zoom_hint: number;
  campus?: string;
  height_m?: number;
  has_indoor: boolean;
  floors: string | number;
  rooms?: string | number;
  spaces?: string | number;
}

export interface Telemetry {
  altM: number;
  pitchDeg: number;
  bearingDeg: number;
  lat: number;
  lon: number;
  zoom: number;
}

interface DroneHudProps {
  telemetry: Telemetry;
  activeCampus: string;
  onSelectCampus: (campusId: string) => void;
  orbiting: boolean;
  onToggleOrbit: () => void;
  selectedBuilding: GeoBuilding | null;
  onClearSelection: () => void;
  onEngageIndoor: (b: GeoBuilding) => void;
}

const CAMPUSES = [
  { id: "garching", label: "TUM Garching (CIT)", sub: "Campus North" },
  { id: "munich_center", label: "TUM Main Campus", sub: "Stammgelände" },
  { id: "weihenstephan", label: "Weihenstephan", sub: "Freising" },
];

function bearingToDirection(bearing: number): string {
  const norm = ((bearing % 360) + 360) % 360;
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const idx = Math.round(norm / 22.5) % 16;
  return `${Math.round(norm)}° ${dirs[idx]}`;
}

export const DroneHud = memo(function DroneHud({
  telemetry,
  activeCampus,
  onSelectCampus,
  orbiting,
  onToggleOrbit,
  selectedBuilding,
  onClearSelection,
  onEngageIndoor,
}: DroneHudProps) {
  return (
    <div className="drone-hud">
      {/* 4 Corner Crosshairs */}
      <div className="hud-corner hud-corner-tl" />
      <div className="hud-corner hud-corner-tr" />
      <div className="hud-corner hud-corner-bl" />
      <div className="hud-corner hud-corner-br" />

      {/* Top Telemetry Header */}
      <header className="hud-header">
        <div className="hud-pill">
          <span className="hud-rec-dot" />
          <span>AUTONOMOUS RECON // DRONE-01</span>
        </div>

        <div className="hud-telemetry-cluster">
          <div className="hud-stat-item">
            <span>ALTITUDE</span>
            <b>{telemetry.altM}M AGL</b>
          </div>
          <div className="hud-stat-item">
            <span>PITCH</span>
            <b>{Math.round(telemetry.pitchDeg)}° OBLIQUE</b>
          </div>
          <div className="hud-stat-item">
            <span>HEADING</span>
            <b>{bearingToDirection(telemetry.bearingDeg)}</b>
          </div>
          <div className="hud-stat-item">
            <span>GPS COORDS</span>
            <b>{telemetry.lat.toFixed(4)}°N, {telemetry.lon.toFixed(4)}°E</b>
          </div>
        </div>
      </header>

      {/* Campus Quick-Switch Bar */}
      <nav className="hud-campus-switch drone-hud-interactive" aria-label="Campus Selection">
        {CAMPUSES.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`hud-campus-btn ${activeCampus === c.id ? "active" : ""}`}
            onClick={() => onSelectCampus(c.id)}
            title={`Fly drone to ${c.label}`}
          >
            <span>📍</span>
            <span>{c.label}</span>
          </button>
        ))}
      </nav>

      {/* Bottom-Right Controls */}
      <div className="hud-camera-controls drone-hud-interactive">
        <button
          type="button"
          className={`hud-orbit-btn ${orbiting ? "orbiting" : ""}`}
          onClick={onToggleOrbit}
          title="Toggle autonomous drone orbit"
        >
          <span className="hud-radar-spinner" />
          <span>{orbiting ? "ORBIT ACTIVE" : "ENGAGE ORBIT"}</span>
        </button>
      </div>

      {/* Target Lock Card */}
      {selectedBuilding && (
        <aside
          className="hud-target-card drone-hud-interactive"
          aria-label={`Target Lock: ${selectedBuilding.name}`}
        >
          <div className="hud-target-header">
            <div className="hud-target-badge">
              <span>●</span>
              <span>INDOOR DIGITAL TWIN ONLINE</span>
            </div>
            <button
              type="button"
              className="hud-target-close"
              onClick={onClearSelection}
              aria-label="Deselect building"
            >
              ✕
            </button>
          </div>

          <h2 className="hud-target-title">{selectedBuilding.name}</h2>

          <div className="hud-target-metrics">
            <div className="hud-metric-box">
              <span>FLOORS</span>
              <b>{selectedBuilding.floors}</b>
            </div>
            <div className="hud-metric-box">
              <span>ROOMS</span>
              <b>{selectedBuilding.rooms ?? selectedBuilding.spaces ?? "—"}</b>
            </div>
            <div className="hud-metric-box">
              <span>3D HEIGHT</span>
              <b>{selectedBuilding.height_m ?? 20}M</b>
            </div>
          </div>

          <button
            type="button"
            className="hud-engage-btn"
            onClick={() => onEngageIndoor(selectedBuilding)}
          >
            <span>DIVE INTO BUILDING ↓</span>
          </button>

          <p className="hud-target-subtext">
            Click to initiate high-speed dive or scroll in to enter.
          </p>
        </aside>
      )}
    </div>
  );
});

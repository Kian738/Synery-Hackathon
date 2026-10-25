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
  { id: "garching", label: "Garching" },
  { id: "munich_center", label: "Main campus" },
  { id: "weihenstephan", label: "Weihenstephan" },
];

function heading(bearing: number): string {
  const norm = ((bearing % 360) + 360) % 360;
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round(norm / 45) % 8];
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
      <nav className="hud-campus-switch hud-interactive hud-material" aria-label="Campus">
        {CAMPUSES.map((c) => (
          <button
            key={c.id}
            type="button"
            className="hud-campus-btn"
            aria-pressed={activeCampus === c.id}
            onClick={() => onSelectCampus(c.id)}
          >
            {c.label}
          </button>
        ))}
      </nav>

      <div className="hud-camera-controls hud-interactive">
        <div className="hud-compass hud-material" role="img" aria-label={`Facing ${heading(telemetry.bearingDeg)}, ${Math.round(telemetry.pitchDeg)}° tilt`}>
          <svg viewBox="0 0 24 24" width="20" height="20" style={{ transform: `rotate(${-telemetry.bearingDeg}deg)` }} aria-hidden>
            <path d="M12 3 16 13H8z" fill="var(--k-accent)" />
            <path d="M12 21 8 13h8z" fill="var(--k-mute)" />
          </svg>
          <span>{heading(telemetry.bearingDeg)}</span>
        </div>
        <button
          type="button"
          className="hud-orbit-btn hud-material"
          aria-pressed={orbiting}
          onClick={onToggleOrbit}
        >
          {orbiting ? "Stop turning" : "Turn slowly"}
        </button>
      </div>

      {selectedBuilding ? (
        <aside className="hud-sheet hud-interactive hud-material" aria-label={selectedBuilding.name}>
          <header>
            <div>
              <small>{selectedBuilding.campus ? selectedBuilding.campus.replace("_", " ") : "Building"}</small>
              <h2>{selectedBuilding.name}</h2>
            </div>
            <button type="button" className="hud-close" onClick={onClearSelection} aria-label="Close">
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            </button>
          </header>
          <dl className="hud-stats">
            <div><dt>Floors</dt><dd>{selectedBuilding.floors}</dd></div>
            <div><dt>Rooms</dt><dd>{selectedBuilding.rooms ?? selectedBuilding.spaces ?? "—"}</dd></div>
            <div><dt>Height</dt><dd>{selectedBuilding.height_m ?? 20} m</dd></div>
          </dl>
          <button type="button" className="hud-engage-btn" onClick={() => onEngageIndoor(selectedBuilding)}>
            Go inside
          </button>
        </aside>
      ) : (
        <p className="hud-hint hud-material" role="status">Tap a building, or zoom in to step inside.</p>
      )}
    </div>
  );
});

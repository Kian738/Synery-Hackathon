import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { preloadBuilding } from "../lib/api";
import { DroneHud, type GeoBuilding, type Telemetry } from "./DroneHud";
import { CampusRoutePanel } from "./CampusRoutePanel";
import "./MapView.css";

const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri, Earthstar Geographics",
    },
  },
  layers: [
    {
      id: "imagery",
      type: "raster",
      source: "imagery",
    },
  ],
};

const CAMPUS_PRESETS: Record<string, { coords: [number, number]; zoom: number; pitch: number; bearing: number }> = {
  garching: {
    coords: [11.668203, 48.262423],
    zoom: 16.5,
    pitch: 65,
    bearing: -20,
  },
  munich_center: {
    coords: [11.567500, 48.149200],
    zoom: 16.2,
    pitch: 65,
    bearing: 35,
  },
  weihenstephan: {
    coords: [11.726692, 48.395714],
    zoom: 16.5,
    pitch: 65,
    bearing: 10,
  },
};

const ENTER_ZOOM_MARGIN = 1.3;
const ENTER_RADIUS_M = 75;

function distanceM(aLat: number, aLon: number, bLat: number, bLon: number) {
  const dLat = (bLat - aLat) * 111320;
  const dLon = (bLon - aLon) * 111320 * Math.cos((aLat * Math.PI) / 180);
  return Math.hypot(dLat, dLon);
}

function truncate(str: string, max = 22): string {
  return str.length > max ? `${str.slice(0, max - 1)}…` : str;
}

export default function MapView() {
  const navigate = useNavigate();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const [buildings, setBuildings] = useState<GeoBuilding[]>([]);
  const [selected, setSelected] = useState<GeoBuilding | null>(null);
  const [activeCampus, setActiveCampus] = useState<string>("garching");
  const [orbiting, setOrbiting] = useState<boolean>(false);
  const [diving, setDiving] = useState<boolean>(false);
  const divingRef = useRef<boolean>(false);

  const [telemetry, setTelemetry] = useState<Telemetry>({
    altM: 180,
    pitchDeg: 65,
    bearingDeg: -20,
    lat: 48.2624,
    lon: 11.6682,
    zoom: 16.5,
  });

  // High-speed dive-in transition
  const enterIndoor = useCallback(
    (b: GeoBuilding) => {
      if (divingRef.current) return;
      divingRef.current = true;
      setDiving(true);
      setOrbiting(false);

      const map = mapRef.current;
      if (map) {
        map.flyTo({
          center: [b.lon, b.lat],
          zoom: 19.5,
          pitch: 80,
          duration: 1100,
          curve: 1.2,
          speed: 1.0,
          easing: (t) => t * t, // smooth quadratic acceleration into the dive
          essential: true,
        });
      }

      window.setTimeout(() => {
        navigate(`/?building=${encodeURIComponent(b.building_id)}&from=map`);
      }, 850);
    },
    [navigate],
  );

  // Preload Three.js components and default building immediately on mount
  useEffect(() => {
    void import("../components/Building3D");
    preloadBuilding("osm-way27917482");
  }, []);

  // Load building list
  useEffect(() => {
    fetch("/api/buildings/georef")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: GeoBuilding[]) => {
        setBuildings(data);
        // Preload all buildings on the active campus from further away
        data.filter((b) => b.campus === "garching").forEach((b) => preloadBuilding(b.building_id));
      })
      .catch(() => {});
  }, []);

  // Initialize MapLibre in 3D Drone Mode
  useEffect(() => {
    if (!container.current) return;

    const initial = CAMPUS_PRESETS.garching;
    const map = new maplibregl.Map({
      container: container.current,
      style: SATELLITE_STYLE,
      center: initial.coords,
      zoom: initial.zoom,
      pitch: initial.pitch,
      bearing: initial.bearing,
      maxPitch: 85,
      canvasContextAttributes: { antialias: true },  // maplibre 6: the WebGL flag lives here, not on the map options
      dragRotate: true,
      pitchWithRotate: true,
      touchPitch: true,
      fadeDuration: 200,
    });
    mapRef.current = map;

    // Smooth wheel zoom rate
    map.scrollZoom.setWheelZoomRate(1 / 450);

    // Throttle React telemetry re-renders to ~12 FPS so WebGL runs at maximum native FPS
    let lastTelemetryTime = 0;
    const updateTelemetry = () => {
      const now = performance.now();
      const center = map.getCenter();
      const zoom = map.getZoom();

      if (now - lastTelemetryTime > 80) {
        lastTelemetryTime = now;
        const altM = Math.max(15, Math.round(160000 / Math.pow(2, zoom - 6)));

        setTelemetry({
          altM,
          pitchDeg: map.getPitch(),
          bearingDeg: map.getBearing(),
          lat: center.lat,
          lon: center.lng,
          zoom,
        });
      }

      // 1. Background preload from further away (within 850m)
      buildings.forEach((b) => {
        if (distanceM(center.lat, center.lng, b.lat, b.lon) <= 850) {
          preloadBuilding(b.building_id);
        }
      });

      // 2. When in "good distance" (zoom >= 17.2 and within 100m), show interior
      if (!divingRef.current && zoom >= 17.2) {
        const target = buildings.find(
          (b) => distanceM(center.lat, center.lng, b.lat, b.lon) <= 100,
        );
        if (target) {
          enterIndoor(target);
        }
      }
    };
    map.on("move", updateTelemetry);

    // Zoom-in auto-dive threshold when zoom gesture completes
    map.on("zoomend", () => {
      if (divingRef.current) return;
      const center = map.getCenter();
      const zoom = map.getZoom();
      const target = buildings.find(
        (b) => zoom >= 17.0 && distanceM(center.lat, center.lng, b.lat, b.lon) <= ENTER_RADIUS_M,
      );
      if (target) {
        enterIndoor(target);
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [buildings, enterIndoor]);

  // Add 3D Target Markers with Radar Ping
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !buildings.length) return;

    const markers = buildings.map((b) => {
      const el = document.createElement("div");
      el.className = `fw-drone-marker ${selected?.building_id === b.building_id ? "selected" : ""}`;
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", `Select ${b.name}`);

      el.innerHTML = `
        <div class="fw-drone-marker-pin">
          <span class="fw-marker-dot"></span>
          <span class="fw-marker-tag">${truncate(b.name)}</span>
        </div>
      `;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        setSelected(b);
        preloadBuilding(b.building_id);
        setOrbiting(false);
        map.flyTo({
          center: [b.lon, b.lat],
          zoom: 17.8,
          pitch: 70,
          duration: 1600,
          curve: 1.35,
          speed: 0.85,
          easing: (t) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t),
          essential: true,
        });
      });

      return new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([b.lon, b.lat]).addTo(map);
    });

    return () => {
      markers.forEach((m) => m.remove());
    };
  }, [buildings, selected]);

  // Autonomous Drone Drift Orbit Loop
  useEffect(() => {
    let animId: number;
    let lastTime = performance.now();

    const orbitStep = (now: number) => {
      const map = mapRef.current;
      if (orbiting && map && !divingRef.current) {
        const delta = Math.min((now - lastTime) / 1000, 0.1);
        const currentBearing = map.getBearing();
        // 1.8 degrees per second slow panoramic rotation
        map.setBearing(currentBearing + 1.8 * delta);
      }
      lastTime = now;
      if (orbiting) {
        animId = requestAnimationFrame(orbitStep);
      }
    };

    if (orbiting) {
      animId = requestAnimationFrame(orbitStep);
    }

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [orbiting]);

  // Fast-travel flyover to selected campus
  const handleSelectCampus = useCallback((campusId: string) => {
    const target = CAMPUS_PRESETS[campusId];
    if (!target) return;
    setActiveCampus(campusId);
    setSelected(null);

    const map = mapRef.current;
    if (map) {
      map.flyTo({
        center: target.coords,
        zoom: target.zoom,
        pitch: target.pitch,
        bearing: target.bearing,
        duration: 2400,
        curve: 1.4,
        speed: 0.85,
        easing: (t) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t),
        essential: true,
      });
    }
  }, []);

  return (
    <div className={`fw-map-shell ${diving ? "fw-map-diving" : ""}`}>
      <div ref={container} className="fw-map-canvas" />

      <CampusRoutePanel mapRef={mapRef} buildings={buildings} selected={selected} />

      {/* Aerospace Drone HUD Component */}
      <DroneHud
        telemetry={telemetry}
        activeCampus={activeCampus}
        onSelectCampus={handleSelectCampus}
        orbiting={orbiting}
        onToggleOrbit={() => setOrbiting((prev) => !prev)}
        selectedBuilding={selected}
        onClearSelection={() => setSelected(null)}
        onEngageIndoor={enterIndoor}
      />
    </div>
  );
}

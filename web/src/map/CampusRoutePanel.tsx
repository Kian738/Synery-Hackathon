import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { useNavigate, useSearchParams } from "react-router";
import * as maplibregl from "maplibre-gl";
import type { GeoBuilding } from "./DroneHud";
import {
  arrivalLink, clearJourney, clearRoute, fallbackSteps, indoorLink, journeyIndex, loadRoute, nextLeg, saveRoute, setJourneyIndex,
  type CampusResult, type IndoorLeg, type Mode, type OutdoorLeg, type Query,
} from "../journey/journey";
import "./CampusRoutePanel.css";

type Candidate = { id: string; label: string };

const MODES: { id: Mode; icon: string; label: string }[] = [
  { id: "foot", icon: "🚶", label: "Walk" },
  { id: "wheelchair", icon: "♿", label: "Wheelchair" },
  { id: "bike", icon: "🚲", label: "Bike" },
  { id: "car", icon: "🚗", label: "Car" },
];
const modeIcon = (mode?: string) => MODES.find((m) => m.id === mode)?.icon ?? "🚶";
const modeVerb: Record<Mode, string> = { foot: "on foot", wheelchair: "by wheelchair", bike: "by bike", car: "by car" };

const SOURCE = "fw-campus-route-src";
// Below the map's dive-in zoom (17), so framing the route or a turn never drops into a building by itself.
const FIT_MAX_ZOOM = 16.5;
const GUIDE_ZOOM = 16.6;

type Props = {
  mapRef: RefObject<maplibregl.Map | null>;
  buildings: GeoBuilding[];
  selected: GeoBuilding | null;
};

const bearingBetween = (from: [number, number], to: [number, number]) => {
  const dLon = ((to[0] - from[0]) * Math.PI) / 180 * Math.cos((from[1] * Math.PI) / 180);
  const dLat = ((to[1] - from[1]) * Math.PI) / 180;
  return ((Math.atan2(dLon, dLat) * 180) / Math.PI + 360) % 360;
};

export function CampusRoutePanel({ mapRef, buildings, selected }: Props) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const walkMode = searchParams.get("walk") === "1"; // the outdoor walk is only guided on the map when asked for
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<Query>({ from_building: "", to_building: "", from_room: "", to_room: "", mode: "foot" });
  const [result, setResult] = useState<CampusResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ask, setAsk] = useState<{ which: "from" | "to"; candidates: Candidate[] } | null>(null);
  const [journey, setJourney] = useState<number | null>(null); // index of the leg being guided, null when not guiding
  const [stepIndex, setStepIndex] = useState(0);
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const youMarker = useRef<maplibregl.Marker | null>(null);

  const clearDrawing = useCallback(() => {
    markers.current.forEach((m) => m.remove());
    markers.current = [];
    youMarker.current?.remove();
    youMarker.current = null;
    const map = mapRef.current;
    if (map?.getLayer(SOURCE)) map.removeLayer(SOURCE);
    if (map?.getLayer(`${SOURCE}-casing`)) map.removeLayer(`${SOURCE}-casing`);
    if (map?.getSource(SOURCE)) map.removeSource(SOURCE);
  }, [mapRef]);

  const fit = useCallback((points: [number, number][]) => {
    const map = mapRef.current;
    if (!map || !points.length) return;
    const bounds = points.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(points[0], points[0]));
    map.fitBounds(bounds, { padding: { top: 120, bottom: 120, left: 420, right: 80 }, maxZoom: FIT_MAX_ZOOM, pitch: 45, duration: 1400 });
  }, [mapRef]);

  const draw = useCallback((r: CampusResult, fitToRoute = true) => {
    const map = mapRef.current;
    if (!map) return;
    const render = () => {
      clearDrawing();
      const outdoor = r.legs.find((l): l is OutdoorLeg => l.kind === "outdoor")!;
      map.addSource(SOURCE, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: outdoor.polyline } } });
      map.addLayer({ id: `${SOURCE}-casing`, type: "line", source: SOURCE, paint: { "line-color": "#080c14", "line-width": 9, "line-opacity": 0.8 }, layout: { "line-cap": "round", "line-join": "round" } });
      map.addLayer({
        id: SOURCE, type: "line", source: SOURCE,
        paint: { "line-color": "#ffd45c", "line-width": 5, ...(outdoor.estimated ? { "line-dasharray": [1.5, 1.5] } : {}) },
        layout: { "line-cap": "round", "line-join": "round" },
      });
      const pin = (lngLat: [number, number], text: string, cls: string) => {
        const el = document.createElement("div");
        el.className = `fw-route-pin ${cls}`;
        el.textContent = text;
        markers.current.push(new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat(lngLat).addTo(map));
      };
      pin([outdoor.from.lon, outdoor.from.lat], "EXIT", "exit");
      pin([outdoor.to.lon, outdoor.to.lat], "ENTRANCE", "entry");
      if (fitToRoute) fit(outdoor.polyline.length ? outdoor.polyline : [[outdoor.from.lon, outdoor.from.lat], [outdoor.to.lon, outdoor.to.lat]]);
    };
    if (map.isStyleLoaded()) render(); else map.once("load", render);
  }, [mapRef, clearDrawing, fit]);

  // The map is created after this panel mounts and again when the building list arrives, and each new map starts
  // empty. Follow the live instance so the route, pins and guide are always drawn on the map that is on screen.
  useEffect(() => {
    const watch = window.setInterval(() => setMapInstance((old) => (mapRef.current !== old ? mapRef.current : old)), 150);
    return () => window.clearInterval(watch);
  }, [mapRef]);

  // Back from an indoor leg: the route, the question and the position in the trip are kept for the session.
  const restoredTrip = useRef(false);
  useEffect(() => {
    const saved = loadRoute();
    if (saved) {
      const index = journeyIndex();
      setQuery(saved.query); setResult(saved.result); setOpen(true);
      if (index !== null && index < saved.result.legs.length) setJourney(index);
      restoredTrip.current = index !== null;
    }
    return clearDrawing;
  }, [clearDrawing]);

  useEffect(() => {
    if (!mapInstance || !result) return;
    draw(result, !restoredTrip.current && journey === null);
  }, [mapInstance]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch: Partial<Query>) => setQuery((q) => ({ ...q, ...patch }));

  const find = async (q: Query = query) => {
    setBusy(true); setError(null); setAsk(null);
    try {
      const res = await fetch("/api/campus/route", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_building: q.from_building, to_building: q.to_building, from_room: q.from_room.trim() || null, to_room: q.to_room.trim() || null, mode: q.mode }),
      });
      const body = await res.json();
      if (res.status === 409) { setAsk({ which: body.detail.which, candidates: body.detail.candidates }); setError(body.detail.error); setResult(null); clearDrawing(); return; }
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Route failed");
      clearJourney(); setJourney(null);
      setResult(body); draw(body); saveRoute(q, body);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setResult(null); clearDrawing(); }
    finally { setBusy(false); }
  };

  const reset = () => { setResult(null); setError(null); setAsk(null); setJourney(null); clearDrawing(); clearRoute(); };

  const goToLeg = (requested: number) => {
    if (!result) return;
    // An indoor leg whose room already is the door has nothing to walk: carry straight on.
    const wanted = result.legs[requested];
    const index = wanted?.kind === "indoor" && wanted.trivial && wanted.role === "entry" ? nextLeg(result, requested) : requested;
    if (index >= result.legs.length) { finishTrip(); return; }
    const leg = result.legs[index];
    setJourneyIndex(index);
    if (leg?.kind === "indoor") navigate(indoorLink(leg, query.mode));
    else navigate("/tunnel"); // the outdoor part is skipped with a teleport; the map walk stays available from there
  };
  const finishTrip = () => {
    if (!result) return;
    const to = arrivalLink(result); // the destination is the entrance room itself, or a building opened without one
    clearRoute();
    navigate(to);
  };
  const startTrip = () => goToLeg(0);
  const pauseTrip = () => { clearJourney(); setJourney(null); setSearchParams({}); if (result) draw(result); };

  const pick = (which: "from" | "to") => {
    if (!selected) return;
    set(which === "from" ? { from_building: selected.building_id, from_room: "" } : { to_building: selected.building_id, to_room: "" });
  };

  const canFind = query.from_building && query.to_building && query.from_building !== query.to_building && !busy;
  const options = [...buildings].sort((a, b) => a.name.localeCompare(b.name));
  const nameOf = (id: string) => buildings.find((b) => b.building_id === id)?.name ?? id;
  const indoor = (result?.legs ?? []).filter((l): l is IndoorLeg => l.kind === "indoor");
  const outdoor = result?.legs.find((l): l is OutdoorLeg => l.kind === "outdoor");

  // ---- outdoor guide: one instruction at a time, the camera follows ----
  const guidingOutdoor = walkMode && result && outdoor && journey !== null && result.legs[journey]?.kind === "outdoor";
  const steps = outdoor ? (outdoor.steps.length ? outdoor.steps : fallbackSteps(outdoor, result?.to_building.name ?? "the destination")) : [];
  useEffect(() => {
    const map = mapInstance;
    const step = steps[stepIndex];
    if (!guidingOutdoor || !map || !step?.at) return;
    const next = steps[stepIndex + 1]?.at ?? (outdoor ? ([outdoor.to.lon, outdoor.to.lat] as [number, number]) : undefined);
    map.flyTo({ center: step.at, zoom: GUIDE_ZOOM, pitch: 55, ...(next ? { bearing: bearingBetween(step.at, next) } : {}), duration: 1200, essential: true });
    youMarker.current?.remove();
    const el = document.createElement("div");
    el.className = "fw-route-you";
    youMarker.current = new maplibregl.Marker({ element: el }).setLngLat(step.at).addTo(map);
  }, [guidingOutdoor, stepIndex, mapInstance]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!guidingOutdoor) { youMarker.current?.remove(); youMarker.current = null; } }, [guidingOutdoor]);

  if (!open) {
    return <button type="button" className="fw-route-toggle" onClick={() => setOpen(true)}>Route between buildings</button>;
  }

  if (result && journey !== null) {
    const leg = result.legs[journey];
    const last = result.legs.length - 1;
    if (leg?.kind === "indoor") {
      return (
        <aside className="fw-route-panel" aria-label="Trip between buildings">
          <header><b>TRIP PAUSED</b></header>
          <p className="fw-route-note">Step {journey + 1} of {result.legs.length}: you are inside {leg.building_name}.</p>
          <div className="fw-route-actions">
            <button type="button" className="fw-route-go" onClick={() => navigate(indoorLink(leg, query.mode))}>Back inside →</button>
            <button type="button" onClick={pauseTrip}>End trip</button>
          </div>
        </aside>
      );
    }
    if (!walkMode && leg?.kind === "outdoor") {
      return (
        <aside className="fw-route-panel" aria-label="Trip between buildings">
          <header><b>TRIP · STEP {journey + 1} OF {result.legs.length}</b></header>
          <p className="fw-route-note">You are between the two buildings. The outdoor part is skipped by teleport.</p>
          <div className="fw-route-actions">
            <button type="button" className="fw-route-go" onClick={() => navigate("/tunnel")}>Continue the trip →</button>
            <button type="button" onClick={() => { setSearchParams({ walk: "1" }); setStepIndex(0); }}>Walk it on the map</button>
          </div>
          <button type="button" className="fw-route-link" onClick={pauseTrip}>End trip</button>
        </aside>
      );
    }
    if (guidingOutdoor && outdoor) {
      const step = steps[stepIndex];
      const atEnd = stepIndex >= steps.length - 1;
      const entry = result.legs.find((l): l is IndoorLeg => l.kind === "indoor" && l.role === "entry");
      const arrive = () => { if (journey < last) goToLeg(journey + 1); else finishTrip(); };
      return (
        <aside className="fw-route-panel fw-route-guide" aria-label="Outdoor guide" aria-live="polite">
          <header><b>TRIP · STEP {journey + 1} OF {result.legs.length}</b><button type="button" onClick={pauseTrip} aria-label="Pause trip">✕</button></header>
          <p className="fw-route-guide-leg">{modeIcon(outdoor.mode)} Outside {modeVerb[outdoor.mode]} · {Math.round(outdoor.distance_m)} m · about {Math.max(1, Math.round(outdoor.duration_min))} min</p>
          <p className="fw-route-guide-text">{step?.instruction}</p>
          {step && step.distance_m > 0 && <p className="fw-route-note">then about {step.distance_m} m</p>}
          <div className="fw-route-dots" aria-hidden>{steps.map((_, i) => <i key={i} className={i === stepIndex ? "on" : i < stepIndex ? "done" : ""} />)}</div>
          <p className="fw-route-note">Step {stepIndex + 1} of {steps.length}{outdoor.estimated ? " · straight-line estimate, no street directions" : ""}</p>
          <div className="fw-route-actions">
            <button type="button" disabled={stepIndex === 0} onClick={() => setStepIndex((i) => Math.max(0, i - 1))}>← Back</button>
            {atEnd
              ? <button type="button" className="fw-route-go" onClick={arrive}>{entry ? `I'm at ${entry.door.label.replace("Entrance into ", "the entrance into ")} — go inside →` : `Go inside ${result.to_building.name} →`}</button>
              : <button type="button" className="fw-route-go" onClick={() => setStepIndex((i) => Math.min(steps.length - 1, i + 1))}>Next step →</button>}
          </div>
          <button type="button" className="fw-route-link" onClick={() => fit(outdoor.polyline)}>Show the whole walk</button>
        </aside>
      );
    }
  }

  const field = (which: "from" | "to") => {
    const b = query[`${which}_building`]; const room = query[`${which}_room`];
    return (
      <fieldset className="fw-route-field">
        <legend>{which === "from" ? "From" : "To"}</legend>
        <select value={b} onChange={(e) => set(which === "from" ? { from_building: e.target.value } : { to_building: e.target.value })} aria-label={`${which} building`}>
          <option value="">Choose a building…</option>
          {options.map((o) => <option key={o.building_id} value={o.building_id}>{o.name}</option>)}
        </select>
        {selected && selected.building_id !== b && <button type="button" className="fw-route-use" onClick={() => pick(which)}>Use {selected.name}</button>}
        <input value={room} placeholder="Room or machine (optional — otherwise any door)" aria-label={`${which} room`}
          onChange={(e) => set(which === "from" ? { from_room: e.target.value } : { to_room: e.target.value })}
          onKeyDown={(e) => { if (e.key === "Enter" && canFind) void find(); }} />
        {ask?.which === which && (
          <div className="fw-route-candidates" role="group" aria-label="Did you mean">
            {ask.candidates.map((c) => <button key={c.id} type="button" onClick={() => { set(which === "from" ? { from_room: c.label } : { to_room: c.label }); setAsk(null); setError(null); }}>{c.label}</button>)}
          </div>
        )}
      </fieldset>
    );
  };

  const stage = (label: string, metres: number, sub: string, onClick: () => void, icon: string) => (
    <button type="button" className="fw-route-stage" onClick={onClick}><span className="icon">{icon}</span><b>{label}</b><span>{Math.round(metres)} m</span><small>{sub}</small></button>
  );
  const entryLeg = indoor.find((l) => l.role === "entry");

  return (
    <aside className="fw-route-panel" aria-label="Route between buildings">
      <header><b>ROUTE BETWEEN BUILDINGS</b><button type="button" onClick={() => { setOpen(false); }} aria-label="Collapse">–</button></header>
      {field("from")}
      <button type="button" className="fw-route-swap" aria-label="Swap" onClick={() => setQuery((q) => ({ ...q, from_building: q.to_building, to_building: q.from_building, from_room: q.to_room, to_room: q.from_room }))}>⇅ swap</button>
      {field("to")}
      <div className="fw-route-modes" role="radiogroup" aria-label="How do you travel between the buildings?">
        {MODES.map((m) => (
          <button key={m.id} type="button" role="radio" aria-checked={query.mode === m.id} className={query.mode === m.id ? "active" : ""} onClick={() => set({ mode: m.id })}>
            <span>{m.icon}</span>{m.label}
          </button>
        ))}
      </div>
      <div className="fw-route-actions">
        <button type="button" className="fw-route-go" disabled={!canFind} onClick={() => void find()}>{busy ? "Routing…" : "Find route"}</button>
        {(result || error) && <button type="button" onClick={reset}>Clear</button>}
      </div>
      {query.from_building && query.from_building === query.to_building && <p className="fw-route-note">Same building: use the indoor navigator for this.</p>}
      {error && <p className="fw-route-error" role="alert">{error}</p>}
      {result && outdoor && (
        <section className="fw-route-result" aria-live="polite">
          <p className="fw-route-total"><b>{Math.round(result.total_m)} m</b> · about {Math.max(1, Math.round(result.duration_min))} min door to door</p>
          <button type="button" className="fw-route-go fw-route-start" onClick={startTrip}>Guide me step by step →</button>
          <div className="fw-route-stepper">
            {indoor[0]?.role === "exit" && stage(`Inside ${indoor[0].building_name}`, indoor[0].distance_m, indoor[0].trivial ? "you are already in the exit room" : `to ${indoor[0].door.label.replace("Entrance into ", "exit via ")}`, () => navigate(indoorLink(indoor[0], query.mode)), "🏢")}
            {stage(`Outside · ${Math.max(1, Math.round(outdoor.duration_min))} min`, outdoor.distance_m, outdoor.estimated ? "straight-line estimate" : outdoor.provider, () => fit(outdoor.polyline), modeIcon(outdoor.mode))}
            {entryLeg && stage(`Inside ${nameOf(result.to_building.id)}`, entryLeg.distance_m, entryLeg.trivial ? "the entrance is in your destination room" : "from the entrance", () => { if (!entryLeg.trivial) navigate(indoorLink(entryLeg, query.mode)); }, "🏢")}
          </div>
          <p className="fw-route-via">Leave by <b>{outdoor.from.label.replace("Entrance into ", "")}</b>, arrive at <b>{outdoor.to.label.replace("Entrance into ", "")}</b>. {result.entrance_pairs_considered} entrance pairs compared.</p>
          {result.warnings.map((w) => <p key={w} className="fw-route-note">{w}</p>)}
          {outdoor.steps.length > 0 && <details><summary>Outdoor directions</summary><ol>{outdoor.steps.map((s, i) => <li key={i}>{s.instruction} <small>{s.distance_m} m</small></li>)}</ol></details>}
          {result.alternatives.length > 0 && <details><summary>Other doors considered</summary><ul>{result.alternatives.map((a, i) => <li key={i}>{a.exit.replace("Entrance into ", "")} → {a.entrance.replace("Entrance into ", "")}: {Math.round(a.total_m)} m</li>)}</ul></details>}
        </section>
      )}
    </aside>
  );
}

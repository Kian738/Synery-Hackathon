import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { afterTunnel, clearJourney, clearRoute, journeyIndex, loadRoute, type OutdoorLeg } from "./journey";
import "./JourneyTunnel.css";

const AUTO_MS = 5000;
const VERB = { foot: "on foot", wheelchair: "by wheelchair", bike: "by bike", car: "by car" } as const;

/** Between the exit of one building and the entrance of the next: we skip the outdoors and say so. */
export default function JourneyTunnel() {
  const navigate = useNavigate();
  const [saved] = useState(loadRoute);
  const index = journeyIndex();
  const outdoor = saved && index !== null ? saved.result.legs[index] : undefined;
  const valid = !!saved && outdoor?.kind === "outdoor";
  const done = useRef(false);
  const [paused, setPaused] = useState(false);

  const proceed = () => {
    if (!saved || index === null || done.current) return;
    done.current = true;
    const { to, finished } = afterTunnel(saved.result, index, saved.query.mode);
    if (finished) clearRoute();
    navigate(to, { replace: true });
  };

  useEffect(() => {
    if (!valid || paused) return;
    const timer = window.setTimeout(proceed, AUTO_MS);
    return () => window.clearTimeout(timer);
  }, [valid, paused]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!valid || !saved) return <Navigate to="/map" replace />;
  const leg = outdoor as OutdoorLeg;
  const { from_building: from, to_building: to, mode } = { ...saved.result, mode: leg.mode };
  const minutes = Math.max(1, Math.round(leg.duration_min));
  const hasEntry = saved.result.legs.some((l) => l.kind === "indoor" && l.role === "entry" && !l.trivial);

  return (
    <main className="fw-tunnel" aria-live="polite" data-paused={paused}>
      <div className="fw-tunnel-warp" aria-hidden>
        {Array.from({ length: 9 }, (_, i) => <i key={i} style={{ animationDelay: `${i * -0.55}s` }} />)}
      </div>
      <section className="fw-tunnel-card">
        <small>Teleporting</small>
        <h1>{from.name} <span aria-hidden>→</span> {to.name}</h1>
        <p>You are out of {from.name}. We skip the {Math.round(leg.distance_m)} m outside (about {minutes} min {VERB[mode]}) and bring you straight to the door of {to.name}.</p>
        <p className="fw-tunnel-door">Arriving at <b>{leg.to.label.replace("Entrance into ", "the entrance into ")}</b></p>
        <div className="fw-tunnel-bar" aria-hidden><i style={paused ? { animation: "none", width: "0%" } : undefined} /></div>
        <div className="fw-tunnel-actions">
          <button type="button" className="primary" onClick={proceed}>{hasEntry ? `Continue inside ${to.name} →` : `Arrive at ${to.name} →`}</button>
          <button type="button" onClick={() => { setPaused(true); navigate("/map?walk=1"); }}>See the walk outside on the map</button>
          <button type="button" onClick={() => { clearJourney(); navigate("/map"); }}>End trip</button>
        </div>
      </section>
    </main>
  );
}

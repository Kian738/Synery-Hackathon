// Stand-alone two-screen demo: open /?role=laptop on the laptop and /?role=phone on the phone.
// It does not touch the Navigator. The "building" is a heading dial and a fixed five-step walk.
import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { LaptopPairing } from "../LaptopPairing";
import { PhoneCompanion } from "../PhoneCompanion";
import { routeStateFromGuide } from "../protocol";
import { useCompanionHost } from "../useCompanionHost";
import type { GuideStep } from "../../lib/types";

const step = (icon: GuideStep["icon"], short: string, text: string, metres: number, kind: GuideStep["kind"] = "walk"): GuideStep => ({ kind, icon, short, text, metres, floor_id: null, point: null, landmark: null, space_id: null });
const STEPS: GuideStep[] = [
  step("start", "Start", "You are at the main entrance. Face the reception desk.", 0, "start"),
  step("straight", "Corridor", "Walk 18 metres along the corridor past the coffee machine.", 18),
  step("left", "Turn left", "Turn left at the notice board and walk 6 metres.", 6),
  step("lift", "Lift 2", "Take Lift 2 to floor 2.", 0, "floor"),
  step("arrive", "Arrived", "Lab 2.17 is the second door on your right.", 4, "arrive"),
];

const wrap = (d: number) => ((d % 360) + 360) % 360;

function Laptop() {
  const [index, setIndex] = useState(0);
  const [heading, setHeading] = useState(0);
  const [log, setLog] = useState<string[]>([]);
  const indexRef = useRef(index);
  indexRef.current = index;
  const note = (line: string) => setLog(l => [line, ...l].slice(0, 6));
  const host = useCompanionHost({
    onHeading: dyaw => setHeading(h => wrap(h + dyaw)),
    onStep: action => { note(`phone asked: ${action}`); setIndex(i => (action === "next" ? Math.min(i + 1, STEPS.length - 1) : action === "back" ? Math.max(i - 1, 0) : i)); },
    onRecenter: () => { setHeading(0); note("recentered"); },
  });
  useEffect(() => { host.publish(routeStateFromGuide(STEPS, index, { routeId: "demo", headingDeg: heading })); }, [index, heading]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 420px) 1fr", gap: 16, padding: 16, color: "#edf3f5", fontFamily: "Barlow, system-ui, sans-serif", minHeight: "100vh", boxSizing: "border-box" }}>
      <LaptopPairing host={host} phonePath="/?role=phone" />
      <main aria-label="Laptop view" style={{ background: "#182329", border: "1px solid #2b3a42", borderRadius: 10, padding: 16 }}>
        <h1 style={{ margin: 0 }}>Laptop view (demo)</h1>
        <p data-testid="heading" style={{ fontSize: 28, margin: "8px 0" }}>Camera heading: <b>{Math.round(heading)}°</b></p>
        <svg viewBox="-60 -60 120 120" width="160" height="160" role="img" aria-label={`Camera heading ${Math.round(heading)} degrees`}>
          <circle r="52" fill="none" stroke="#2b3a42" strokeWidth="2" />
          <g transform={`rotate(${heading})`}><path d="M0 -46 L9 -12 L0 -20 L-9 -12 Z" fill="#ffd45c" /></g>
        </svg>
        <ol data-testid="steps" style={{ fontSize: 20, lineHeight: 1.5, paddingLeft: 24 }}>
          {STEPS.map((s, i) => <li key={i} aria-current={i === index ? "step" : undefined} style={{ color: i === index ? "#ffd45c" : "#b6c5cc", fontWeight: i === index ? 700 : 400 }}>{s.text}</li>)}
        </ol>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setIndex(i => Math.max(0, i - 1))}>Previous (laptop)</button>
          <button onClick={() => setIndex(i => Math.min(STEPS.length - 1, i + 1))}>Next (laptop)</button>
        </div>
        <p style={{ color: "#b6c5cc" }}>Laptop navigation works with or without a phone. Recent phone requests:</p>
        <ul data-testid="log" style={{ color: "#b6c5cc" }}>{log.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </main>
    </div>
  );
}

const role = new URLSearchParams(location.search).get("role");
createRoot(document.getElementById("root")!).render(<StrictMode>{role === "phone" ? <PhoneCompanion /> : <Laptop />}</StrictMode>);

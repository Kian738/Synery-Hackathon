import type { ReactNode } from "react";
import { Pictogram } from "../../components/Pictogram";
import { LIMITS } from "./parts";

export type ScenarioKind = "fire" | "blocked" | "crowd" | "outage";
export const SCENARIO_PRESETS: { key: ScenarioKind; label: string; engine: string }[] = [
  { key: "fire", label: "Fire in a room", engine: "Exact flow over time" },
  { key: "blocked", label: "Exit blocked", engine: "Exact flow, busiest exit closed" },
  { key: "crowd", label: "Crowd surge", engine: "Every person simulated" },
  { key: "outage", label: "Lift/stair outage", engine: "Step-free exit check" },
];

/** The preset chips at the top of every Scenarios panel: one tool, one choice of what to test. */
export function ScenarioChips({ value, onChange }: { value: ScenarioKind; onChange: (k: ScenarioKind) => void }) {
  return <div className="k-scen-chips" role="group" aria-label="Scenario">
    {SCENARIO_PRESETS.map(p => <button key={p.key} type="button" className="k-ctl" aria-pressed={value === p.key} title={p.engine} onClick={() => onChange(p.key)}>{p.label}</button>)}
  </div>;
}

type Weak = { kind: string; name: string; rooms_lost: number; of_rooms: number; room_ids: string[] };

/** Lift/stair outage: each connector closed on its own, counting rooms that lose step-free exit access. */
export function OutagePanel({ top, busy, items, onClose, onShow, onRerun }: { top: ReactNode; busy: boolean; items: Weak[]; onClose: () => void; onShow: (item: Weak) => void; onRerun: () => void }) {
  return <section className="stress-drawer" aria-label="Building stress test">
    <header><div><span>Scenarios</span><h2>Lift or stair out of service</h2></div><button aria-label="Close stress test" onClick={onClose}><Pictogram name="close" /></button></header>
    {top}
    <p>Each result closes one connector independently and checks step-free routes to mapped exits.</p>
    {busy ? <p role="status">Checking connector closures…</p> : items.length ? items.map((item, i) => <button className="stress-result" key={i} onClick={() => onShow(item)}>
      <span><Pictogram name={item.kind === "lift" ? "lift" : "stairs"} /><b>{item.name}</b></span><strong>{item.rooms_lost}<small> / {item.of_rooms} rooms</small></strong><span>would lose step-free exit access</span><span className="stress-inspect">Show affected rooms</span>
    </button>) : <p>No individual connector closure disconnects mapped rooms for this analysis.</p>}
    <details><summary>Evidence and assumptions</summary><p>Computed by removing each connector from the route graph and comparing exit reachability. This is a single-failure sensitivity check, not a fire or crowd-capacity simulation. Occupancy and door throughput are not supplied.</p></details>
    <p className="k-hint k-scen-limits">{LIMITS}</p>
    <button className="stress-rerun" disabled={busy} onClick={onRerun}>Run again</button>
  </section>;
}

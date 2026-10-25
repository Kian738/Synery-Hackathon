import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { area } from "../lib/geometry";
import type { Geometry, Opening } from "../lib/types";
import { Pictogram } from "./Pictogram";

/** Evacuation stress test: run it, scrub through time with a density heat map on the floors, see where the queues form and where a new door helps. */
export interface StressRun {
  kpis: { people: number; evacuated: number; stranded: number; first_out_s: number; p50_s: number; p95_s: number; max_s: number; stranded_rooms: { id: string; name: string; people: number }[] };
  doors: { id: string; kind: string; between: string[]; floor_id: string; position: number[]; width_m: number; flow_pps: number; load: number; peak_queue: number; max_wait_s: number; total_wait_s: number }[];
  rooms: { id: string; name: string; floor_id: string; peak_people: number; peak_at_s: number; peak_density: number; los: string }[];
  frames: { step_s: number; rooms: Record<string, number[]> };
  flags: { kind: string; text: string }[];
  assumptions: string[];
}
export interface DoorIdea { first: string; second: string; first_name: string; second_name: string; floor_id: string; door: Opening & { id: string }; p95_before_s: number; p95_after_s: number; delta_p95_s: number; stranded_before: number; stranded_after: number; regress: boolean; reason: string; new_exit?: boolean }

/** Level-of-service colours: calm blue, teal, lime, amber, orange, red. Ordered by density; each also carries its letter in the legend and lists. */
export const LOS_COLOR: Record<string, string> = { A: "#3d5a80", B: "#4f9d9a", C: "#b7d04f", D: "#f2c14e", E: "#ee8434", F: "#d62839" };
const EMPTY_COLOR = "#26333b";
const LOS_BANDS: [string, number][] = [["A", 0.31], ["B", 0.43], ["C", 0.72], ["D", 1.08], ["E", 2.17]];
const levelOf = (density: number) => LOS_BANDS.find(([, bound]) => density <= bound)?.[0] ?? "F";

export function heatAt(run: StressRun, geometry: Geometry, seconds: number): Record<string, string> {
  const index = Math.min(Math.round(seconds / run.frames.step_s), Math.max(0, (Object.values(run.frames.rooms)[0]?.length ?? 1) - 1));
  const out: Record<string, string> = {};
  for (const space of geometry.spaces) {
    const head = run.frames.rooms[space.id]?.[index] ?? 0;
    if (!head) { out[space.id] = EMPTY_COLOR; continue; }  // empty rooms recede so the crowded ones read at a glance
    out[space.id] = LOS_COLOR[levelOf(head / Math.max(area(space.polygon) * 0.7, 1))];
  }
  return out;
}

const PRESETS = [
  { key: "all", label: "Everyone leaves", body: {} },
  { key: "slow", label: "Slow reaction", body: { pre_movement_median_s: 120 } },
  { key: "stepfree", label: "Step-free only", body: { kind: "step_free_evacuation" } },
  { key: "exit", label: "Busiest exit blocked", body: { _closeBusiest: true } },
] as const;
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function StressPanel({ geometry, sessionId, onClose, onHeat, onPins, onIdea, onApplied }: {
  geometry: Geometry; sessionId: string; onClose: () => void;
  onHeat: (heat: Record<string, string> | null) => void;
  onPins: (pins: { id: string; floor_id: string; x: number; y: number }[]) => void;
  onIdea: (door: Opening | null) => void;
  onApplied: (events: import("../lib/types").UiEvent[]) => void;
}) {
  const [preset, setPreset] = useState<string>("all");
  const [run, setRun] = useState<StressRun | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [time, setTime] = useState(0), [playing, setPlaying] = useState(false);
  const [ideas, setIdeas] = useState<{ candidates: DoorIdea[]; checked: number } | null>(null), [ideasBusy, setIdeasBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const horizon = run ? run.kpis.max_s : 0;

  const post = async (path: string, body: object) => {
    const r = await fetch(`/api/sessions/${sessionId}/stress${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw Error(typeof j.detail === "string" ? j.detail : "The stress test could not run.");
    return j;
  };
  const start = async (key = preset) => {
    setBusy(true); setError(""); setIdeas(null); onIdea(null); setPlaying(false);
    try {
      const chosen = PRESETS.find(p => p.key === key)!;
      let body: Record<string, unknown> = { ...chosen.body };
      if ("_closeBusiest" in body) {
        delete body._closeBusiest;
        const base: StressRun = await post("", {});
        const busiest = base.doors.find(d => d.between.includes("outside"));
        if (busiest) body.closed = [busiest.id];
      }
      const result: StressRun = await post("", body);
      setRun(result); setTime(0); setPlaying(true);
    } catch (e) { setError(String((e as Error).message ?? e)); } finally { setBusy(false); }
  };
  useEffect(() => { void start("all"); return () => { onHeat(null); onPins([]); onIdea(null); }; }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!run) return;
    onHeat(heatAt(run, geometry, time));
    const spaces = new Map(geometry.spaces.map(s => [s.id, s]));
    onPins(run.doors.slice(0, 4).filter(d => d.max_wait_s >= 5).map(d => ({ id: d.id, floor_id: d.floor_id, x: d.position[0], y: d.position[1] })).filter(p => !!p.floor_id && spaces.size > 0));
  }, [run, time, geometry]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    window.clearInterval(timer.current);
    if (!playing || !run) return;
    timer.current = window.setInterval(() => setTime(t => { const next = t + Math.max(run.frames.step_s, horizon / 90); if (next >= horizon) { setPlaying(false); return horizon; } return next; }), 90);
    return () => window.clearInterval(timer.current);
  }, [playing, run, horizon]);

  const suggest = async () => {
    setIdeasBusy(true); setError("");
    try {
      const chosen = PRESETS.find(p => p.key === preset)!;
      const body: Record<string, unknown> = { ...chosen.body };
      delete body._closeBusiest;
      setIdeas(await post("/doors", { ...body, top: 4 }));
    } catch (e) { setError(String((e as Error).message ?? e)); } finally { setIdeasBusy(false); }
  };
  const apply = async (idea: DoorIdea) => {
    setError("");
    try { const done = await api.door(sessionId, idea.first_name, idea.second_name, true); onApplied(done.events); onIdea(null); await start(); } catch (e) { setError(String((e as Error).message ?? e)); }
  };

  const k = run?.kpis;
  const worst = useMemo(() => run?.rooms.slice(0, 4) ?? [], [run]);
  return (
    <section className="k-stress" aria-label="Evacuation stress test">
      <header><h2>Evacuation test</h2><button type="button" className="k-ctl icon" aria-label="Close stress test" onClick={onClose}><Pictogram name="close" size={18} /></button></header>
      <div className="k-stress-presets" role="group" aria-label="Scenario">
        {PRESETS.map(p => <button key={p.key} type="button" className="k-ctl" aria-pressed={preset === p.key} onClick={() => { setPreset(p.key); void start(p.key); }} disabled={busy}>{p.label}</button>)}
      </div>
      {error && <p role="alert" className="k-stress-error">{error}</p>}
      {busy && !run && <p className="k-hint">Simulating every person…</p>}
      {k && (
        <>
          <dl className="k-stress-kpis" data-busy={busy}>
            <div><dt>First out</dt><dd>{mmss(k.first_out_s)}</dd></div>
            <div><dt>Half out</dt><dd>{mmss(k.p50_s)}</dd></div>
            <div><dt>95 % out</dt><dd>{mmss(k.p95_s)}</dd></div>
            <div><dt>Last out</dt><dd>{mmss(k.max_s)}</dd></div>
          </dl>
          <p className="k-stress-people">{k.evacuated} of {k.people} people reach an exit{k.stranded ? <b className="k-stress-warn"> · {k.stranded} cannot ({k.stranded_rooms.slice(0, 2).map(r => r.name).join(", ")}{k.stranded_rooms.length > 2 ? "…" : ""})</b> : ""}</p>
          <div className="k-stress-scrub">
            <button type="button" className="k-ctl icon" aria-label={playing ? "Pause" : "Play"} onClick={() => { if (time >= horizon) setTime(0); setPlaying(p => !p); }}><Pictogram name={playing ? "pause" : "play"} size={18} /></button>
            <input type="range" aria-label="Time into the evacuation" min={0} max={Math.max(1, Math.round(horizon))} step={1} value={Math.round(time)} onChange={e => { setPlaying(false); setTime(Number(e.target.value)); }} />
            <output>{mmss(time)}</output>
          </div>
          <div className="k-stress-legend" aria-label="Crowding legend">{Object.entries(LOS_COLOR).map(([letter, colour]) => <span key={letter}><i style={{ background: colour }} />{letter}</span>)}<em>crowding, A calm to F packed</em></div>
          <h3>Where people queue</h3>
          <ul className="k-stress-list">
            {run!.doors.slice(0, 4).map(d => (
              <li key={d.id}><b>{d.between.join(" → ")}</b><span>{d.load} people, up to {d.peak_queue} waiting, longest wait {Math.round(d.max_wait_s)} s ({d.width_m} m wide)</span></li>
            ))}
          </ul>
          {worst.length > 0 && <><h3>Most crowded rooms</h3><ul className="k-stress-list">{worst.map(r => <li key={r.id}><b>{r.name}</b><span>level {r.los} · {r.peak_people} people at {mmss(r.peak_at_s)}</span></li>)}</ul></>}
          {run!.flags.map(f => <p key={f.kind} className="k-stress-flag">{f.text}</p>)}
          <button type="button" className="k-ctl accent k-stress-suggest" onClick={suggest} disabled={ideasBusy}>{ideasBusy ? "Trying doors…" : "Where should a new door go?"}</button>
          {ideas && (ideas.candidates.length === 0 ? <p className="k-hint">No new door improves this scenario.</p> : (
            <ul className="k-stress-ideas">
              {ideas.candidates.map((c, i) => (
                <li key={i} data-regress={c.regress}>
                  <b>{c.first_name} ↔ {c.second_name}</b>
                  <span>{c.regress ? "Worse: " : ""}{c.reason}. 95 % out {mmss(c.p95_before_s)} → {mmss(c.p95_after_s)}{c.stranded_after !== c.stranded_before ? `, stranded ${c.stranded_before} → ${c.stranded_after}` : ""}.</span>
                  <div><button type="button" className="k-ctl" onClick={() => onIdea(c.door)}>Show</button>{!c.new_exit && !c.regress && <button type="button" className="k-ctl accent" onClick={() => void apply(c)}>Add this door</button>}</div>
                </li>
              ))}
            </ul>
          ))}
          <details className="k-stress-assume"><summary>How this is computed</summary><ul>{run!.assumptions.map(a => <li key={a}>{a}</li>)}</ul></details>
        </>
      )}
    </section>
  );
}

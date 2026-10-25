import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ScenarioCapacity } from "../lib/api";
import { stopSpeaking } from "../lib/voice";
import { IconButton, Segmented } from "../ui/kit";
import type { Audience, Geometry, RobustReport, ScenarioMark, ScenarioReport, Space, UiEvent } from "../lib/types";

const AUDIENCES: { value: Audience; label: string; ariaLabel: string }[] = [
  { value: "safety_officer", label: "Safety", ariaLabel: "Safety officer" }, { value: "occupant", label: "Occupant", ariaLabel: "Occupant" },
  { value: "builder", label: "Builder", ariaLabel: "Builder" }, { value: "regulator", label: "Regulator", ariaLabel: "Regulator" },
];
const SEVERITY = { blocker: "Blocker", risk: "Risk", improve: "Improve", info: "Note" } as const;
const ORDER = ["blocker", "risk", "improve", "info"];

export function headline(r: ScenarioReport): string {
  if (r.abstained && !r.evacuation) return "This scenario could not be checked.";
  const e = r.evacuation;
  if (!e) return "No evacuation result.";
  const stranded = Object.values(e.stranded ?? {}).reduce((a, b) => a + b, 0);
  return stranded > 0 || e.evacuated < e.total ? `${e.evacuated} of ${e.total} people get out; ${e.total - e.evacuated} do not` : `Everyone is out in ${e.T_s} s`;
}

const REPLAY_SECONDS = 15;

/** People out, and people left in each room, at time t. Rooms are 1 (some) or 2 (many, over half the busiest the room gets). */
export function crowdAt(e: NonNullable<ScenarioReport["evacuation"]>, t: number): { out: number; crowd: Record<string, 1 | 2> } {
  const moves = e.schedule ?? [];
  const initial: Record<string, number> = {};
  for (const m of moves) {
    initial[m.from_space] = (initial[m.from_space] ?? 0) + m.persons;
    initial[m.to_space] = (initial[m.to_space] ?? 0) - m.persons;
  }
  for (const [sp, n] of Object.entries(e.stranded ?? {})) initial[sp] = (initial[sp] ?? 0) + n;
  const at = (time: number) => {
    const left = { ...initial };
    for (const m of moves) { if (m.depart_s <= time) left[m.from_space] -= m.persons; if (m.arrive_s <= time) left[m.to_space] += m.persons; }
    return left;
  };
  const inside = (r: Record<string, number>) => Object.entries(r).filter(([k]) => k !== "outside").map(([, v]) => v);
  const peak = Math.max(1, ...inside(initial), ...moves.map(m => Math.max(0, ...inside(at(m.arrive_s)))));
  const crowd: Record<string, 1 | 2> = {};
  for (const [sp, n] of Object.entries(at(t))) if (sp !== "outside" && n > 0.5) crowd[sp] = n > peak / 2 ? 2 : 1;
  const out = moves.reduce((a, m) => a + (m.to_space === "outside" && m.arrive_s <= t ? m.persons : 0), 0);
  return { out, crowd };
}

type Beat = { t: number; say: string; focus: string };
type Numbers = { people: number | null; rate: number | null };

const whole = (v: string) => { const n = Math.floor(Number(v)); return v.trim() !== "" && Number.isFinite(n) && n > 0 ? n : null; };
const positive = (v: string) => { const n = Number(v); return v.trim() !== "" && Number.isFinite(n) && n > 0 ? n : null; };

export function ScenarioPanel({ quickRun = 0, geometry, sessionId, selected, onClose, onHighlight, onScenario, onFloor, apply, incoming, replayCmd, onBeat }: {
  onBeat?: (say: string, focus: string) => void;
  geometry: Geometry; sessionId: string; selected: Space | null; onClose: () => void;
  quickRun?: number;
  incoming?: { n: number; report: ScenarioReport; hazard: string } | null;
  replayCmd?: { n: number; action: "play" | "pause" | "restart" | "seek"; seconds?: number } | null;
  onHighlight: (ids: Set<string>) => void; onScenario: (m: ScenarioMark | null) => void; onFloor: (id: string) => void; apply: (events: UiEvent[]) => void;
}) {
  const [hazard, setHazard] = useState<Space | null>(null);
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState<Audience>("safety_officer");
  const [report, setReport] = useState<ScenarioReport | null>(null);
  const [used, setUsed] = useState<Numbers>({ people: null, rate: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);
  const [more, setMore] = useState(false);
  const [robust, setRobust] = useState<RobustReport | null>(null);
  const [robustBusy, setRobustBusy] = useState(false);
  const [limit, setLimit] = useState<{ element: string; value: number } | null>(null);
  const [limitExit, setLimitExit] = useState("");
  const [limitMax, setLimitMax] = useState("10");
  const [people, setPeople] = useState("");
  const [rate, setRate] = useState("");
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const T = report?.evacuation?.T_s ?? 0;
  // A room picked before running sets the fire room. Once a result is showing, the replay's own camera moves select rooms too, so they must not clear it.
  useEffect(() => { if (selected && !report) setHazard(selected); }, [selected]);
  useEffect(() => { setT(0); setPlaying(!!report?.evacuation?.schedule?.length); }, [report]);
  useEffect(() => { if (quickRun > 0 && busiest && !busy) { setHazard(busiest); void run(busiest); } }, [quickRun]);
  useEffect(() => {
    if (!incoming) return;
    const h = geometry.spaces.find(x => x.id === incoming.hazard);
    if (h) { setHazard(h); onFloor(h.floor_id); }
    setLimit(null); setUsed({ people: null, rate: null }); setReport(incoming.report);
    onHighlight(new Set([incoming.hazard, ...(incoming.report.evacuation?.bottleneck ?? [])]));
  }, [incoming?.n]);
  useEffect(() => {
    if (!replayCmd || !report) return;
    if (replayCmd.action === "pause") setPlaying(false);
    else if (replayCmd.action === "restart") { setT(0); setPlaying(true); }
    else if (replayCmd.action === "seek") { setT(Math.max(0, Math.min(T, replayCmd.seconds ?? 0))); setPlaying(false); }
    else { if (t >= T) setT(0); setPlaying(true); }
  }, [replayCmd?.n]);
  useEffect(() => {
    if (!playing || T <= 0) return;
    let raf = 0, last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000; last = now;
      setT(v => { const n = Math.min(T, v + dt * T / REPLAY_SECONDS); if (n >= T) setPlaying(false); return n; });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, T]);
  const replay = useMemo(() => report?.evacuation ? crowdAt(report.evacuation, t) : null, [report, t]);
  const name = (id: string) => geometry.spaces.find(s => s.id === id)?.name ?? id;
  const exitName = (id: string) => { const o = geometry.openings.find(x => x.id === id); const n = o?.space_ids.filter(x => x !== "outside").map(name).join(" / "); return n || id; };
  const [beatText, setBeatText] = useState("");
  const beats = useMemo<Beat[]>(() => {
    const e = report?.evacuation; if (!e?.schedule?.length || !hazard) return [];
    const mv = e.schedule, out: Beat[] = [];
    const fire = mv.filter(m => m.from_space === hazard.id);
    if (fire.length) out.push({ t: 0, say: `People are leaving ${name(hazard.id)}.`, focus: hazard.id });
    const outs = mv.filter(m => m.to_space === "outside").sort((a, b) => a.arrive_s - b.arrive_s);
    if (outs.length) out.push({ t: outs[0].arrive_s, say: `The first people are out through ${exitName(outs[0].element)}.`, focus: outs[0].from_space });
    const queue = mv.filter(m => (e.bottleneck ?? []).includes(m.element) && m.depart_s > 0 && (crowdAt(e, m.depart_s).crowd[m.from_space] ?? 0) > 0).sort((a, b) => a.depart_s - b.depart_s)[0];
    if (queue) out.push({ t: queue.depart_s, say: `${exitName(queue.element)} is a bottleneck: a queue forms.`, focus: queue.from_space });
    let acc = 0; const half = outs.find(m => (acc += m.persons) >= e.total / 2);
    if (half) out.push({ t: half.arrive_s, say: "Half of the people are out.", focus: half.from_space });
    const stranded = e.total - e.evacuated;
    out.push({ t: e.T_s, say: stranded > 0 ? `${stranded} people could not get out.` : `The last person is out at ${e.T_s} s.`, focus: Object.keys(e.stranded ?? {})[0] ?? outs[outs.length - 1]?.from_space ?? hazard.id });
    return out.sort((a, b) => a.t - b.t);
  }, [report, hazard]);
  const beatIdx = useRef(0), lastT = useRef(0), lastBeatAt = useRef(0);
  useEffect(() => {
    if (t < lastT.current) { beatIdx.current = Math.max(0, beats.filter(b => b.t <= t).length - 1); lastBeatAt.current = 0; }
    lastT.current = t;
    let due: Beat | null = null;
    const now = performance.now();  // one beat at a time, each stays on screen about 2.5 s, so none is skipped
    if (playing && beatIdx.current < beats.length && beats[beatIdx.current].t <= t && now - lastBeatAt.current >= 2500) { due = beats[beatIdx.current++]; lastBeatAt.current = now; }
    if (!due || !playing) return;
    setBeatText(due.say);
    const sp = geometry.spaces.find(x => x.id === due!.focus);
    onHighlight(new Set([due.focus]));
    if (sp) onFloor(sp.floor_id);
    onBeat?.(due.say, due.focus);
  }, [t, beats, playing]);
  useEffect(() => { beatIdx.current = 0; lastT.current = 0; lastBeatAt.current = 0; setBeatText(""); }, [report]);
  useEffect(() => { if (!playing) stopSpeaking(); }, [playing]);
  useEffect(() => () => { stopSpeaking(); }, []);
  const lastMark = useRef("");
  useEffect(() => {
    if (!report || !hazard || !replay) return;
    const mark: ScenarioMark = { hazard: hazard.id, doors: report.evacuation?.bottleneck ?? [], responder: report.responder, crowd: replay.crowd };
    const key = JSON.stringify(mark);
    if (key !== lastMark.current) { lastMark.current = key; onScenario(mark); }
  }, [report, hazard, replay]);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? geometry.spaces.filter(s => s.name.toLowerCase().includes(q)).slice(0, 6) : [];
  }, [query, geometry.spaces]);
  const run = async (h = hazard, a = audience, lim = limit) => {
    if (!h) return;
    const mine: Numbers = { people: whole(people), rate: positive(rate) };
    setBusy(true); setError(""); setApplied(false); setMore(false); setRobust(null);
    try {
      // An exit limit replaces the passage rate on that one exit (the solver keeps one cap per element).
      const caps: ScenarioCapacity[] = mine.rate ? geometry.openings.filter(o => o.id !== lim?.element).map(o => ({ element: o.id, kind: "rate_persons_per_s", value: mine.rate! / 60 })) : [];
      if (lim) caps.push({ element: lim.element, kind: "total_persons", value: lim.value });
      const r = await api.scenario(sessionId, h.id, a, caps, mine.people ? { [h.id]: mine.people } : undefined);
      setUsed(mine); setReport(r);
      onHighlight(new Set([h.id, ...(r.evacuation?.bottleneck ?? [])]));
      onFloor(h.floor_id);
    } catch (e) { setError(e instanceof Error ? e.message : "Scenario failed"); }
    setBusy(false);
  };
  const pick = (s: Space) => { setHazard(s); setReport(null); setLimit(null); setQuery(""); onScenario({ hazard: s.id, doors: [] }); onFloor(s.floor_id); onHighlight(new Set([s.id])); };
  // One-click first result: start the fire in the room with the most seats (the same occupant estimate the solver uses).
  const busiest = useMemo(() => {
    const seats = new Map<string, number>();
    geometry.assets.forEach(x => { if (["chair", "office_chair", "bench"].includes(x.type)) seats.set(x.space_id, (seats.get(x.space_id) ?? 0) + 1); });
    const top = [...seats].sort((p, q) => q[1] - p[1] || p[0].localeCompare(q[0]))[0];
    return top ? geometry.spaces.find(x => x.id === top[0]) : undefined;
  }, [geometry.assets, geometry.spaces]);
  const findings = report ? [...report.findings].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity)).slice(0, more ? 99 : 3) : [];
  const fix = report?.answer?.fixes?.[0];
  const suggested = fix && report?.findings.some(f => f.suggestion);
  const abstain = report?.abstained ? report.steps.find(s => !s.ok) : null;
  const reason = abstain?.reason ?? (typeof report?.abstained === "string" ? report.abstained : report?.abstained?.reason);
  const ev = report?.evacuation;
  const exits = Object.keys(ev?.by_exit ?? {});
  const fireOut = ev && hazard ? (ev.schedule ?? []).reduce((a, m) => a + (m.from_space === hazard.id ? m.persons : 0), 0) : 0;
  const source = !ev ? "" : used.people || used.rate
    ? `Your numbers: ${used.people ? `${Math.min(fireOut, used.people)} of ${used.people} people get out of the fire room` : "people estimated from seats"}${used.rate ? `; every door passes ${used.rate} people per minute` : ""}.${used.people ? " Other rooms are estimated from seats." : ""}`
    : `${ev.total} people, estimated from seats.`;

  return <section className="k-sheet scenario" aria-label="Fire / evacuation scenario">
    <header className="k-sheet-head">
      <div><div className="k-pop-title">Scenario</div><h2>Fire / evacuation</h2></div>
      <IconButton label="Close scenario" icon="close" onClick={onClose} />
    </header>
    <p className="k-hint">{hazard ? <>Fire room: <b>{hazard.name}</b></> : "Click a room on the map, or search, to set where the fire starts."}</p>
    {!hazard && busiest && <IconButton accent label={`Quick fire test: ${busiest.name} (most seats)`} text={`Quick fire test: ${busiest.name}`} disabled={busy} onClick={() => { setHazard(busiest); run(busiest); }} />}
    <input className="k-input" aria-label="Search rooms" placeholder="Search rooms" value={query} onChange={e => setQuery(e.target.value)} />
    {matches.length > 0 && <div className="k-sheet-list">{matches.map(s => <button key={s.id} type="button" className="k-row" onClick={() => pick(s)}>{s.name}</button>)}</div>}
    <div className="k-pop-title">Who is this for</div>
    <Segmented ariaLabel="Who is this for" value={audience} options={AUDIENCES} onChange={a => { setAudience(a); if (report) run(hazard, a); }} />
    <details className="k-sheet-more">
      <summary>Your numbers</summary>
      <p className="k-hint">Leave empty to estimate people from seats and door rates from door widths.</p>
      <label className="k-field"><span>People in the fire room</span><input className="k-input" type="number" min={1} step={1} inputMode="numeric" value={people} onChange={e => setPeople(e.target.value)} /></label>
      <label className="k-field"><span>Passage rate (people per minute)</span><input className="k-input" type="number" min={1} step={1} inputMode="decimal" value={rate} onChange={e => setRate(e.target.value)} /></label>
    </details>
    <IconButton accent label="Run scenario" text={busy ? "Checking…" : "Run scenario"} disabled={!hazard || busy} onClick={() => run()} />
    {error && <p role="alert" className="k-sheet-alert">Could not run: {error}</p>}
    <div aria-live="polite">{busy && <p className="k-hint">Checking the evacuation…</p>}</div>
    {report && <>
      <h3 className="scenario-headline" role="status">{headline(report)}</h3>
      {source && <p className="k-hint scenario-source">{source}</p>}
      {ev && limit && ev.evacuated < ev.total && <p className="k-sheet-alert" role="alert">Cannot meet this limit: {exitName(limit.element)} takes at most {limit.value} people and no other exit can take the rest. {ev.total - ev.evacuated} people have no way out.</p>}
      {replay && ev && T > 0 && <div className="k-sheet-group">
        <p className="sr-only scenario-beat" aria-live="polite">{beatText}</p>
        <p className="scenario-counter">{Math.round(replay.out)} of {ev.total} out</p>
        <div className="k-sheet-row">
          <IconButton label={playing ? "Pause" : "Play"} icon={playing ? "pause" : "play"} onClick={() => { if (!playing && t >= T) setT(0); setPlaying(p => !p); }} />
          <input type="range" className="k-range" aria-label="Replay time" min={0} max={T} step={1} value={Math.round(t)} onChange={e => { setT(Number(e.target.value)); setPlaying(false); }} />
          <span className="k-hint">{Math.round(t)} s</span>
        </div>
        <p className="k-hint">Red: fire. Blue: responders. Amber: slow door. Darker rooms hold more people.</p>
      </div>}
      {ev?.nearest_exit && ev.nearest_exit.T_s > ev.T_s && <p className="k-hint">Everyone using their nearest exit instead: {ev.nearest_exit.T_s} s ({ev.nearest_exit.T_s - ev.T_s} s slower). Exits are planned together here.</p>}
      {report.abstained && !ev ? <p>Stopped at {abstain ? `step ${abstain.id}: ` : "a step: "}{reason ?? "A step could not be completed."}</p> : <>
        <details className="k-sheet-more"><summary>{report.steps.length} steps checked</summary>
          <ol>{report.steps.map(s => <li key={s.id}>{s.ok ? s.summary : `Stopped: ${s.summary}`}</li>)}</ol></details>
        {findings.map((f, i) => <div key={i} className="k-sheet-finding" data-severity={f.severity}><b>{SEVERITY[f.severity]}</b><span>{f.title}</span><small>{f.detail}</small></div>)}
        {report.findings.length > 3 && <IconButton label={more ? "Show fewer" : "Show more"} text={more ? "Show fewer" : "Show more"} onClick={() => setMore(v => !v)} />}
        {suggested && fix && <IconButton accent label={applied ? "Applied to model" : `Apply to model (widen door to ${fix.width_m} m)`} text={applied ? "Applied to model" : `Apply to model: widen door to ${fix.width_m} m`} disabled={applied}
          onClick={async () => { const { events } = await api.widen(sessionId, fix.element, fix.width_m); apply(events); await run(hazard, audience); setApplied(true); }} />}
        {exits.length > 0 && <div className="k-sheet-group">
          <div className="k-pop-title">Limit one exit (0 blocks it)</div>
          <select className="k-input" aria-label="Exit to limit" value={limitExit || exits[0]} onChange={e => setLimitExit(e.target.value)}>
            {exits.map(id => <option key={id} value={id}>{exitName(id)}</option>)}
          </select>
          <div className="k-sheet-row">
            <input className="k-input k-num" type="number" min={0} aria-label="Max people" placeholder="Max people" value={limitMax} onChange={e => setLimitMax(e.target.value)} />
            <IconButton label="Re-run with limit" text="Re-run with limit" disabled={busy || limitMax === ""} onClick={() => { const l = { element: limitExit || exits[0], value: Math.max(0, Math.floor(Number(limitMax))) }; setLimit(l); run(hazard, audience, l); }} />
          </div>
        </div>}
        {hazard && !robust && <IconButton label="Check if an exit fails" text={robustBusy ? "Checking each exit…" : "Check if an exit fails"} disabled={robustBusy}
          onClick={async () => { setRobustBusy(true); try { setRobust(await api.scenarioRobust(sessionId, hazard.id)); } catch (e) { setError(e instanceof Error ? e.message : "Check failed"); } setRobustBusy(false); }} />}
        {robust && <p className="k-hint">If one exit is lost, everyone is out in {Math.max(...robust.before.map(r => r.T_s))} s{robust.fixes.length ? <>; widening {robust.fixes[0].name} to {robust.fixes[0].width_m} m brings that worst case to {Math.max(...robust.after.map(r => r.T_s))} s</> : "; no door change improves that"}.</p>}
      </>}
    </>}
  </section>;
}

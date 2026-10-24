import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Audience, Geometry, RobustReport, ScenarioReport, Space, UiEvent } from "../lib/types";

const AUDIENCES: { id: Audience; label: string }[] = [
  { id: "safety_officer", label: "Safety officer" }, { id: "occupant", label: "Occupant" },
  { id: "builder", label: "Builder" }, { id: "regulator", label: "Regulator" },
];
const ICON = { blocker: "Blocker", risk: "Risk", improve: "Improve", info: "Note" } as const;
const ORDER = ["blocker", "risk", "improve", "info"];

export function headline(r: ScenarioReport): string {
  if (r.abstained && !r.evacuation) return "This scenario could not be checked.";
  const e = r.evacuation;
  if (!e) return "No evacuation result.";
  const stranded = Object.values(e.stranded ?? {}).reduce((a, b) => a + b, 0);
  return stranded > 0 || e.evacuated < e.total ? `${e.evacuated} of ${e.total} people get out; ${e.total - e.evacuated} do not` : `Everyone is out in ${e.T_s} s`;
}

export function ScenarioPanel({ geometry, sessionId, selected, onClose, onHighlight, onScenario, onFloor, apply }: {
  geometry: Geometry; sessionId: string; selected: Space | null; onClose: () => void;
  onHighlight: (ids: Set<string>) => void; onScenario: (m: { hazard: string; doors: string[] } | null) => void; onFloor: (id: string) => void; apply: (events: UiEvent[]) => void;
}) {
  const [hazard, setHazard] = useState<Space | null>(null);
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState<Audience>("safety_officer");
  const [report, setReport] = useState<ScenarioReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);
  const [more, setMore] = useState(false);
  const [robust, setRobust] = useState<RobustReport | null>(null);
  const [robustBusy, setRobustBusy] = useState(false);
  useEffect(() => { if (selected) { setHazard(selected); setReport(null); } }, [selected]);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? geometry.spaces.filter(s => s.name.toLowerCase().includes(q)).slice(0, 6) : [];
  }, [query, geometry.spaces]);
  const name = (id: string) => geometry.spaces.find(s => s.id === id)?.name ?? id;
  const doorName = (id: string) => { const o = geometry.openings.find(x => x.id === id); return o ? `${o.space_ids.map(name).join(" / ")} (${o.width_m} m)` : id; };
  const run = async (h = hazard, a = audience) => {
    if (!h) return;
    setBusy(true); setError(""); setApplied(false); setMore(false); setRobust(null);
    try {
      const r = await api.scenario(sessionId, h.id, a);
      setReport(r);
      onHighlight(new Set([h.id, ...(r.evacuation?.bottleneck ?? [])]));
      onScenario({ hazard: h.id, doors: r.evacuation?.bottleneck ?? [] });
      onFloor(h.floor_id);
    } catch (e) { setError(e instanceof Error ? e.message : "Scenario failed"); }
    setBusy(false);
  };
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
  return <section className="stress-drawer scenario-panel" aria-label="Fire / evacuation scenario">
    <header><div><span>Scenario</span><h2>Fire / evacuation</h2></div><button aria-label="Close scenario" onClick={onClose}>Close</button></header>
    <p>{hazard ? <>Hazard room: <b>{hazard.name}</b></> : "Click a room on the plan or 3D view, or search below, to set where the fire starts."}</p>
    {!hazard && busiest && <button className="stress-rerun" disabled={busy} onClick={() => { setHazard(busiest); run(busiest); }}>Quick fire test: {busiest.name} (most seats)</button>}
    <input aria-label="Search rooms" placeholder="Search rooms" value={query} onChange={e => setQuery(e.target.value)} />
    {matches.map(s => <button key={s.id} className="stress-result" onClick={() => { setHazard(s); setReport(null); setQuery(""); onScenario({ hazard: s.id, doors: [] }); onFloor(s.floor_id); onHighlight(new Set([s.id])); }}>{s.name}</button>)}
    <div role="radiogroup" aria-label="Who is this for" className="scenario-audience">
      {AUDIENCES.map(a => <button key={a.id} role="radio" aria-checked={audience === a.id} onClick={() => { setAudience(a.id); if (report) run(hazard, a.id); }}>{a.label}</button>)}
    </div>
    <button className="stress-rerun" disabled={!hazard || busy} onClick={() => run()}>{busy ? "Checking…" : "Run scenario"}</button>
    {error && <p role="alert">Could not run: {error}</p>}
    <div aria-live="polite">{busy && <p>Checking the evacuation…</p>}</div>
    {report && <>
      <h3 className="scenario-headline" role="status">{headline(report)}</h3>
      {report.evacuation?.nearest_exit && report.evacuation.nearest_exit.T_s > report.evacuation.T_s && <p className="scenario-baseline">Everyone using their nearest exit instead: {report.evacuation.nearest_exit.T_s} s ({report.evacuation.nearest_exit.T_s - report.evacuation.T_s} s slower). Exits are planned together here.</p>}
      {report.abstained && !report.evacuation ? <p>Stopped at {abstain ? `step ${abstain.id}: ` : "a step: "}{reason ?? "A step could not be completed."}</p> : <>
        <details><summary>{report.steps.length} steps checked</summary>
          <ol>{report.steps.map(s => <li key={s.id}>{s.ok ? s.summary : `Stopped: ${s.summary}`}</li>)}</ol></details>
        {findings.map((f, i) => <div key={i} className="scenario-finding"><b>{ICON[f.severity]}</b> {f.title}<br /><small>{f.detail}</small></div>)}
        {report.findings.length > 3 && <button onClick={() => setMore(v => !v)}>{more ? "Show fewer" : "Show more"}</button>}
        {hazard && !robust && <button disabled={robustBusy} onClick={async () => { setRobustBusy(true); try { setRobust(await api.scenarioRobust(sessionId, hazard.id)); } catch (e) { setError(e instanceof Error ? e.message : "Check failed"); } setRobustBusy(false); }}>{robustBusy ? "Checking each exit…" : "Check if an exit fails"}</button>}
        {robust && <p className="scenario-robust">If one exit is lost, everyone is out in {Math.max(...robust.before.map(r => r.T_s))} s{robust.fixes.length ? <>; widening {robust.fixes[0].name} to {robust.fixes[0].width_m} m brings that worst case to {Math.max(...robust.after.map(r => r.T_s))} s</> : "; no door change improves that"}.</p>}
        {suggested && fix && <button className="stress-rerun" disabled={applied} onClick={async () => { const { events } = await api.widen(sessionId, fix.element, fix.width_m); apply(events); await run(hazard, audience); setApplied(true); }}>{applied ? "Applied to model" : `Apply to model (widen door to ${fix.width_m} m)`}</button>}
      </>}
    </>}
  </section>;
}

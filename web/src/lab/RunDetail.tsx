import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { FloorRail } from "../components/FloorRail";
import { PlanView } from "../components/PlanView";
import { api, lab, type RunSummary } from "../lib/api";
import type { Geometry, Route } from "../lib/types";
import { PageHead, pct } from "./Lab";

/** One run: score by kind and source, filterable items, and a drill-down with the trace drawn on the plan. */
export default function RunDetail() {
  const { run } = useParams<{ run: string }>();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<{ summary: RunSummary; rows: any[] } | null>(null);
  const [error,setError]=useState('');
  const [kind, setKind] = useState("");
  const [source, setSource] = useState("");
  const [outcome, setOutcome] = useState<"" | "wrong" | "correct">(params.get("only") === "wrong" ? "wrong" : "");
  const [query, setQuery] = useState("");
  const selectedId = params.get("item");

  const reload=()=>{setError('');if(run)void lab.run(run).then(setData).catch(e=>setError(String(e)));};
  useEffect(reload, [run]);
  const rows = useMemo(() => (data?.rows ?? []).filter((r) =>
    (!kind || r.kind === kind) && (!source || r.source === source) &&
    (!outcome || (outcome === "wrong" ? r.correct === false : r.correct === true)) &&
    (!query || JSON.stringify(r).toLowerCase().includes(query.toLowerCase()))), [data, kind, source, outcome, query]);
  if (!data) return <><PageHead title="Run" />{error?<div role="alert">{error}<button onClick={reload}>Retry loading</button></div>:<p role="status">Loading run evidence…</p>}</>;
  const s = data.summary;
  const selected = data.rows.find((r) => r.id === selectedId) ?? null;
  const ci = s.ci95_clustered ?? s.ci95_wilson;

  return (
    <div className="flex min-h-full flex-col">
      <PageHead title={s.suite}>
        <span className="text-sm text-ink-3">{run} · git {s.git} · {s.seconds}s</span>
      </PageHead>
      <div className="grid gap-6 px-6 py-5 lg:grid-cols-[260px_1fr_1fr]">
        <div>
          <p className="font-sign text-[52px] font-bold leading-none">{pct(s.accuracy)}</p>
          <p className="mt-1 text-[15px] text-ink-3">{s.correct} of {s.total} items{ci ? ` · 95 % ${pct(ci[0])}–${pct(ci[1])}` : ""}</p>
          {s.usage?.input_tokens ? <p className="mt-1 text-[14px] text-ink-3">{s.usage.input_tokens.toLocaleString()} in / {(s.usage.output_tokens ?? 0).toLocaleString()} out tokens</p> : null}
        </div>
        <Breakdown title="By kind" table={s.by_kind} active={kind} onPick={setKind} />
        {s.by_source && <Breakdown title="By source" table={s.by_source} active={source} onPick={setSource} />}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-y border-ink bg-white px-6 py-2.5">
        {(["", "wrong", "correct"] as const).map((o) => (
          <button key={o} onClick={() => setOutcome(o)} aria-pressed={outcome === o}
            className={`border px-3 py-1 font-sign text-[15px] ${outcome === o ? "border-ink bg-ink text-white" : "border-concrete-3"}`}>
            {o === "" ? "All" : o === "wrong" ? `Wrong (${data.rows.filter((r) => r.correct === false).length})` : "Correct"}
          </button>
        ))}
        {(kind || source) && <button onClick={() => { setKind(""); setSource(""); }} className="text-sm text-mandatory underline">clear {kind} {source}</button>}
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search id, text, reply…" className="ml-auto h-9 w-64 border border-concrete-3 px-2" />
        <span className="text-sm text-ink-3">{rows.length} shown</span>
      </div>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="max-h-[70vh] overflow-y-auto scroll-thin border-r border-ink lg:max-h-none">
          <table className="w-full text-[14px]">
            <tbody>
              {rows.slice(0, 600).map((r) => (
                <tr key={r.id} onClick={() => setParams({ item: r.id })}
                  className={`cursor-pointer border-b border-concrete-3 ${r.id === selectedId ? "bg-mark/40" : "hover:bg-white"}`}>
                  <td className="w-8 px-3 py-1.5 text-center font-bold">{r.correct === true ? <span className="text-escape" aria-label="correct">✓</span> : r.correct === false ? <span className="text-signal" aria-label="wrong">✕</span> : "·"}</td>
                  <td className="py-1.5 pr-3"><span className="font-medium">{r.id}</span><span className="ml-2 text-ink-3">{r.kind}</span>
                    {r.question && <span className="block truncate text-[13px] text-ink-3">{r.question}</span>}
                    {r.error && <span className="block truncate text-[13px] text-signal">{r.error}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="bg-white lg:sticky lg:top-0 lg:h-screen">{selected ? <ItemDetail row={selected} /> : <p className="p-6 text-ink-3">Select an item to see its question, the expected and given answer, the parse trace and the places on the plan.</p>}</div>
      </div>
    </div>
  );
}

/** Accuracy per category: one magnitude series, ink bars on a recessive track, labels in text tokens. */
function Breakdown({ title, table, active, onPick }: { title: string; table: Record<string, { correct?: number; wrong?: number }>; active: string; onPick: (k: string) => void }) {
  const entries = Object.entries(table).map(([k, v]) => ({ k, c: v.correct ?? 0, n: (v.correct ?? 0) + (v.wrong ?? 0) }))
    .sort((a, b) => a.c / Math.max(a.n, 1) - b.c / Math.max(b.n, 1)).slice(0, 12);
  return (
    <div>
      <h2 className="mb-2 font-sign text-[17px] font-bold">{title}</h2>
      <ul className="space-y-[2px]">
        {entries.map(({ k, c, n }) => {
          const share = c / Math.max(n, 1);
          return (
            <li key={k}>
              <button onClick={() => onPick(active === k ? "" : k)} title={`${k}: ${c}/${n} (${pct(share)})`}
                className={`grid w-full grid-cols-[140px_1fr_74px] items-center gap-2 py-0.5 text-left text-[13.5px] ${active === k ? "font-bold" : ""}`}>
                <span className="truncate">{k}</span>
                <span className="relative h-3 bg-concrete-3"><span className="absolute inset-y-0 left-0 rounded-r-[4px] bg-ink" style={{ width: `${share * 100}%` }} /></span>
                <span className="text-right tabular-nums">{c}/{n}{share < 1 && <span className="ml-1 text-signal">●</span>}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const SPACE_ID = /-F-?\d+-S\d+$/;

function collectIds(value: unknown, out: Set<string>) {
  if (typeof value === "string" && SPACE_ID.test(value)) out.add(value);
  else if (Array.isArray(value)) value.forEach((v) => collectIds(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => collectIds(v, out));
}

function ItemDetail({ row }: { row: any }) {
  const {run}=useParams<{run:string}>();
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [floorId, setFloorId] = useState("");
  const [route, setRoute] = useState<Route | null>(null);
  const building = row.building ?? row.id.split(/-[HQ]\d+/)[0];
  const ids = useMemo(() => {
    const out = new Set<string>();
    collectIds(row.inputs, out); collectIds(row.gold_inputs, out); collectIds(row.result, out); collectIds(row.expected, out);
    return out;
  }, [row]);

  useEffect(() => {
    setRoute(null);
    api.geometry(building).then((g) => {
      setGeometry(g);
      const first = g.spaces.find((s) => ids.has(s.id));
      setFloorId(first?.floor_id ?? g.floors[0].id);
    }).catch(() => setGeometry(null));
    const r = row.result ?? {};
    const stops: string[] = r.stops ?? (r.pickup_space_id ? [row.inputs?.start, r.pickup_space_id, r.target_space_id] : []);
    if (stops.length >= 2 && stops.every(Boolean)) {
      api.routePreview(building, stops.join(","), "", !!row.inputs?.step_free).then(setRoute).catch(() => {});
    }
  }, [row, building, ids]);

  const mismatched = row.gold_inputs && row.inputs ? Object.keys(row.gold_inputs).filter((k) => JSON.stringify(row.gold_inputs[k]) !== JSON.stringify(row.inputs?.[k])) : [];
  return (
    <div className="flex h-full flex-col">
      <div className="max-h-[48%] shrink-0 space-y-3 overflow-y-auto scroll-thin p-5 text-[14.5px]">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 font-sign font-bold text-white ${row.correct ? "bg-escape" : row.correct === false ? "bg-signal" : "bg-ink-3"}`}>{row.correct ? "Correct" : row.correct === false ? "Wrong" : "Unscored"}</span>
          <span className="font-semibold">{row.id}</span><span className="text-ink-3">{row.kind} · {row.source}</span>
          <Link to={`/?building=${building}`} className="ml-auto text-sm text-mandatory underline">open building</Link>
        </div>
        {row.question && <p className="border-l-4 border-ink pl-3 leading-snug">{row.question}</p>}
        {row.reason&&<p role="status">{row.reason}</p>}
        {row.outcome&&<p>Outcome: {row.outcome}. {row.review_source??''}</p>}
        {row.checks&&<details open><summary>Assertions: expected versus observed</summary><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(row.checks,null,2)}</pre></details>}
        {row.review&&<details open><summary>Language review (model, not human)</summary><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(row.review,null,2)}</pre></details>}
        {row.events&&<details><summary>Complete tool and response evidence</summary><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(row.events,null,2)}</pre></details>}
        {row.screenshot&&<a href={`/api/lab/runs/${run}/artifacts/${encodeURIComponent(String(row.screenshot).split(/[\\/]/).at(-1)!)}`} target="_blank" rel="noreferrer"><img alt="Observed UI for this case" loading="lazy" src={`/api/lab/runs/${run}/artifacts/${encodeURIComponent(String(row.screenshot).split(/[\\/]/).at(-1)!)}`}/></a>}
        {row.expected && <Field label="Expected"><span className="font-semibold">{expectedText(row.expected)}</span></Field>}
        {row.reply && <Field label="Reply (last lines)"><pre className="whitespace-pre-wrap font-sans text-[13.5px]">{String(row.reply).split("\n").slice(-4).join("\n")}</pre></Field>}
        {row.parser && <Field label="Path">{row.parser}{row.fallback ? ` → fallback: ${row.fallback}` : ""}{row.readings > 1 ? ` · ${row.readings} readings voted` : ""}</Field>}
        {mismatched.length > 0 && <Field label="Inputs differ from gold"><span className="text-signal">{mismatched.join(", ")}</span></Field>}
        {(row.spec || row.inputs) && (
          <details className="text-[13px]"><summary className="cursor-pointer font-sign font-semibold">Trace</summary>
            <pre className="mt-2 overflow-x-auto bg-concrete-2 p-2">{JSON.stringify({ spec: row.spec, inputs: row.inputs, gold_inputs: row.gold_inputs, result: row.result }, null, 1)}</pre>
          </details>
        )}
        {row.transcript && <pre className="whitespace-pre-wrap bg-concrete-2 p-3 font-sans text-[13.5px]">{row.transcript}</pre>}
      </div>
      {geometry && floorId && (
        <div className="relative min-h-[320px] flex-1 border-t border-ink bg-concrete">
          <PlanView geometry={geometry} floorId={floorId} route={route} highlights={ids} showItems={false} compact />
          <div className="absolute left-2 top-2"><FloorRail floors={geometry.floors} active={floorId} route={route} onPick={setFloorId} /></div>
        </div>
      )}
    </div>
  );
}

function expectedText(e: any): string {
  if (e == null) return "";
  if (e.reachable === false) return "no route";
  if (e.optimal_length_m != null) return `${e.optimal_length_m} m`;
  if (e.asset_id) return `${e.asset_id} in ${e.space_name ?? e.space_id}`;
  if (e.count != null) return String(e.count);
  if (e.accept) return `${e.accept.join(" / ")}${e.area ? `, ${e.area.value} m²` : ""}`;
  if (e.value != null) return `${e.value}${e.unit ? ` ${e.unit}` : ""}`;
  return JSON.stringify(e);
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><p className="text-[12.5px] text-ink-3">{label}</p><div>{children}</div></div>;
}

import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useSearchParams } from "react-router";
import { lab, type RunSummary } from "../lib/api";
import Checks from "./Checks";
import Readiness from './Readiness';
import RunDetail from "./RunDetail";

/** Benchmark Lab: dense, data-first. Same tokens as the Navigator, no sign column. */
export default function Lab() {
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <nav className="flex shrink-0 gap-1 overflow-x-auto bg-ink px-3 py-2 text-white md:w-52 md:flex-col md:px-0 md:py-4">
        <Link to="/" className="px-4 pb-3 font-sign text-lg font-bold">Floorwise <span className="font-normal text-ink-4">Lab</span></Link>
        {[["", "Readiness"], ["checks", "Checks"], ["runs", "History"], ["compare", "Compare runs"], ["advanced", "Run anything"], ["dataset", "Dataset"]].map(([to, label]) => (
          <NavLink key={to} to={`/lab/${to}`} end={to === ""}
            className={({ isActive }) => `whitespace-nowrap px-4 py-2 font-sign text-[15px] ${isActive ? "bg-ink-2 text-mark" : "text-concrete hover:bg-ink-2"}`}>
            {label}
          </NavLink>
        ))}
        <Link to="/" className="mt-auto hidden px-4 py-2 font-sign text-sm text-ink-4 hover:text-white md:block">← Navigator</Link>
      </nav>
      <main className="min-h-0 flex-1 overflow-y-auto scroll-thin">
        <Routes>
          <Route index element={<Readiness />} />
          <Route path="checks" element={<Checks />} />
          <Route path="advanced" element={<Overview />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/:run" element={<RunDetail />} />
          <Route path="compare" element={<Compare />} />
          <Route path="dataset" element={<Dataset />} />
        </Routes>
      </main>
    </div>
  );
}

export const pct = (v: number | null | undefined, digits = 1) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);
const ago = (stamp: string) => {
  const m = stamp.match(/(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/);
  if (!m) return stamp;
  const t = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime();
  const min = Math.round((Date.now() - t) / 60000);
  return min < 60 ? `${min} min ago` : min < 1440 ? `${Math.round(min / 60)} h ago` : `${Math.round(min / 1440)} d ago`;
};
const configKey = (s: RunSummary) => `${s.suite} ${JSON.stringify(Object.fromEntries(Object.entries(s.config ?? {}).filter(([, v]) => v != null && v !== "")))}`;
const configText = (s: RunSummary) =>
  Object.entries(s.config ?? {}).filter(([, v]) => v != null && v !== "" && !(Array.isArray(v) && !v.length)).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`).join(" ");

export function PageHead({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end gap-3 border-b border-ink px-6 pb-4 pt-6">
      <h1 className="font-sign text-[30px] font-bold leading-none">{title}</h1>
      <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>
    </header>
  );
}

/** Trend of accuracy over the last runs of one suite+config: single series, so no legend. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="text-ink-4">–</span>;
  const w = 96, h = 24, min = Math.min(...values, 0.9), max = 1;
  const x = (i: number) => (i / (values.length - 1)) * (w - 4) + 2;
  const y = (v: number) => h - 2 - ((v - min) / Math.max(max - min, 1e-6)) * (h - 4);
  return (
    <svg width={w} height={h} aria-label={`trend ${values.map((v) => pct(v, 0)).join(", ")}`}>
      <polyline points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="var(--color-ink)" strokeWidth={2} strokeLinejoin="round" />
      {values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={6} fill="transparent"><title>{pct(v)}</title></circle>)}
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r={3} fill="var(--color-ink)" />
    </svg>
  );
}

function Overview() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [suites, setSuites] = useState<Awaited<ReturnType<typeof lab.suites>> | null>(null);
  const reload = () => lab.runs().then(setRuns);
  useEffect(() => { reload(); lab.suites().then(setSuites); }, []);

  const groups = useMemo(() => {
    const out = new Map<string, RunSummary[]>();
    for (const r of [...runs].reverse()) out.set(configKey(r), [...(out.get(configKey(r)) ?? []), r]);
    return [...out.entries()].map(([key, list]) => ({ key, list, latest: list[list.length - 1] }))
      .sort((a, b) => b.latest.run.localeCompare(a.latest.run));
  }, [runs]);

  return (
    <div>
      <PageHead title="Overview">
        {suites && (
          <span className={`border px-2.5 py-1 text-sm ${suites.provider.available ? "border-escape text-escape" : "border-signal text-signal"}`}>
            LLM: {suites.provider.name} · {suites.provider.available ? suites.provider.models.chat : "no key"}
          </span>
        )}
      </PageHead>
      <Launcher suites={suites?.suites ?? {}} onDone={reload} />
      <section className="px-6 pb-10">
        <h2 className="mb-2 mt-6 font-sign text-xl font-bold">Latest result per suite</h2>
        <div className="overflow-x-auto border border-ink bg-white">
          <table className="w-full min-w-[820px] text-[14px]">
            <thead className="bg-concrete-2 text-left text-ink-3">
              <tr>{["Suite", "Config", "Score", "95 % interval", "Items", "Buildings", "Trend", "When", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {groups.map(({ key, list, latest }) => {
                const ci = latest.ci95_clustered ?? latest.ci95_wilson;
                const prev = list[list.length - 2];
                const delta = prev && latest.accuracy != null && prev.accuracy != null ? latest.accuracy - prev.accuracy : 0;
                return (
                  <tr key={key} className="border-t border-concrete-3 hover:bg-concrete-2">
                    <td className="px-3 py-2 font-sign text-[15px] font-semibold">{latest.suite}</td>
                    <td className="max-w-[220px] truncate px-3 py-2 text-ink-3" title={configText(latest)}>{configText(latest) || "default"}</td>
                    <td className="px-3 py-2 font-semibold">
                      {pct(latest.accuracy)}
                      {Math.abs(delta) > 1e-9 && <span className={`ml-2 text-[12px] ${delta < 0 ? "text-signal" : "text-escape"}`}>{delta > 0 ? "▲" : "▼"} {pct(Math.abs(delta))}</span>}
                    </td>
                    <td className="px-3 py-2 text-ink-3">{ci ? `${pct(ci[0])} – ${pct(ci[1])}` : "–"}</td>
                    <td className="px-3 py-2">{latest.correct}/{latest.total}</td>
                    <td className="px-3 py-2">{latest.buildings ?? "–"}</td>
                    <td className="px-3 py-2"><Sparkline values={list.slice(-10).map((r) => r.accuracy ?? 0)} /></td>
                    <td className="px-3 py-2 text-ink-3">{ago(latest.run)}</td>
                    <td className="px-3 py-2"><Link to={`/lab/runs/${latest.run}`} className="font-sign font-semibold text-mandatory underline underline-offset-4">Open</Link></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[13px] text-ink-3">Intervals are clustered by building when items carry one (questions from one building are correlated); otherwise Wilson.</p>
      </section>
    </div>
  );
}

const PRESETS: Record<string, string[]> = {
  routes: ["--split", "train,dev"],
  solver: ["--split", "train,dev"],
  parser: ["--split", "dev"],
  e2e: ["--split", "dev"],
  e2e_basic: ["--split", "dev"],
  robust: ["--split", "dev", "--variants", "perturb"],
  metamorphic: ["--split", "dev"],
  build: ["--split", "dev", "--limit", "15"],
  interaction: [],
};

function Launcher({ suites, onDone }: { suites: Record<string, { label: string; llm: boolean | string; args: string[] }>; onDone: () => void }) {
  const [suite, setSuite] = useState("e2e");
  const [args, setArgs] = useState(PRESETS.e2e.join(" "));
  const [log, setLog] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const navigate = useNavigate();

  const start = async () => {
    setRunning(true);
    setLog([]);
    setResult(null);
    try {
      const { id } = await lab.launch(suite, args.split(/\s+/).filter(Boolean));
      await lab.stream(id, (e) => {
        if (e.type === "line") setLog((l) => [...l.slice(-400), e.text ?? ""]);
        if (e.type === "done") setResult(e.run ?? null);
      });
      onDone();
    } catch (err) {
      setLog((l) => [...l, String(err)]);
    } finally {
      setRunning(false);
    }
  };
  const info = suites[suite];
  return (
    <section className="mx-6 mt-6 border border-ink bg-white">
      <div className="flex flex-wrap items-end gap-3 p-4">
        <label className="flex flex-col text-sm text-ink-3">Suite
          <select value={suite} onChange={(e) => { setSuite(e.target.value); setArgs((PRESETS[e.target.value] ?? []).join(" ")); }}
            className="mt-1 h-10 border border-ink bg-white px-2 font-sign text-[16px] text-ink">
            {Object.entries(suites).map(([k, v]) => <option key={k} value={k}>{k} · {v.label}</option>)}
          </select>
        </label>
        <label className="flex min-w-[240px] flex-1 flex-col text-sm text-ink-3">Arguments
          <input value={args} onChange={(e) => setArgs(e.target.value)} className="mt-1 h-10 border border-ink px-2 font-sign text-[16px] text-ink" />
        </label>
        <button onClick={start} disabled={running} className="h-10 bg-ink px-5 font-sign text-[16px] font-bold text-white disabled:opacity-50">
          {running ? "Running…" : "Run"}
        </button>
      </div>
      {info && <p className="px-4 pb-3 text-[13px] text-ink-3">Allowed: {info.args.join(" ")} · {info.llm === true ? "uses the LLM (costs)" : info.llm ? "free unless --parser llm / paraphrase" : "free, offline"}</p>}
      {(log.length > 0 || running) && (
        <div className="border-t border-ink">
          <pre className="scroll-thin max-h-56 overflow-auto bg-ink p-3 text-[12.5px] leading-snug text-concrete">{log.join("\n") || "starting…"}</pre>
          {result && <button onClick={() => navigate(`/lab/runs/${result}`)} className="w-full bg-mark py-2 font-sign font-bold">Open result</button>}
        </div>
      )}
    </section>
  );
}

function Runs() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [suite, setSuite] = useState("");
  useEffect(() => { lab.runs().then(setRuns); }, []);
  const suites = [...new Set(runs.map((r) => r.suite))];
  const shown = runs.filter((r) => !suite || r.suite === suite);
  return (
    <div>
      <PageHead title="Runs">
        <select value={suite} onChange={(e) => setSuite(e.target.value)} className="h-9 border border-ink bg-white px-2 font-sign">
          <option value="">All suites</option>
          {suites.map((s) => <option key={s}>{s}</option>)}
        </select>
      </PageHead>
      <div className="overflow-x-auto px-6 py-4">
        <table className="w-full min-w-[760px] border border-ink bg-white text-[14px]">
          <thead className="bg-concrete-2 text-left text-ink-3"><tr>{["Run", "Suite", "Config", "Score", "Items", "Tokens", "Time", "Git"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.run} className="border-t border-concrete-3 hover:bg-concrete-2">
                <td className="px-3 py-1.5"><Link to={`/lab/runs/${r.run}`} className="text-mandatory underline underline-offset-4">{ago(r.run)}</Link></td>
                <td className="px-3 py-1.5 font-sign font-semibold">{r.suite}</td>
                <td className="max-w-[260px] truncate px-3 py-1.5 text-ink-3">{configText(r)}</td>
                <td className="px-3 py-1.5 font-semibold">{pct(r.accuracy)}</td>
                <td className="px-3 py-1.5">{r.correct}/{r.total}</td>
                <td className="px-3 py-1.5 text-ink-3">{r.usage?.input_tokens ? `${Math.round((r.usage.input_tokens + (r.usage.output_tokens ?? 0)) / 1000)}k` : "–"}</td>
                <td className="px-3 py-1.5 text-ink-3">{r.seconds}s</td>
                <td className="px-3 py-1.5 text-ink-3">{r.git}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Compare() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "", b = params.get("b") ?? "";
  const [data, setData] = useState<Awaited<ReturnType<typeof lab.compare>> | null>(null);
  useEffect(() => { lab.runs().then(setRuns); }, []);
  useEffect(() => { if (a && b) lab.compare(a, b).then(setData); }, [a, b]);
  const pick = (key: "a" | "b", v: string) => setParams({ a, b, [key]: v });
  const option = (r: RunSummary) => <option key={r.run} value={r.run}>{r.suite} · {configText(r)} · {ago(r.run)} · {pct(r.accuracy)}</option>;
  return (
    <div>
      <PageHead title="Compare runs" />
      <div className="flex flex-wrap gap-3 px-6 py-4">
        {(["a", "b"] as const).map((k) => (
          <label key={k} className="flex min-w-[300px] flex-1 flex-col text-sm text-ink-3">{k === "a" ? "Baseline" : "Candidate"}
            <select value={k === "a" ? a : b} onChange={(e) => pick(k, e.target.value)} className="mt-1 h-10 border border-ink bg-white px-2 text-ink">
              <option value="">choose a run</option>{runs.map(option)}
            </select>
          </label>
        ))}
      </div>
      {data && (
        <div className="px-6 pb-10">
          <p className="font-sign text-lg">
            {pct(data.a.accuracy)} → <b>{pct(data.b.accuracy)}</b>
            <span className="ml-4 text-signal">{data.counts.broken ?? 0} broken</span>
            <span className="ml-3 text-escape">{data.counts.fixed ?? 0} fixed</span>
            <span className="ml-3 text-ink-3">{data.counts.changed ?? 0} other changes</span>
          </p>
          <table className="mt-3 w-full border border-ink bg-white text-[14px]">
            <thead className="bg-concrete-2 text-left text-ink-3"><tr>{["Status", "Item", "Kind", "Source"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {data.changes.map((c) => (
                <tr key={c.id} className="border-t border-concrete-3">
                  <td className={`px-3 py-1.5 font-semibold ${c.status === "broken" ? "text-signal" : c.status === "fixed" ? "text-escape" : ""}`}>{c.status === "broken" ? "✕ broken" : c.status === "fixed" ? "✓ fixed" : c.status}</td>
                  <td className="px-3 py-1.5"><Link className="text-mandatory underline underline-offset-4" to={`/lab/runs/${b}?item=${encodeURIComponent(c.id)}`}>{c.id}</Link></td>
                  <td className="px-3 py-1.5">{c.kind}</td>
                  <td className="px-3 py-1.5 text-ink-3">{c.source}</td>
                </tr>
              ))}
              {!data.changes.length && <tr><td className="px-3 py-3 text-ink-3" colSpan={4}>No item changed outcome.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Dataset() {
  const [data, setData] = useState<Awaited<ReturnType<typeof lab.dataset>> | null>(null);
  const [split, setSplit] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => { lab.dataset().then(setData); }, []);
  if (!data) return <PageHead title="Dataset" />;
  const rows = data.buildings.filter((b) => (!split || b.split === split) && (!query || `${b.building_id} ${b.name}`.toLowerCase().includes(query.toLowerCase())));
  return (
    <div>
      <PageHead title="Dataset">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search buildings" className="h-9 border border-ink bg-white px-2" />
        <select value={split} onChange={(e) => setSplit(e.target.value)} className="h-9 border border-ink bg-white px-2 font-sign">
          <option value="">All splits</option>{Object.entries(data.splits).map(([s, n]) => <option key={s} value={s}>{s} ({n})</option>)}
        </select>
      </PageHead>
      <div className="overflow-x-auto px-6 py-4">
        <table className="w-full min-w-[860px] border border-ink bg-white text-[14px]">
          <thead className="bg-concrete-2 text-left text-ink-3"><tr>{["Building", "Split", "Source", "Floors", "Rooms", "Items", "Benchmark questions", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.building_id} className="border-t border-concrete-3 hover:bg-concrete-2">
                <td className="px-3 py-1.5"><span className="font-semibold">{b.name}</span><span className="ml-2 text-ink-3">{b.building_id}</span></td>
                <td className="px-3 py-1.5">{b.split}</td>
                <td className="px-3 py-1.5 text-ink-3">{b.source}</td>
                <td className="px-3 py-1.5">{b.floors}</td>
                <td className="px-3 py-1.5">{b.rooms}</td>
                <td className="px-3 py-1.5">{b.assets}</td>
                <td className="px-3 py-1.5 text-ink-3">{Object.entries(b.kinds).map(([k, n]) => `${k} ${n}`).join(", ") || "–"}</td>
                <td className="px-3 py-1.5"><Link to={`/?building=${b.building_id}`} className="font-sign text-mandatory underline underline-offset-4">Open</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export { ago, configText };
export type { RunSummary };



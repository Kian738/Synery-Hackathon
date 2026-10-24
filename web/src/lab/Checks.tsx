import { useEffect, useState } from "react";
import { Link } from "react-router";
import { lab } from "../lib/api";

/** The Lab's front page: an inspection sheet. One line per check, in plain words, grouped by what the jury
 *  grades; each line says what it proves, the target, the measured result and a pass/fail stamp. */

type Sheet = Awaited<ReturnType<typeof lab.checks>>;
type CheckRow = Sheet["checks"][number];

const pct = (v: number | null | undefined) => (v == null ? "–" : `${(v * 100).toFixed(v >= 0.999 || v <= 0.001 ? 0 : 1)} %`);

function ago(run: string) {
  const m = run.match(/(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/);
  if (!m) return "";
  const minutes = Math.round((Date.now() - new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime()) / 60000);
  return minutes < 1 ? "just now" : minutes < 60 ? `${minutes} min ago` : minutes < 1440 ? `${Math.round(minutes / 60)} h ago` : `${Math.round(minutes / 1440)} days ago`;
}

function Stamp({ status }: { status: string }) {
  const look = status === "pass" ? "border-escape text-escape" : status === "fail" ? "border-signal text-signal" : "border-ink-4 text-ink-3";
  const text = status === "pass" ? "Pass" : status === "fail" ? "Fail" : "Not run";
  return <span className={`inline-block w-[74px] -rotate-2 border-2 py-0.5 text-center font-sign text-[15px] font-bold ${look}`}>{text}</span>;
}

/** Last results of this check as small ticks: one per run, height = score. Single series, no legend needed. */
function History({ values, target }: { values: (number | null)[]; target: number }) {
  if (values.length < 2) return null;
  return (
    <span className="flex h-6 items-end gap-[2px]" title={`Last ${values.length} runs: ${values.map((v) => pct(v)).join(", ")}`}>
      {values.map((v, i) => (
        <span key={i} className={`w-[5px] rounded-t-[2px] ${(v ?? 0) >= target ? "bg-ink-3" : "bg-signal"}`} style={{ height: `${Math.max(12, (v ?? 0) * 100)}%` }} />
      ))}
    </span>
  );
}

export default function Checks() {
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [running, setRunning] = useState<Record<string, string[]>>({});
  const [provider, setProvider] = useState<Awaited<ReturnType<typeof lab.suites>>["provider"] | null>(null);
  const reload = () => lab.checks().then(setSheet);
  useEffect(() => { reload(); lab.suites().then((s) => setProvider(s.provider)); }, []);

  const run = async (key: string, suite: string, args: string[]) => {
    setRunning((r) => ({ ...r, [key]: ["Starting…"] }));
    try {
      const { id } = await lab.launch(suite, args);
      await lab.stream(id, (e) => {
        if (e.type === "line") setRunning((r) => ({ ...r, [key]: [...(r[key] ?? []).slice(-6), e.text ?? ""] }));
      });
    } finally {
      setRunning((r) => { const n = { ...r }; delete n[key]; return n; });
      reload();
    }
  };

  if (!sheet) return <p className="p-8 font-sign text-xl text-ink-3">Loading checks…</p>;
  const failing = sheet.checks.filter((c) => c.status === "fail");
  const notRun = sheet.checks.filter((c) => c.status === "not run");

  return (
    <div className="mx-auto max-w-[1100px] px-6 pb-16 pt-8">
      <header className="flex flex-wrap items-end gap-4 border-b-2 border-ink pb-5">
        <div className="min-w-0 flex-1">
          <h1 className="font-sign text-[40px] font-bold leading-none">
            {sheet.counts.pass} of {sheet.checks.length} checks pass
          </h1>
          <p className="mt-2 max-w-[70ch] text-[16px] text-ink-2">
            {failing.length === 0 ? "Nothing is failing." : <>Needs attention: {failing.map((c) => c.title).join("; ")}.</>}
            {notRun.length > 0 && <> Not run yet: {notRun.map((c) => c.title).join("; ")}.</>}
          </p>
          {provider && (
            <p className="mt-1 text-[14px] text-ink-3">
              Model for LLM checks: {provider.available ? `${provider.name} (${provider.models.chat})` : "none: add a key to .env"}. Every run stops at its token budget.
            </p>
          )}
        </div>
        <button onClick={() => run("all", "gates", [])} disabled={!!running.all}
          className="h-12 bg-ink px-6 font-sign text-[17px] font-bold text-white hover:bg-ink-2 disabled:opacity-60">
          {running.all ? "Running all free checks…" : "Run all free checks"}
        </button>
      </header>
      {running.all && <pre className="mt-3 overflow-x-auto bg-ink p-3 text-[12.5px] text-concrete">{running.all.join("\n")}</pre>}

      {sheet.groups.map((group) => {
        const rows = sheet.checks.filter((c) => c.group === group.id);
        return (
          <section key={group.id} className="mt-10">
            <h2 className="font-sign text-[24px] font-bold">{group.title}</h2>
            <p className="max-w-[75ch] text-[15px] text-ink-3">{group.about}</p>
            <ul className="mt-3 border-t border-ink">
              {rows.map((c) => <CheckLine key={c.id} check={c} log={running[c.id]} onRun={() => run(c.id, c.suite, c.args)} />)}
            </ul>
          </section>
        );
      })}

      <p className="mt-12 text-[14px] text-ink-3">
        Pass means the share of items that pass reaches the target. Scores on few items swing a lot. The run page shows the 95 % range,
        clustered by building because questions from one building are correlated.
      </p>
    </div>
  );
}

function CheckLine({ check, log, onRun }: { check: CheckRow; log?: string[]; onRun: () => void }) {
  const latest = check.latest;
  const wrong = latest ? latest.total - latest.correct : 0;
  return (
    <li className="grid grid-cols-[86px_1fr] gap-x-4 gap-y-1 border-b border-concrete-3 py-4 sm:grid-cols-[86px_1fr_auto]">
      <div className="row-span-2 pt-1"><Stamp status={check.status} /></div>
      <div className="min-w-0">
        <h3 className="font-sign text-[19px] font-semibold leading-tight">{check.title}</h3>
        <p className="mt-0.5 max-w-[70ch] text-[14.5px] text-ink-3">{check.proves}</p>
      </div>
      <div className="col-start-2 flex flex-wrap items-center gap-x-5 gap-y-2 sm:col-start-3 sm:row-start-1 sm:justify-end">
        <div className="text-right">
          <p className="font-sign text-[22px] font-bold tabular-nums leading-none">{latest ? pct(latest.accuracy) : "–"}</p>
          <p className="text-[12.5px] text-ink-3">target {pct(check.target)}</p>
        </div>
        <History values={check.history} target={check.target} />
        <button onClick={onRun} disabled={!!log} className="h-9 border border-ink px-3 font-sign text-[15px] font-semibold hover:bg-ink hover:text-white disabled:opacity-50">
          {log ? "Running…" : "Run"}
        </button>
      </div>
      <div className="col-start-2 flex flex-wrap gap-x-4 text-[13.5px] text-ink-3 sm:col-span-2">
        {latest ? (
          <>
            <span>{latest.correct} of {latest.total} passed</span>
            <span>{ago(latest.run)}</span>
            <span>{check.cost === "free" ? "free to run" : `costs ${check.cost}`}</span>
            {latest.config?.llm && latest.config.llm !== "none" && <span>model {String(latest.config.llm)}</span>}
            <Link to={`/lab/runs/${latest.run}${wrong ? "?only=wrong" : ""}`} className="font-semibold text-mandatory underline underline-offset-4">
              {wrong ? `See the ${wrong} failure${wrong > 1 ? "s" : ""}` : "Open run"}
            </Link>
          </>
        ) : <span>Never run. {check.cost === "free" ? "Free to run." : `Costs ${check.cost}.`}</span>}
      </div>
      {log && <pre className="col-span-full mt-1 overflow-x-auto bg-ink p-2 text-[12px] text-concrete">{log.join("\n")}</pre>}
    </li>
  );
}

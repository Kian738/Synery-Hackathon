import { compareBars } from "../lib/demo";
import type { ScenarioReport } from "../lib/types";

/** Planned together (exact) against the classic heuristic and against everyone using their nearest exit, from the same report. */
export function CompareBars({ report }: { report: ScenarioReport }) {
  const bars = compareBars(report), longest = Math.max(1, ...bars.map(b => b.seconds));
  if (bars.length < 2) return null;
  return <ul className="k-bars" aria-label="Evacuation time by plan">
    {bars.map(b => <li key={b.label} className={`k-bar${b.planned ? " planned" : ""}`} data-seconds={b.seconds}>
      <span>{b.label}</span><span>{b.seconds} s</span><i style={{ width: `${(100 * b.seconds) / longest}%` }} />
    </li>)}
  </ul>;
}

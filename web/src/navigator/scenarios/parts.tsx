import type { ReactNode } from "react";
import { Pictogram } from "../../components/Pictogram";
import { clock, mmss, useClock } from "./clock";

/** The one timeline for every scenario: play/pause, a range on the shared clock, and the time. */
export function Scrubber({ label }: { label: string }) {
  const { t, T, playing } = useClock();
  return <div className="k-stress-scrub k-scen-scrub" data-scrubber="shared">
    <button type="button" className="k-ctl icon" aria-label={playing ? "Pause" : "Play"} onClick={() => (playing ? clock.pause() : clock.play())}><Pictogram name={playing ? "pause" : "play"} size={18} /></button>
    <input type="range" aria-label={label} min={0} max={Math.max(1, Math.round(T))} step={1} value={Math.round(t)} onChange={e => clock.seek(Number(e.target.value))} />
    <output>{mmss(t)}</output>
  </div>;
}

/** Three lines every scenario answers the same way, then a plain legend. */
export function ResultsCard({ total, bottleneck, atRisk, legend }: { total: string; bottleneck: string; atRisk: number; legend: ReactNode }) {
  return <div className="k-scen-results" aria-label="Scenario results">
    <p><span>Everyone out</span><b>{total}</b></p>
    <p><span>Worst bottleneck</span><b>{bottleneck}</b></p>
    <p data-risk={atRisk > 0}><span>People at risk</span><b>{atRisk > 0 ? `${atRisk} cannot get out` : "none"}</b></p>
    <div className="k-scen-legend">{legend}</div>
  </div>;
}

export const LIMITS = "Limits: people and door flow only. No smoke or fire spread is modelled; the smoke shown in 3D is illustrative. No panic behaviour.";

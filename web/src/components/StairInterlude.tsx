import { useEffect, useState } from "react";
import { Pictogram } from "./Pictogram";
import { rideState } from "./LiftShafts";

/** Short overlay shown instead of a stair ride the camera cannot walk honestly (see lib/rideMode). Dims the view, shows the connector
 *  and the floor change, then fades out on the arrival floor. Reduced motion: static. Never takes focus. */
export function StairInterlude({ kind, from, to, reduced }: { kind: string; from: string; to: string; reduced?: boolean }) {
  const lift = kind === "lift";
  return <div className={`k-interlude${reduced ? " k-interlude-static" : ""}`} role="status" aria-live="polite"
    style={{ position: "absolute", inset: 0, pointerEvents: "none", display: "grid", placeItems: "center", background: "rgba(10,14,18,.9)",
      animation: reduced ? undefined : "k-interlude .35s ease-out both" }}>
    <div className="k-interlude-card" style={{ textAlign: "center", color: "#fff" }}>
      <Pictogram name={lift ? "lift" : "stairs"} size={40}/>
      <div className="k-interlude-floors">{from} → {to}</div>
      <div className="k-interlude-note">{lift ? "Taking the lift" : "Taking the stairs"}</div>
    </div>
  </div>;
}

/** Watches the camera's ride and shows the cutout for the whole duration of a ride the camera cannot walk honestly. */
export function InterludeHost({ reduced }: { reduced?: boolean }) {
  const [now, setNow] = useState<typeof rideState.interlude>(null);
  useEffect(() => {
    let id = 0, last = "";
    const tick = () => {
      const r = rideState.interlude, key = r ? `${r.kind}|${r.from}|${r.to}` : "";
      if (key !== last) { last = key; setNow(r ? { ...r } : null); }
      id = window.setTimeout(tick, 120);
    };
    tick();
    return () => window.clearTimeout(id);
  }, []);
  return now ? <StairInterlude kind={now.kind} from={now.from} to={now.to} reduced={reduced} /> : null;
}

import { useEffect, useState } from "react";
import { Pictogram } from "./Pictogram";
import { rideState } from "./LiftShafts";

/** Short overlay shown instead of a stair ride the camera cannot walk honestly (see lib/rideMode). Dims the view, shows the connector
 *  and the floor change, then fades out on the arrival floor. Reduced motion: static. Never takes focus. */
export function StairInterlude({ kind, from, to, reduced }: { kind: string; from: string; to: string; reduced?: boolean }) {
  const lift = kind === "lift";
  return <div className={`k-interlude${reduced ? " k-interlude-static" : ""}`} role="status" aria-live="polite"
    style={{ position: "absolute", inset: 0, pointerEvents: "none", display: "grid", placeItems: "center", background: "#0e1319",
      animation: undefined }}>
    <div className="k-interlude-card" style={{ textAlign: "center", color: "#fff" }}>
      <Pictogram name={lift ? "lift" : "stairs"} size={40}/>
      <div className="k-interlude-floors">{from} → {to}</div>
      <div className="k-interlude-note">{lift ? "Taking the lift" : "Taking the stairs"}</div>
    </div>
  </div>;
}

/** Shows the cutout the moment the camera enters a floor change and keeps it for the whole chain (1 to 4 is one cutout). */
export function InterludeHost({ reduced }: { reduced?: boolean }) {
  const [now, setNow] = useState<typeof rideState.interlude>(null);
  useEffect(() => {
    const sync = () => setNow(rideState.interlude ? { ...rideState.interlude } : null);
    window.addEventListener("floorwise:interlude", sync);
    sync();
    return () => window.removeEventListener("floorwise:interlude", sync);
  }, []);
  return now ? <StairInterlude kind={now.kind} from={now.from} to={now.to} reduced={reduced} /> : null;
}

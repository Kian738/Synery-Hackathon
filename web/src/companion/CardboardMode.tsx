import { useEffect, useRef, useState } from "react";
import { CardboardController, type CardboardStatus } from "./orientation";

const SAY: Record<CardboardStatus, string> = {
  off: "",
  starting: "Waiting for motion data…",
  on: "",
  denied: "Motion access was declined. Allow it in the browser's site settings and try again.",
  unsupported: "This browser has no motion sensors.",
  "no-data": "No motion data arrived. This phone may have no gyroscope, or the page is not HTTPS.",
};

/**
 * Cardboard VR shell: a first-run card, then a full-screen tap surface over the stereo view.
 * Tap: next step. Double tap: recenter. The 3D side reads `cardboardPose` and draws two eyes.
 */
export function CardboardMode({ onActive, onNext, onExit }: { onActive: (on: boolean) => void; onNext: () => void; onExit: () => void }) {
  const [status, setStatus] = useState<CardboardStatus>("off");
  const ctl = useRef<CardboardController | null>(null);
  const tap = useRef<{ t: number; timer: number }>({ t: 0, timer: 0 });
  if (!ctl.current) ctl.current = new CardboardController(setStatus);
  const running = status === "on" || status === "starting";
  useEffect(() => { onActive(running); }, [running, onActive]);
  useEffect(() => () => { ctl.current?.stop(); window.clearTimeout(tap.current.timer); onActive(false); }, [onActive]);
  const exit = () => { ctl.current?.stop(); setStatus("off"); onExit(); };
  const onTap = () => {
    const now = performance.now(), t = tap.current;
    window.clearTimeout(t.timer);
    if (now - t.t < 320) { t.t = 0; ctl.current?.recenter(); return; }
    t.t = now;
    t.timer = window.setTimeout(onNext, 320);
  };
  if (running) return <div className="cardboard-surface" data-testid="cardboard-surface" role="button" tabIndex={0} aria-label="Tap for the next step, double tap to recenter"
    onClick={onTap} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") onNext(); if (e.key === "Escape") exit(); }}>
    <button className="k-ctl cardboard-exit" onClick={e => { e.stopPropagation(); exit(); }}>Exit</button>
    {status === "starting" && <p className="cardboard-wait" role="status">{SAY.starting}</p>}
  </div>;
  return <section className="cardboard-card" role="dialog" aria-label="Cardboard VR">
    <h2>Cardboard VR</h2>
    <ol>
      <li>Turn the phone sideways (landscape).</li>
      <li>Put it in the viewer, screen facing the lenses.</li>
      <li>Look around by turning your head. Tap the viewer button for the next step; double tap to look straight ahead again.</li>
    </ol>
    {SAY[status] && <p className="cardboard-note" role="alert">{SAY[status]}</p>}
    <div className="cardboard-actions">
      <button className="k-ctl" onClick={exit}>Cancel</button>
      <button className="k-ctl accent" onClick={() => void ctl.current?.start()}>Start</button>
    </div>
  </section>;
}

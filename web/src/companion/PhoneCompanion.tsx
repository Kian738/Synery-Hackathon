import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { CompanionClient, REASON_TEXT, type ClientState, type Credentials, type Scheduler, type SocketFactory } from "./client";
import { Glyph } from "./Glyph";
import type { RouteState, StepAction } from "./protocol";
import { browserSensorEnv, detectSensors, GyroLook, pulse, SENSOR_TEXT, type SensorEnv, type SensorStatus } from "./sensors";
import "./companion.css";

export interface PhoneCompanionProps {
  /** Server origin. Defaults to the page's own origin (the phone opened the app from the laptop's server). */
  baseUrl?: string;
  /** Router prefix, default "/companion". */
  prefix?: string;
  /** Pairing code to prefill. When omitted, `#code=123456` in the page URL is read once and removed from the address bar. */
  initialCode?: string;
  /** Where to keep the phone's credentials so a reload of this tab reconnects. Default: sessionStorage. Pass null to disable. */
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  /** Short vibration on step changes where the browser supports it. Never the only cue. Default true. */
  haptics?: boolean;
  /** Degrees of look per dragged pixel. Default 0.3. */
  dragSensitivity?: number;
  onStateChange?: (state: ClientState) => void;
  // Test seams: leave undefined in the app.
  socketFactory?: SocketFactory;
  fetchImpl?: typeof fetch;
  scheduler?: Scheduler;
  sensorEnv?: SensorEnv;
}

const STORE_KEY = "floorwise.companion.phone";
const NUDGE_DEG = 15;

function safeStorage(): PhoneCompanionProps["storage"] {
  try { return typeof sessionStorage === "undefined" ? null : sessionStorage; } catch { return null; }
}
function readCredentials(store: PhoneCompanionProps["storage"]): Credentials | undefined {
  try {
    const parsed = JSON.parse(store?.getItem(STORE_KEY) ?? "null");
    return parsed && typeof parsed.session === "string" && typeof parsed.token === "string" ? parsed : undefined;
  } catch { return undefined; }
}

function takeCodeFromUrl(): string {
  if (typeof location === "undefined") return "";
  const match = /(?:^|[#&])code=(\d{4,10})/.exec(location.hash);
  if (!match) return "";
  try { history.replaceState(null, "", location.pathname + location.search); } catch { /* keep going */ }
  return match[1];
}

/**
 * The phone as a companion/controller. Shows the current instruction large, with Back / Repeat / Next, Recenter and a
 * look pad (drag, or nudge buttons). Motion look is an explicit opt-in. The laptop decides what every action does;
 * nothing here moves the person along the route.
 *
 * Embed it on its own route, e.g. `<Route path="/phone" element={<PhoneCompanion />} />`.
 */
export function PhoneCompanion(props: PhoneCompanionProps) {
  const { baseUrl, prefix, socketFactory, fetchImpl, scheduler, haptics = true, dragSensitivity = 0.3, onStateChange } = props;
  const store = props.storage === undefined ? safeStorage() : props.storage;
  const [state, setState] = useState<ClientState>("idle");
  const [route, setRoute] = useState<RouteState | null>(null);
  const [verify, setVerify] = useState<number | null>(null);
  const [code, setCode] = useState(() => props.initialCode ?? takeCodeFromUrl());
  const [error, setError] = useState("");
  const [ended, setEnded] = useState("");
  const [laptopOnline, setLaptopOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sensor, setSensor] = useState<SensorStatus>("unsupported");
  const [dragging, setDragging] = useState(false);
  const client = useRef<CompanionClient | null>(null);
  const gyro = useRef<GyroLook | null>(null);
  const env = useMemo(() => props.sensorEnv ?? (typeof window !== "undefined" ? browserSensorEnv() : null), [props.sensorEnv]);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const lastStep = useRef<number | null>(null);

  const build = useCallback((resume?: Credentials) => {
    client.current?.disconnect();
    const c = new CompanionClient({ role: "phone", baseUrl, prefix, socketFactory, fetchImpl, scheduler, resume });
    c.on("state", s => { setState(s); onStateChange?.(s); if (s === "paired") setError(""); });
    c.on("route_state", r => setRoute(r));
    c.on("verify", v => setVerify(v));
    c.on("peer", online => setLaptopOnline(online));
    c.on("notice", (codeName, message) => { if (codeName !== "stale_seq" && codeName !== "rate_limited") setError(message); });
    c.on("ended", reason => {
      setEnded(REASON_TEXT[reason] ?? "The connection to the laptop ended.");
      try { store?.removeItem(STORE_KEY); } catch { /* storage unavailable */ }
      gyro.current?.stop();
    });
    client.current = c;
    return c;
  }, [baseUrl, prefix, socketFactory, fetchImpl, scheduler, onStateChange, store]);

  useEffect(() => {
    if (env) setSensor(detectSensors(env));
    const saved = readCredentials(store);
    if (saved) { const c = build(saved); setVerify(saved.verify ?? null); c.resume(); }
    return () => { gyro.current?.stop(); client.current?.disconnect(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pair = async (event: { preventDefault(): void }) => {
    event.preventDefault();
    setError(""); setEnded(""); setBusy(true);
    try {
      const c = build();
      const number = await c.pair(code.replace(/\s+/g, ""));
      setVerify(number);
      try { store?.setItem(STORE_KEY, JSON.stringify(c.credentials)); } catch { /* storage unavailable */ }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not pair.");
    } finally { setBusy(false); }
  };

  const act = (action: StepAction) => {
    client.current?.step(action);
    if (haptics) pulse(action === "repeat" ? 20 : 35);
  };
  // Haptic tick when the laptop moves to a new step: a second cue next to the visible and spoken text.
  useEffect(() => {
    if (route?.step_index === undefined) return;
    if (lastStep.current !== null && lastStep.current !== route.step_index && haptics) pulse([30, 40, 30]);
    lastStep.current = route.step_index;
  }, [route?.step_index, haptics]);

  const look = (dyaw: number, dpitch: number, mode: "touch" | "gyro" = "touch") => client.current?.look(dyaw, dpitch, mode);

  const startGyro = async () => {
    if (!env) return;
    if (!gyro.current) gyro.current = new GyroLook(env, { onDelta: (y, p) => look(y, p, "gyro"), onStatus: setSensor });
    await gyro.current.start();    // runs inside this click handler, as iOS requires
  };
  const stopGyro = () => gyro.current?.stop();
  const recenter = () => { client.current?.recenter(); gyro.current?.recenter(); };

  const onPointerDown = (e: ReactPointerEvent) => { drag.current = { x: e.clientX, y: e.clientY }; setDragging(true); (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); };
  const onPointerMove = (e: ReactPointerEvent) => {
    if (!drag.current) return;
    look((e.clientX - drag.current.x) * dragSensitivity, -(e.clientY - drag.current.y) * dragSensitivity);
    drag.current = { x: e.clientX, y: e.clientY };
  };
  const endDrag = () => { drag.current = null; setDragging(false); };

  const connected = state === "paired";
  const leave = () => {
    client.current?.disconnect(); client.current = null;
    try { store?.removeItem(STORE_KEY); } catch { /* storage unavailable */ }
    setState("idle"); setRoute(null); setVerify(null); setEnded(""); gyro.current?.stop();
  };

  // ---------- views ----------

  if (state === "idle" || state === "pairing" || state === "ended") {
    return (
      <main className="cmp" aria-labelledby="cmp-title">
        <h1 id="cmp-title">Pair with the laptop</h1>
        <p>Open the pairing panel on the laptop, then type the code it shows. The laptop will ask you to confirm.</p>
        <form className="cmp-panel cmp-row" onSubmit={pair}>
          <label htmlFor="cmp-code" className="cmp-small">Pairing code</label>
          <input id="cmp-code" className="cmp-input" value={code} onChange={e => setCode(e.target.value.replace(/[^\d\s]/g, ""))}
            inputMode="numeric" pattern="[0-9 ]*" autoComplete="one-time-code" maxLength={10} aria-describedby="cmp-msg" />
          <button className="cmp-btn primary" type="submit" disabled={busy || code.replace(/\s+/g, "").length < 4}>{busy ? "Pairing…" : "Pair"}</button>
        </form>
        <div id="cmp-msg" role="status" aria-live="polite">
          {ended && <p className="cmp-error">{ended}</p>}
          {error && <p className="cmp-error" role="alert">{error}</p>}
        </div>
        <p className="cmp-small">The code works once and expires in two minutes. Your laptop keeps working on its own if this phone disconnects.</p>
      </main>
    );
  }

  if (state === "waiting") {
    return (
      <main className="cmp" aria-labelledby="cmp-title">
        <h1 id="cmp-title">Confirm on the laptop</h1>
        <p>The laptop is asking whether to allow this phone. Check that it shows the same number:</p>
        <p className="cmp-verify" aria-label={`Verification number ${verify ?? ""}`}>{verify ?? "…"}</p>
        <div role="status" aria-live="polite">{error && <p className="cmp-error">{error}</p>}</div>
        <button className="cmp-btn quiet" onClick={leave}>Cancel</button>
      </main>
    );
  }

  const idle = !route || route.status === "idle";
  const tone = !connected ? "warn" : laptopOnline ? "ok" : "warn";
  const statusText = state === "reconnecting" || state === "connecting" ? "Reconnecting… the laptop keeps working without the phone" : connected ? (laptopOnline ? "Connected to laptop" : "Laptop offline: waiting for it") : "Connecting…";
  const gyroOn = sensor === "active" || sensor === "starting";

  return (
    <main className="cmp" aria-label="Phone companion">
      <div className="cmp-status" data-tone={tone}><span className="cmp-dot" aria-hidden="true" /><span role="status" aria-live="polite">{statusText}</span></div>
      {route?.building_id&&<a className="cmp-open-building" href={`/?building=${encodeURIComponent(route.building_id)}&explore=1`} target="_blank" rel="noopener">Open 3D on this phone ↗</a>}

      <section className="cmp-panel" aria-label="Current instruction">
        {idle ? (
          <><h1>Explore the building</h1><p>Drag below to turn the laptop’s building view. Choose a route on the laptop to get directions here.</p></>
        ) : (
          <>
            <div className="cmp-step">
              <Glyph icon={route!.instruction!.icon} />
              <div>
                <div className="cmp-count">Step {(route!.step_index ?? 0) + 1} of {route!.step_count}{route!.status === "arrived" ? " · Arrived" : ""}{route!.instruction!.metres ? ` · ${Math.round(route!.instruction!.metres!)} m` : ""}</div>

              </div>
            </div>
            <p className="cmp-instruction" aria-live="polite">{route!.instruction!.text}</p>

          </>
        )}
      </section>

      {!idle&&<div className="cmp-row three">
        <button className="cmp-btn" onClick={() => act("back")} disabled={!connected || idle}>Back</button>
        <button className="cmp-btn" onClick={() => act("repeat")} disabled={!connected || idle}>Repeat</button>
        <button className="cmp-btn primary" onClick={() => act("next")} disabled={!connected || idle}>Next</button>
      </div>}

      <section aria-label="Look around" className="cmp-panel cmp-row">
        <div className="cmp-pad" data-active={dragging} role="group" aria-label="Look pad: drag to turn the laptop view"
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerCancel={endDrag}>
          <span>{idle?"Turn the building":"Look around on the laptop"}<br/><span className="cmp-small">Drag left / right · up / down</span></span>
        </div>
        <div className="cmp-row two">
          <button className="cmp-btn" onClick={() => look(-NUDGE_DEG, 0)} disabled={!connected} aria-label="Look left 15 degrees">◀ Look left</button>
          <button className="cmp-btn" onClick={() => look(NUDGE_DEG, 0)} disabled={!connected} aria-label="Look right 15 degrees">Look right ▶</button>
        </div>
        <button className="cmp-btn" onClick={recenter} disabled={!connected}>Recenter view</button>
      </section>

      <details className="cmp-settings"><summary>Motion & connection</summary><section aria-label="Motion look" className="cmp-panel cmp-row">
        <p role="status" aria-live="polite">{SENSOR_TEXT[sensor]}</p>
        {gyroOn ? (
          <button className="cmp-btn" onClick={stopGyro}>Turn off motion look</button>
        ) : (
          <button className="cmp-btn" onClick={startGyro} disabled={!connected || sensor === "unsupported" || sensor === "insecure"}>Turn on motion look</button>
        )}
      </section>

      <button className="cmp-btn quiet" onClick={leave}>Disconnect this phone</button></details>
    </main>
  );
}

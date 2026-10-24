// Optional motion look for the phone. Controls the laptop camera HEADING only: never position, never progress.
//
// Rules this module enforces:
//  - nothing is requested or listened to until startGyro() is called from a user gesture (a click handler);
//  - secure-context rules are respected: on plain-HTTP LAN pages the API is not even attempted;
//  - every failure ends in a status the UI can explain, and the touch controls never depend on any of it.
import { wrapDeg } from "./protocol";

export type SensorStatus = "unsupported" | "insecure" | "needs-permission" | "ready" | "denied" | "starting" | "active" | "no-data";

/** The browser surface this module touches, injectable for tests. */
export interface SensorEnv {
  isSecureContext: boolean;
  /** Present when the browser has DeviceOrientationEvent at all. */
  hasOrientationEvent: boolean;
  /** iOS Safari: must be called from a click and resolves "granted" | "denied". */
  requestPermission?: () => Promise<"granted" | "denied" | string>;
  addOrientationListener(fn: (e: OrientationSample) => void): void;
  removeOrientationListener(fn: (e: OrientationSample) => void): void;
  /** Degrees: 0, 90, 180, 270 (screen.orientation.angle, or window.orientation as a fallback). */
  screenAngle(): number;
  /** Subscribes to screen rotation; returns an unsubscribe. */
  onScreenRotate(fn: () => void): () => void;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(id: unknown): void;
}
export interface OrientationSample { alpha: number | null; beta: number | null; gamma: number | null }

export function browserSensorEnv(win: Window & typeof globalThis = window): SensorEnv {
  const DOE = (win as unknown as { DeviceOrientationEvent?: { requestPermission?: () => Promise<string> } }).DeviceOrientationEvent;
  const map = new Map<(e: OrientationSample) => void, EventListener>();
  return {
    isSecureContext: win.isSecureContext === true,
    hasOrientationEvent: typeof DOE !== "undefined",
    requestPermission: typeof DOE?.requestPermission === "function" ? () => DOE.requestPermission!() : undefined,
    addOrientationListener(fn) {
      const wrapped = ((e: DeviceOrientationEvent) => fn({ alpha: e.alpha, beta: e.beta, gamma: e.gamma })) as EventListener;
      map.set(fn, wrapped);
      win.addEventListener("deviceorientation", wrapped);
    },
    removeOrientationListener(fn) { const w = map.get(fn); if (w) win.removeEventListener("deviceorientation", w); map.delete(fn); },
    screenAngle() { return win.screen?.orientation?.angle ?? ((win as unknown as { orientation?: number }).orientation ?? 0); },
    onScreenRotate(fn) {
      const target = win.screen?.orientation;
      if (target?.addEventListener) { target.addEventListener("change", fn); return () => target.removeEventListener("change", fn); }
      win.addEventListener("orientationchange", fn);
      return () => win.removeEventListener("orientationchange", fn);
    },
    setTimeout: (fn, ms) => win.setTimeout(fn, ms),
    clearTimeout: id => win.clearTimeout(id as number),
  };
}

/** What can be said before the user acts. Never prompts. */
export function detectSensors(env: SensorEnv): SensorStatus {
  if (!env.hasOrientationEvent) return "unsupported";
  if (!env.isSecureContext) return "insecure";
  return env.requestPermission ? "needs-permission" : "ready";
}

export const SENSOR_TEXT: Record<SensorStatus, string> = {
  unsupported: "This browser has no motion sensors. Use the touch controls.",
  insecure: "Motion look needs a secure page (HTTPS, or this phone opening the app as localhost). Over plain Wi-Fi HTTP the touch controls still work.",
  "needs-permission": "Motion look is off. Turn it on to look around by turning your phone.",
  ready: "Motion look is off. Turn it on to look around by turning your phone.",
  denied: "Motion access was declined. The touch controls work as before. You can allow it later in the browser's site settings.",
  starting: "Waiting for motion data…",
  active: "Motion look is on. Turn your phone to look around. Your position on the route does not change.",
  "no-data": "No motion data arrived. This device may have no gyroscope. Use the touch controls.",
};

// ---------- pure math ----------

type V3 = [number, number, number];
const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Device-to-world rotation from alpha/beta/gamma (W3C Device Orientation, Z-X'-Y'' order). World: x east, y north, z up. */
function deviceToWorld(alpha: number, beta: number, gamma: number, v: V3): V3 {
  const [a, b, g] = [rad(alpha), rad(beta), rad(gamma)];
  // Ry(gamma)
  let [x, y, z] = v;
  [x, z] = [x * Math.cos(g) + z * Math.sin(g), -x * Math.sin(g) + z * Math.cos(g)];
  // Rx(beta)
  [y, z] = [y * Math.cos(b) - z * Math.sin(b), y * Math.sin(b) + z * Math.cos(b)];
  // Rz(alpha)
  [x, y] = [x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a)];
  return [x, y, z];
}

export interface Look { yaw: number; pitch: number; basis: "camera" | "screen-top" }

/**
 * Where the phone is looking. Held upright it is the direction of the back camera (like a window); held flat it is
 * the direction the top of the screen points (like a map), using the current screen rotation so rotating the
 * screen does not read as turning. yaw: degrees clockwise from north; pitch: degrees up.
 */
export function lookFromOrientation(s: OrientationSample, screenAngle: number): Look | null {
  if (s.alpha === null || s.beta === null || s.gamma === null || ![s.alpha, s.beta, s.gamma].every(Number.isFinite)) return null;
  const camera = deviceToWorld(s.alpha, s.beta, s.gamma, [0, 0, -1]);
  const theta = rad(screenAngle);
  const top = deviceToWorld(s.alpha, s.beta, s.gamma, [Math.sin(theta), Math.cos(theta), 0]);
  const basis = Math.abs(camera[2]) < 0.8 ? "camera" : "screen-top";
  const [x, y, z] = basis === "camera" ? camera : top;
  return { yaw: deg(Math.atan2(x, y)), pitch: deg(Math.asin(Math.max(-1, Math.min(1, z)))), basis };
}

/** Change in look between two samples, or null when they are not comparable (basis changed). Right/up positive. */
export function lookDelta(prev: Look, next: Look): { dyaw: number; dpitch: number } | null {
  if (prev.basis !== next.basis) return null;
  return { dyaw: wrapDeg(next.yaw - prev.yaw), dpitch: next.pitch - prev.pitch };
}

// ---------- controller ----------

export interface GyroOptions {
  onDelta(dyaw: number, dpitch: number): void;
  onStatus(status: SensorStatus): void;
  /** Ignore changes smaller than this many degrees (sensor noise). */
  deadzoneDeg?: number;
  /** Give up waiting for the first sample after this long. */
  firstSampleMs?: number;
}

export class GyroLook {
  status: SensorStatus;
  private prev: Look | null = null;
  private listener: ((e: OrientationSample) => void) | null = null;
  private offRotate: (() => void) | null = null;
  private timer: unknown = null;

  constructor(private readonly env: SensorEnv, private readonly o: GyroOptions) {
    this.status = detectSensors(env);   // detection only: no prompt, no listener
  }

  private set(status: SensorStatus) { this.status = status; this.o.onStatus(status); }

  /** Must run inside a user gesture (click). Resolves with the resulting status. */
  async start(): Promise<SensorStatus> {
    if (this.listener) return this.status;
    const before = detectSensors(this.env);
    if (before === "unsupported" || before === "insecure") { this.set(before); return before; }
    if (this.env.requestPermission) {
      let answer: string;
      try { answer = await this.env.requestPermission(); } catch { answer = "denied"; }
      if (answer !== "granted") { this.set("denied"); return "denied"; }
    }
    this.set("starting");
    this.prev = null;
    this.listener = sample => this.onSample(sample);
    this.env.addOrientationListener(this.listener);
    this.offRotate = this.env.onScreenRotate(() => { this.prev = null; });   // never treat a screen rotation as a turn
    this.timer = this.env.setTimeout(() => { if (this.status === "starting") { this.stop(); this.set("no-data"); } }, this.o.firstSampleMs ?? 2000);
    return this.status;
  }

  /** Forget the current pose: the next sample becomes the new zero. */
  recenter() { this.prev = null; }

  stop() {
    if (this.listener) this.env.removeOrientationListener(this.listener);
    this.listener = null;
    this.offRotate?.(); this.offRotate = null;
    if (this.timer !== null) this.env.clearTimeout(this.timer);
    this.timer = null;
    this.prev = null;
    if (this.status === "active" || this.status === "starting") this.set(detectSensors(this.env));
  }

  private onSample(sample: OrientationSample) {
    const look = lookFromOrientation(sample, this.env.screenAngle());
    if (!look) return;                                          // desktop browsers fire one event full of nulls
    if (this.status === "starting") { this.set("active"); if (this.timer !== null) this.env.clearTimeout(this.timer); this.timer = null; }
    const prev = this.prev;
    this.prev = look;
    if (!prev) return;
    const d = lookDelta(prev, look);
    if (!d) return;
    const dead = this.o.deadzoneDeg ?? 0.15;
    if (Math.abs(d.dyaw) < dead && Math.abs(d.dpitch) < dead) { this.prev = prev; return; }   // accumulate until it clears the noise floor
    this.o.onDelta(d.dyaw, d.dpitch);
  }
}

// ---------- haptics ----------

/** Optional, capability-detected, never the only cue. Returns whether a pulse was requested. */
export function pulse(pattern: number | number[], nav: { vibrate?: (p: number | number[]) => boolean } | undefined = typeof navigator !== "undefined" ? navigator : undefined): boolean {
  try { return typeof nav?.vibrate === "function" ? nav.vibrate(pattern) : false; } catch { return false; }
}

// Cardboard VR head tracking: the phone's absolute orientation as a camera quaternion, plus a small controller
// (permission, wake lock, fullscreen, landscape lock, recenter). Pure maths, no three.js, so the main bundle stays small.
//
// Maths: the W3C DeviceOrientation angles (alpha about z, beta about x', gamma about y'') mapped to a y-up camera, the
// recipe of three.js DeviceOrientationControls: Euler(beta, alpha, -gamma, "YXZ"), then -90 degrees about X (the camera
// looks out of the back of the phone, not out of the top), then the screen rotation undone about Z.
import { browserSensorEnv, type OrientationSample, type SensorEnv } from "./sensors";

export type Quat = [number, number, number, number];   // x, y, z, w (three.js order)

const rad = (d: number) => (d * Math.PI) / 180;

export function multiply(a: Quat, b: Quat): Quat {
  const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
  return [ax * bw + aw * bx + ay * bz - az * by, ay * bw + aw * by + az * bx - ax * bz, az * bw + aw * bz + ax * by - ay * bx, aw * bw - ax * bx - ay * by - az * bz];
}

export function axisAngle(axis: [number, number, number], angle: number): Quat {
  const s = Math.sin(angle / 2);
  return [axis[0] * s, axis[1] * s, axis[2] * s, Math.cos(angle / 2)];
}

/** Rotates a vector by a unit quaternion. */
export function rotate(q: Quat, v: [number, number, number]): [number, number, number] {
  const [x, y, z, w] = q, [vx, vy, vz] = v;
  const tx = 2 * (y * vz - z * vy), ty = 2 * (z * vx - x * vz), tz = 2 * (x * vy - y * vx);
  return [vx + w * tx + y * tz - z * ty, vy + w * ty + z * tx - x * tz, vz + w * tz + x * ty - y * tx];
}

/** Camera quaternion (three.js world: y up, camera looks down -z) for alpha/beta/gamma in degrees and the screen angle in degrees. */
export function quaternionFromOrientation(alpha: number, beta: number, gamma: number, screenAngle: number): Quat {
  const x = rad(beta) / 2, y = rad(alpha) / 2, z = rad(-gamma) / 2;
  const c1 = Math.cos(x), c2 = Math.cos(y), c3 = Math.cos(z), s1 = Math.sin(x), s2 = Math.sin(y), s3 = Math.sin(z);
  const euler: Quat = [s1 * c2 * c3 + c1 * s2 * s3, c1 * s2 * c3 - s1 * c2 * s3, c1 * c2 * s3 - s1 * s2 * c3, c1 * c2 * c3 + s1 * s2 * s3];   // "YXZ"
  const backCamera: Quat = [-Math.SQRT1_2, 0, 0, Math.SQRT1_2];   // -90 degrees about X
  return multiply(multiply(euler, backCamera), axisAngle([0, 0, 1], -rad(screenAngle)));
}

/** Compass yaw of the camera's forward direction, radians about +Y (0 = looking down -Z). */
export function yawOf(q: Quat): number {
  const [fx, , fz] = rotate(q, [0, 0, -1]);
  return Math.atan2(-fx, -fz);
}

/** Removes a yaw offset so that the pose at recenter time looks straight ahead (down -Z). Pitch and roll are kept. */
export function recentered(q: Quat, yaw0: number): Quat {
  return multiply(axisAngle([0, 1, 0], -yaw0), q);
}

// ---------- shared pose (read every frame by the 3D route camera) ----------

/** `current` is the recentered device quaternion while Cardboard VR runs, otherwise null. */
export const cardboardPose: { current: Quat | null } = { current: null };

export type CardboardStatus = "off" | "starting" | "on" | "denied" | "unsupported" | "no-data";

/** Wake lock that comes back after the tab was hidden (the browser drops it on visibility change). */
function keepAwake(): () => void {
  type Sentinel = { release(): Promise<void> };
  const wl = (navigator as unknown as { wakeLock?: { request(t: "screen"): Promise<Sentinel> } }).wakeLock;
  if (!wl) return () => {};
  let sentinel: Sentinel | null = null, alive = true;
  const take = () => { if (alive && document.visibilityState === "visible") wl.request("screen").then(s => { if (alive) sentinel = s; else void s.release(); }).catch(() => {}); };
  const onVis = () => take();
  take();
  document.addEventListener("visibilitychange", onVis);
  return () => { alive = false; document.removeEventListener("visibilitychange", onVis); void sentinel?.release().catch(() => {}); sentinel = null; };
}

/** True when the page could receive orientation events at all (the button is hidden otherwise). */
export function cardboardSupported(win: Window = window): boolean {
  return typeof (win as unknown as { DeviceOrientationEvent?: unknown }).DeviceOrientationEvent !== "undefined" && win.matchMedia?.("(pointer: coarse)").matches === true;
}

export class CardboardController {
  private listener: ((s: OrientationSample) => void) | null = null;
  private yaw0: number | null = null;
  private release: (() => void) | null = null;
  private timer = 0;
  constructor(private readonly onStatus: (s: CardboardStatus) => void, private readonly env: SensorEnv = browserSensorEnv()) {}

  /** Call from a click: permission, fullscreen and the landscape lock all need a user gesture. */
  async start(): Promise<CardboardStatus> {
    if (this.listener) return "on";
    if (!this.env.hasOrientationEvent) { this.onStatus("unsupported"); return "unsupported"; }
    const root = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void };
    const full = root.requestFullscreen ? root.requestFullscreen().catch(() => {}) : Promise.resolve(root.webkitRequestFullscreen?.());
    if (this.env.requestPermission) {
      let answer = "denied";
      try { answer = await this.env.requestPermission(); } catch { /* treated as denied */ }
      if (answer !== "granted") { this.onStatus("denied"); return "denied"; }
    }
    void full.then(() => (screen.orientation as unknown as { lock?: (o: string) => Promise<void> })?.lock?.("landscape")).catch(() => {});
    this.release = keepAwake();
    this.yaw0 = null;
    this.onStatus("starting");
    this.listener = s => {
      if (s.alpha === null || s.beta === null || s.gamma === null) return;
      const q = quaternionFromOrientation(s.alpha, s.beta, s.gamma, this.env.screenAngle());
      if (this.yaw0 === null) { this.yaw0 = yawOf(q); window.clearTimeout(this.timer); this.onStatus("on"); }
      cardboardPose.current = recentered(q, this.yaw0);
    };
    this.env.addOrientationListener(this.listener);
    this.timer = window.setTimeout(() => { if (this.yaw0 === null) { this.stop(); this.onStatus("no-data"); } }, 2500);
    return "starting";
  }

  /** The next sample's heading becomes "straight ahead along the route". */
  recenter() { this.yaw0 = null; }

  stop() {
    if (this.listener) this.env.removeOrientationListener(this.listener);
    this.listener = null;
    window.clearTimeout(this.timer);
    cardboardPose.current = null;
    this.release?.(); this.release = null;
    (screen.orientation as unknown as { unlock?: () => void })?.unlock?.();
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
  }
}

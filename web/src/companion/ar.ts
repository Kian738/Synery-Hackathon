/** Phone AR overlay helpers: pure geometry (testable without a headset) and feature detection.
 *  Plan frame: x east, y north, metres. AR local-floor frame (WebXR / three.js): x east, y up, z = -north, origin where the session starts. */

export type Pt = [number, number];

export interface ArPlacement { origin: Pt; /** compass heading (degrees clockwise from north) the phone faced when the person pressed "start here" */ headingDeg: number }

/** Plan metres to local-floor metres. The person stands at `origin` facing `headingDeg`; the AR session's -Z axis is where the phone points. */
export function toArLocal(p: Pt, place: ArPlacement): [number, number, number] {
  const dx = p[0] - place.origin[0], dy = p[1] - place.origin[1];
  const a = (place.headingDeg * Math.PI) / 180;           // rotate the plan so that "ahead" is -Z
  const ahead = dx * Math.sin(a) + dy * Math.cos(a);       // component along the facing direction
  const right = dx * Math.cos(a) - dy * Math.sin(a);       // component to the right of it
  return [right, 0, -ahead];
}

/** A flat ribbon along the path: two vertices per point, `width` metres wide, just above the floor. Returns positions and triangle indices. */
export function ribbon(path: Pt[], place: ArPlacement, width = 0.35, lift = 0.02): { positions: number[]; indices: number[] } {
  const local = path.map(p => toArLocal(p, place));
  const positions: number[] = [], indices: number[] = [];
  local.forEach((p, i) => {
    const a = local[Math.max(0, i - 1)], b = local[Math.min(local.length - 1, i + 1)];
    let tx = b[0] - a[0], tz = b[2] - a[2]; const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    positions.push(p[0] - tz * width / 2, lift, p[2] + tx * width / 2, p[0] + tz * width / 2, lift, p[2] - tx * width / 2);
    if (i > 0) { const k = (i - 1) * 2; indices.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
  });
  return { positions, indices };
}

/** Metres left until the next decision point, and a unit direction (in AR local space) to it, for the on-screen arrow. */
export function nextTurn(path: Pt[], place: ArPlacement): { distance: number; direction: [number, number] } | null {
  if (path.length < 2) return null;
  const local = path.map(p => toArLocal(p, place));
  const d = Math.hypot(local[1][0], local[1][2]) || 1;
  return { distance: Math.hypot(local[local.length - 1][0], local[local.length - 1][2]), direction: [local[1][0] / d, local[1][2] / d] };
}

type XrNavigator = { xr?: { isSessionSupported(mode: string): Promise<boolean> } };

/** What this phone can do. iOS Safari has no WebXR AR: it gets the compass arrow instead. */
export async function arSupport(nav: XrNavigator = typeof navigator === "undefined" ? {} : (navigator as unknown as XrNavigator)): Promise<{ ar: boolean; vr: boolean }> {
  const ask = async (mode: string) => { try { return !!(await nav.xr?.isSessionSupported(mode)); } catch { return false; } };
  return { ar: await ask("immersive-ar"), vr: await ask("immersive-vr") };
}

/** Which way to turn: signed angle in degrees between where the phone points and the next path direction (positive = turn right). */
export function turnAngle(headingDeg: number, path: Pt[]): number | null {
  if (path.length < 2) return null;
  const want = (Math.atan2(path[1][0] - path[0][0], path[1][1] - path[0][1]) * 180) / Math.PI;
  return ((want - headingDeg + 540) % 360) - 180;
}

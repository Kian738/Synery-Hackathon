// Z-fighting audit for the procedural models: two boxes of different colour whose outward faces face the same way,
// lie in the same plane (within EPS) and overlap in area flicker when the camera is far. Pure data, no three.js.
import type { AssetPart } from "./parts";

export const ZFIGHT_EPS_M = 0.0015;
export interface Coplanar { a: number; b: number; axis: "x" | "y" | "z"; side: "+" | "-"; at: number; overlapM2: number }

type Box = { lo: [number, number, number]; hi: [number, number, number] };

function boxOf(p: AssetPart, w: number, d: number): Box | null {
  if (p.shape !== "box" || (p.rotation && p.rotation.some(r => Math.abs(r) > 1e-6))) return null;
  const c = [p.position[0] * w, p.position[1], p.position[2] * d], s = [p.scale[0] * w, p.scale[1], p.scale[2] * d];
  return { lo: [c[0] - s[0] / 2, c[1] - s[1] / 2, c[2] - s[2] / 2], hi: [c[0] + s[0] / 2, c[1] + s[1] / 2, c[2] + s[2] / 2] };
}

export function coplanarFaces(parts: AssetPart[], w: number, d: number): Coplanar[] {
  const boxes = parts.map(p => boxOf(p, w, d));
  const out: Coplanar[] = [];
  for (let i = 0; i < parts.length; i++) for (let j = i + 1; j < parts.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (!a || !b || parts[i].color === parts[j].color) continue;
    for (let k = 0; k < 3; k++) {
      const u = (k + 1) % 3, v = (k + 2) % 3;
      const overlap = Math.min(a.hi[u], b.hi[u]) - Math.max(a.lo[u], b.lo[u]);
      const overlap2 = Math.min(a.hi[v], b.hi[v]) - Math.max(a.lo[v], b.lo[v]);
      if (overlap <= ZFIGHT_EPS_M || overlap2 <= ZFIGHT_EPS_M) continue;
      for (const side of ["+", "-"] as const) {
        if (k === 1 && side === "-") continue; // downward faces are hidden by the floor or the thing they stand on
        const pa = side === "+" ? a.hi[k] : a.lo[k], pb = side === "+" ? b.hi[k] : b.lo[k];
        if (Math.abs(pa - pb) <= ZFIGHT_EPS_M) out.push({ a: i, b: j, axis: "xyz"[k] as "x", side, at: pa, overlapM2: overlap * overlap2 });
      }
    }
  }
  return out;
}

export const ZFIGHT_PUSH_M = 0.003;
const volume = (b: Box) => (b.hi[0] - b.lo[0]) * (b.hi[1] - b.lo[1]) * (b.hi[2] - b.lo[2]);

/** Guard rail for every model: where two differently coloured boxes still share a face plane, the larger one is recessed 3 mm on that face
 *  (the detail stays on the footprint edge; a part thinner than 1 cm grows 3 mm outward instead). */
export function separateCoplanar(parts: AssetPart[], w: number, d: number): AssetPart[] {
  const out = parts.map(p => ({ ...p, position: [...p.position] as AssetPart["position"], scale: [...p.scale] as AssetPart["scale"] }));
  for (let pass = 0; pass < 8; pass++) {
    const hits = coplanarFaces(out, w, d);
    if (!hits.length) break;
    const done = new Set<number>();
    for (const h of hits) {
      const k = "xyz".indexOf(h.axis), size = k === 0 ? w : k === 2 ? d : 1, dir = h.side === "+" ? 1 : -1;
      const ba = boxOf(out[h.a], w, d)!, bb = boxOf(out[h.b], w, d)!;
      const larger = volume(ba) > volume(bb) || (volume(ba) === volume(bb) && h.a < h.b) ? h.a : h.b;
      const smaller = larger === h.a ? h.b : h.a;
      const thin = (i: number) => out[i].scale[k] * size < 0.01;
      const [mover, sign] = thin(larger) ? [smaller, 1] : [larger, -1];
      const key = mover * 6 + k * 2 + (dir > 0 ? 1 : 0);
      if (done.has(key)) continue;
      done.add(key);
      const p = out[mover];
      p.position[k] = Math.round((p.position[k] + (sign * dir * ZFIGHT_PUSH_M) / 2 / size) * 1e5) / 1e5;
      p.scale[k] = Math.round((p.scale[k] + (sign * ZFIGHT_PUSH_M) / size) * 1e5) / 1e5;
    }
  }
  return out;
}

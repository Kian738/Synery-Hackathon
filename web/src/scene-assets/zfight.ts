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

export const ZFIGHT_STEP_M = 0.0022;
const volume = (b: Box) => (b.hi[0] - b.lo[0]) * (b.hi[1] - b.lo[1]) * (b.hi[2] - b.lo[2]);

/** Guard rail for every model. Parts that share one face plane (same axis, same side, different colours) form a group. Details (parts thinner
 *  than 4 cm along that axis: door fronts, panels, labels) keep their faces; the bodies step back 2.2 mm behind the innermost detail
 *  face, all by the same amount, so same-coloured neighbours stay flush. Two passes at most; a part never changes by more than a few mm.
 *  Parts too thin to step back are left alone (the audit test reports them). */
export function separateCoplanar(parts: AssetPart[], w: number, d: number): AssetPart[] {
  let out = parts.map(p => ({ ...p, position: [...p.position] as AssetPart["position"], scale: [...p.scale] as AssetPart["scale"] }));
  for (let pass = 0; pass < 4; pass++) out = separatePass(out, w, d);
  return out;
}

function separatePass(out: AssetPart[], w: number, d: number): AssetPart[] {
  const hits = coplanarFaces(out, w, d);
  if (!hits.length) return out;
  const boxes = out.map(p => boxOf(p, w, d));
  const parent = new Map<string, string>();
  const find = (x: string): string => { let r = x; while ((parent.get(r) ?? r) !== r) r = parent.get(r)!; parent.set(x, r); return r; };
  const key = (i: number, h: Coplanar) => `${h.axis}${h.side}:${i}`;
  for (const h of hits) { const a = find(key(h.a, h)), b = find(key(h.b, h)); if (a !== b) parent.set(a, b); }
  const groups = new Map<string, number[]>();
  for (const h of hits) for (const i of [h.a, h.b]) {
    const root = find(key(i, h)), list = groups.get(root) ?? [];
    if (!list.includes(i)) list.push(i);
    groups.set(root, list);
  }
  for (const [root, members] of groups) {
    const k = "xyz".indexOf(root[0]), plus = root[1] === "+", dir = plus ? 1 : -1, size = k === 0 ? w : k === 2 ? d : 1;
    const plane = (i: number) => (plus ? boxes[i]!.hi[k] : boxes[i]!.lo[k]);
    const thick = (i: number) => boxes[i]!.hi[k] - boxes[i]!.lo[k];
    // details (door fronts, panels, labels: thinner than 4 cm along this axis, else the single thinnest part) keep their faces;
    // everything else steps back 2.2 mm behind the innermost detail face, together, so same-coloured neighbours stay flush with each other
    const thin = members.filter(i => thick(i) <= 0.04);
    const details = thin.length && thin.length < members.length ? thin
      : [members.reduce((best, i) => (thick(i) < thick(best) - 1e-9 || (Math.abs(thick(i) - thick(best)) <= 1e-9 && volume(boxes[i]!) < volume(boxes[best]!)) ? i : best))];
    const innermost = details.map(plane).reduce((m, v) => (plus ? Math.min(m, v) : Math.max(m, v)));
    const target = innermost - dir * ZFIGHT_STEP_M;
    for (const i of members) {
      if (details.includes(i)) continue;
      const delta = target - plane(i), next = out[i].scale[k] + (plus ? delta : -delta) / size;
      if (Math.abs(delta) < 1e-9 || next * size < 0.004) continue;
      out[i].position[k] = Math.round((out[i].position[k] + delta / 2 / size) * 1e5) / 1e5;
      out[i].scale[k] = Math.round(next * 1e5) / 1e5;
    }
  }
  return out;
}

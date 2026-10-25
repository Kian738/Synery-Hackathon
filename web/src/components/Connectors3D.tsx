import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import {alignStairFrame} from "../lib/stairFrame";
import type { Connector, Geometry, Space, XY } from "../lib/types";

/** Real-size stairwells and lift shafts, built from the supplied stair and lift spaces and floor elevations.
 *  Stairs are dog-leg flights sized to the space (tread depth and riser from the rise), lifts a car in a shaft.
 *  Everything is generated from the data: no stair interior is supplied, so the arrangement is illustrative. */

export interface Box { x: number; y: number; z: number; sx: number; sy: number; sz: number; yaw: number; tilt: number; color: string; emissive?: boolean }

interface OrientedRect { cx: number; cy: number; ux: number; uy: number; length: number; width: number }

/** Smallest-area oriented rectangle around a polygon; `length` is the long side, `u` its direction. */
export function orientedRect(points: XY[]): OrientedRect {
  let best: OrientedRect | null = null, bestArea = Infinity;
  for (let i = 0; i < points.length; i++) {
    const a = points[i], b = points[(i + 1) % points.length];
    const dx = b[0] - a[0], dy = b[1] - a[1], norm = Math.hypot(dx, dy);
    if (norm < 1e-6) continue;
    const ux = dx / norm, uy = dy / norm;
    let minS = Infinity, maxS = -Infinity, minT = Infinity, maxT = -Infinity;
    for (const p of points) {
      const s = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy, t = -(p[0] - a[0]) * uy + (p[1] - a[1]) * ux;
      minS = Math.min(minS, s); maxS = Math.max(maxS, s); minT = Math.min(minT, t); maxT = Math.max(maxT, t);
    }
    const area = (maxS - minS) * (maxT - minT);
    if (area < bestArea) {
      bestArea = area;
      const lengthS = maxS - minS, widthT = maxT - minT, midS = (minS + maxS) / 2, midT = (minT + maxT) / 2;
      const cx = a[0] + midS * ux - midT * uy, cy = a[1] + midS * uy + midT * ux;
      best = lengthS >= widthT ? { cx, cy, ux, uy, length: lengthS, width: widthT } : { cx, cy, ux: -uy, uy: ux, length: widthT, width: lengthS };
    }
  }
  return best ?? { cx: points[0][0], cy: points[0][1], ux: 1, uy: 0, length: 1, width: 1 };
}

function orientedRectPolygon(points: XY[]): XY[] {
  const r = orientedRect(points), vx = -r.uy, vy = r.ux, hl = r.length / 2, hw = r.width / 2;
  const at = (s: number, t: number): XY => [r.cx + s * r.ux + t * vx, r.cy + s * r.uy + t * vy];
  return [at(-hl, -hw), at(hl, -hw), at(hl, hw), at(-hl, hw)];
}

/** Connectors that share one space (a lift and a stair in the same corridor, or several stairs) each get their own slot along
 *  the space, and a space that is not itself a stair or lift gets compact fixtures instead of a fixture filling the whole room. */
export function inside(poly: XY[], x: number, y: number): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

/** Shrink a rectangle about its centre until its corners and edge midpoints lie inside the polygon, so fixtures never poke through walls. */
export function fitInside(poly: XY[], rect: XY[]): XY[] {
  const cx = rect.reduce((a, p) => a + p[0], 0) / rect.length, cy = rect.reduce((a, p) => a + p[1], 0) / rect.length;
  const xs = poly.map(p => p[0]), ys = poly.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  // candidate centres: the rectangle's own centre first, then a grid over the polygon (an L-shape's bounding-box centre can be outside it)
  const centres: XY[] = [[cx, cy]];
  for (let a = 0; a <= 8; a++) for (let b = 0; b <= 8; b++) centres.push([x0 + ((x1 - x0) * a) / 8, y0 + ((y1 - y0) * b) / 8]);
  let best: XY[] | null = null, bestK = 0;
  for (const [mx, my] of centres) {
    if (!inside(poly, mx, my)) continue;
    for (let k = 1; k >= 0.1 && k > bestK + 1e-9; k -= 0.05) {
      const pts = rect.map(p => [mx + (p[0] - cx) * k, my + (p[1] - cy) * k] as XY);
      const probes = pts.flatMap((p, n) => [p, [(p[0] + pts[(n + 1) % 4][0]) / 2, (p[1] + pts[(n + 1) % 4][1]) / 2] as XY]);
      if (probes.every(p => inside(poly, p[0], p[1]))) { best = pts; bestK = k; break; }
    }
    if (bestK >= 1 - 1e-9) break;
  }
  return best ?? rect;
}

export function slotSpace(space: Space, index: number, count: number, kind: "stairs" | "lift", core: boolean): Space {
  const fitted = (s: Space): Space => ({ ...s, polygon: fitInside(space.polygon, s.polygon.length === 4 ? s.polygon : orientedRectPolygon(s.polygon)) });
  if (count <= 1 && core) return fitted(space);
  const r = orientedRect(space.polygon), slot = r.length / count;
  const length = Math.min(slot, kind === "stairs" ? 3.8 : 2.2), width = Math.min(r.width, kind === "stairs" ? 2.4 : 2.0);
  const s0 = -r.length / 2 + (index + 0.5) * slot, vx = -r.uy, vy = r.ux;
  const at = (s: number, t: number): XY => [r.cx + (s0 + s) * r.ux + t * vx, r.cy + (s0 + s) * r.uy + t * vy];
  return fitted({ ...space, polygon: [at(-length / 2, -width / 2), at(length / 2, -width / 2), at(length / 2, width / 2), at(-length / 2, width / 2)] });
}

const RISER = 0.175, MIN_TREAD = 0.24, WALL = 0.18, GAP = 0.16, TREAD_THICK = 0.05;

/** Dog-leg stair (or a straight flight in a long thin space) rising `rise` metres from `base`. */
export function stairBoxes(space: Space, base: number, rise: number, lit: boolean, alignment: XY | OrientedRect | null = null): Box[] {
  let r = alignment&&!Array.isArray(alignment)?alignment:orientedRect(space.polygon);
  // The flat landing sits at the door end, so nobody steps from a doorway straight onto a riser.
  if (Array.isArray(alignment) && ((alignment[0] - r.cx) * r.ux + (alignment[1] - r.cy) * r.uy) < 0) r = { ...r, ux: -r.ux, uy: -r.uy };
  const L = Math.max(0.8, r.length - 2 * WALL), W = Math.max(0.7, r.width - 2 * WALL);
  const yaw = Math.atan2(r.uy, r.ux), vx = -r.uy, vy = r.ux; // v: across the flight, to the left of u
  const at = (s: number, t: number) => ({ x: r.cx + s * r.ux + t * vx, z: -(r.cy + s * r.uy + t * vy) });
  const boxes: Box[] = [];
  const tread = lit ? "#ffe39a" : "#dde2e0", riserColor = lit ? "#e0b55a" : "#aab4b2", under = "#8e9a99", rail = "#f2f5f5";
  const straight = W < 2.4 && L >= 5.5; // a long narrow shaft takes one straight flight
  const flights = straight ? 1 : 2;
  const gap = flights === 2 ? GAP : 0, fw = (W - gap) / flights;
  const landing = flights === 2 ? Math.min(fw + 0.25, 1.5, L * 0.35) : 0;
  const run = L - landing;
  const perFlight = rise / flights, n = Math.max(2, Math.min(Math.round(perFlight / RISER), Math.floor(run / MIN_TREAD)));
  const rs = perFlight / n, ts = run / n;
  const phi = Math.atan2(perFlight, run);
  for (let f = 0; f < flights; f++) {
    const t = flights === 1 ? 0 : (f === 0 ? -1 : 1) * (fw + gap) / 2; // across offset of this flight's centre line
    const dir = f === 0 ? 1 : -1; // flight 1 climbs +u, flight 2 comes back along -u
    const startS = f === 0 ? -L / 2 : -L / 2 + run; // where this flight begins at its low end
    const lowY = base + f * perFlight;
    for (let k = 0; k < n; k++) {
      const s = startS + dir * (k + 0.5) * ts, top = lowY + (k + 1) * rs;
      const p = at(s, t);
      boxes.push({ x: p.x, y: top - TREAD_THICK / 2, z: p.z, sx: ts + 0.02, sy: TREAD_THICK, sz: fw, yaw, tilt: 0, color: tread });
      const q = at(s - dir * ts / 2, t); // riser at the back edge of the tread below
      boxes.push({ x: q.x, y: top - rs / 2, z: q.z, sx: 0.025, sy: rs, sz: fw, yaw, tilt: 0, color: riserColor });
    }
    // sloped soffit under the flight
    const centre = at(startS + dir * run / 2, t);
    const slope = Math.hypot(run, perFlight);
    boxes.push({ x: centre.x, y: lowY + perFlight / 2 - 0.08, z: centre.z, sx: slope, sy: 0.14, sz: fw, yaw: dir === 1 ? yaw : yaw + Math.PI, tilt: phi, color: under });
    // handrail along the open (gap) side and the outer wall side
    for (const side of flights === 2 ? [(f === 0 ? 1 : -1) * (fw / 2 - 0.04)] : [-fw / 2 + 0.04, fw / 2 - 0.04]) {
      const c = at(startS + dir * run / 2, t + side);
      boxes.push({ x: c.x, y: lowY + perFlight / 2 + 0.92, z: c.z, sx: slope, sy: 0.04, sz: 0.04, yaw: dir === 1 ? yaw : yaw + Math.PI, tilt: phi, color: rail });
      for (const frac of [0.1, 0.5, 0.9]) {
        const pp = at(startS + dir * run * frac, t + side);
        boxes.push({ x: pp.x, y: lowY + perFlight * frac + 0.46, z: pp.z, sx: 0.035, sy: 0.92, sz: 0.035, yaw, tilt: 0, color: rail });
      }
    }
  }
  if (flights === 2) {
    const c = at(-L / 2 + run + landing / 2, 0);
    boxes.push({ x: c.x, y: base + perFlight - 0.07, z: c.z, sx: landing, sy: 0.14, sz: W, yaw, tilt: 0, color: "#cfd6d4" });
  }
  return boxes;
}

export interface WalkPoint { x: number; y: number; h: number }

/** The line a person walks up (or down) a stair, from the same layout as stairBoxes: flight, landing, flight. Heights are tread tops above `base`. */
export function stairWalkLine(space: Space, base: number, rise: number, alignment: XY | OrientedRect | null = null): WalkPoint[] {
  let r = alignment && !Array.isArray(alignment) ? alignment : orientedRect(space.polygon);
  if (Array.isArray(alignment) && ((alignment[0] - r.cx) * r.ux + (alignment[1] - r.cy) * r.uy) < 0) r = { ...r, ux: -r.ux, uy: -r.uy };
  const L = Math.max(0.8, r.length - 2 * WALL), W = Math.max(0.7, r.width - 2 * WALL);
  const vx = -r.uy, vy = r.ux;
  const at = (s0: number, t: number, h: number): WalkPoint => ({ x: r.cx + s0 * r.ux + t * vx, y: r.cy + s0 * r.uy + t * vy, h });
  const straight = W < 2.4 && L >= 5.5, flights = straight ? 1 : 2;
  const gap = flights === 2 ? GAP : 0, fw = (W - gap) / flights;
  const landing = flights === 2 ? Math.min(fw + 0.25, 1.5, L * 0.35) : 0;
  const run = L - landing, perFlight = rise / flights;
  const n = Math.max(2, Math.min(Math.round(perFlight / RISER), Math.floor(run / MIN_TREAD)));
  const rs = perFlight / n, ts = run / n;
  const out: WalkPoint[] = [at(-L / 2 - 0.4, flights === 1 ? 0 : -(fw + gap) / 2, base)];
  for (let f = 0; f < flights; f++) {
    const t = flights === 1 ? 0 : (f === 0 ? -1 : 1) * (fw + gap) / 2, dir = f === 0 ? 1 : -1;
    const startS = f === 0 ? -L / 2 : -L / 2 + run, lowY = base + f * perFlight;
    for (let k = 0; k <= n; k++) out.push(at(startS + dir * k * ts, t, lowY + Math.min(k + 0.5, n) * rs));
    if (f === 0 && flights === 2) out.push(at(-L / 2 + run + landing / 2, 0, base + perFlight));
  }
  const last = out[out.length - 1], prev = out[out.length - 2];
  const d = Math.hypot(last.x - prev.x, last.y - prev.y) || 1;
  out.push({ x: last.x + ((last.x - prev.x) / d) * 0.5, y: last.y + ((last.y - prev.y) / d) * 0.5, h: base + rise });
  return out;
}

/** The walk for one connector between two floors (every storey in between), ascending order; null if the connector is not a drawn stair. */
export function stairWalkFor(geometry: Geometry, fromFloor: string, toFloor: string, nodeA: string, nodeB: string): WalkPoint[] | null {
  const c = (geometry.connectors as Connector[]).find(k => k.kind === "stairs" && k.space_ids.includes(nodeA) && k.space_ids.includes(nodeB));
  if (!c) return null;
  const floors = new Map(geometry.floors.map(f => [f.id, f]));
  const spaces = new Map(geometry.spaces.map(sp => [sp.id, sp]));
  const stops = c.floor_ids.map((fid, i) => ({ floor: floors.get(fid)!, space: spaces.get(c.space_ids[i]) })).filter(x => x.floor && x.space).sort((a, b) => a.floor.level - b.floor.level);
  const lo = Math.min(floors.get(fromFloor)?.level ?? 0, floors.get(toFloor)?.level ?? 0), hi = Math.max(floors.get(fromFloor)?.level ?? 0, floors.get(toFloor)?.level ?? 0);
  const line: WalkPoint[] = [];
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (a.floor.level < lo || b.floor.level > hi) continue;
    const shaft = geometry.scene?.stair_shafts?.find(sh => sh.connector_id === c.id && sh.from_floor === a.floor.id && sh.to_floor === b.floor.id);
    if (!shaft?.footprint) return null;
    const lower = geometry.openings.filter(o => o.floor_id === a.floor.id && o.space_ids.includes(a.space!.id)).map(o => o.position);
    const upper = geometry.openings.filter(o => o.floor_id === b.floor.id && o.space_ids.includes(b.space!.id)).map(o => o.position);
    const frame = alignStairFrame(orientedRect(shaft.footprint), lower, upper);
    line.push(...stairWalkLine(a.space!, a.floor.elevation_m + 0.02, b.floor.elevation_m - a.floor.elevation_m, frame));
  }
  return line.length > 1 ? line : null;
}

function Instances({ boxes }: { boxes: Box[] }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const o = new THREE.Object3D(), colour = new THREE.Color(), up = new THREE.Vector3(0, 1, 0), forward = new THREE.Vector3(0, 0, 1);
    boxes.forEach((b, i) => {
      o.position.set(b.x, b.y, b.z);
      o.quaternion.setFromAxisAngle(up, b.yaw).multiply(new THREE.Quaternion().setFromAxisAngle(forward, b.tilt));
      o.scale.set(b.sx, b.sy, b.sz);
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
      mesh.setColorAt(i, colour.set(b.color));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [boxes]);
  return <instancedMesh ref={ref} args={[undefined, undefined, Math.max(1, boxes.length)]} frustumCulled={false} castShadow receiveShadow><boxGeometry /><meshStandardMaterial roughness={0.75} metalness={0.1} /></instancedMesh>;
}

export interface Connectors3DProps {
  geometry: Geometry;
  /** Displayed elevation of each floor (includes the exploded gap). */
  elevations: Record<string, number>;
  visibleFloors: Set<string>;
  activeFloor: string;
  /** Connector ids the current route uses; they are tinted. */
  used: Set<string>;
}

/** Stairwells and lift shafts for every visible floor. Stairs climb to the displayed elevation of the next stop. */
export function Connectors3D({ geometry, elevations, visibleFloors, activeFloor, used }: Connectors3DProps) {
  const elevation = (id: string) => elevations[id] ?? 0;
  const spaceById = useMemo(() => new Map(geometry.spaces.map(s => [s.id, s])), [geometry]);
  const levelOf = useMemo(() => new Map(geometry.floors.map(f => [f.id, f])), [geometry]);
  const boxes = useMemo(() => {
    const out: Box[] = [];
    const sharing = new Map<string, string[]>();
    for (const c of geometry.connectors as Connector[]) c.floor_ids.forEach((fid, i) => {
      const key = `${fid}|${c.space_ids[i]}`;
      sharing.set(key, [...(sharing.get(key) ?? []), c.id]);
    });
    for (const c of geometry.connectors as Connector[]) {
      const stops = c.floor_ids.map((fid, i) => ({ floor: levelOf.get(fid)!, space: spaceById.get(c.space_ids[i]) })).filter(s => s.floor && s.space)
        .sort((a, b) => a.floor.level - b.floor.level);
      const lit = used.has(c.id);
      stops.forEach((stop, i) => {
        if (!visibleFloors.has(stop.floor.id) || stop.space!.polygon.length < 3) return;
        const base = elevation(stop.floor.id) + 0.02;
        const group = sharing.get(`${stop.floor.id}|${stop.space!.id}`) ?? [c.id];
        const core = /stair|lift/.test(stop.space!.type);
        const space = slotSpace(stop.space!, group.indexOf(c.id), group.length, c.kind === "stairs" ? "stairs" : "lift", core);
        if (c.kind === "stairs") {
          const next = stops[i + 1];
          if (!next) return;
          const realRise = next.floor.elevation_m - stop.floor.elevation_m;
          const shownRise = visibleFloors.has(next.floor.id) ? elevation(next.floor.id) - elevation(stop.floor.id) : realRise;
          const modelSpace = space;
          const lower = geometry.openings.filter(o=>o.floor_id===stop.floor.id&&o.space_ids.includes(stop.space!.id)).map(o=>o.position);
          const upper = geometry.openings.filter(o=>o.floor_id===next.floor.id&&o.space_ids.includes(next.space!.id)).map(o=>o.position);
          const shaft=geometry.scene?.stair_shafts?.find(s=>s.connector_id===c.id&&s.from_floor===stop.floor.id&&s.to_floor===next.floor.id);
          if(!shaft?.footprint)return; // Never stretch a bounding rectangle through neighbouring rooms.
          const frame = alignStairFrame(orientedRect(shaft.footprint),lower,upper);
          out.push(...stairBoxes(modelSpace,base,shownRise,lit,frame));
        } else {
          // lifts are drawn by LiftShafts (animated car, doors that open only where the car stands)
        }
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, spaceById, levelOf, elevations, visibleFloors, activeFloor, used]);
  return boxes.length ? <Instances boxes={boxes} /> : null;
}

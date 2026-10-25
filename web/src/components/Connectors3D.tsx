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

const RISER = 0.175, MIN_TREAD = 0.24, WALL = 0.18, GAP = 0.16, TREAD_THICK = 0.05;

/** Dog-leg stair (or a straight flight in a long thin space) rising `rise` metres from `base`. */
export function stairBoxes(space: Space, base: number, rise: number, lit: boolean, alignment: XY | OrientedRect | null = null): Box[] {
  const r = alignment&&!Array.isArray(alignment)?alignment:orientedRect(space.polygon), L = Math.max(0.8, r.length - 2 * WALL), W = Math.max(0.7, r.width - 2 * WALL);
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

/** A lift car in its shaft: car body, door leaves facing the nearest opening, and a lit floor indicator. */
export function liftBoxes(space: Space, base: number, doorSide: XY | null, carHere: boolean, lit: boolean): Box[] {
  const r = orientedRect(space.polygon), yaw = Math.atan2(r.uy, r.ux), vx = -r.uy, vy = r.ux;
  const L = Math.max(0.9, r.length - 0.5), W = Math.max(0.9, r.width - 0.5);
  const boxes: Box[] = [];
  const at = (s: number, t: number) => ({ x: r.cx + s * r.ux + t * vx, z: -(r.cy + s * r.uy + t * vy) });
  // landing door on every stop: two steel leaves in the wall nearest the supplied opening
  let side = 1;
  if (doorSide) side = ((doorSide[0] - r.cx) * r.ux + (doorSide[1] - r.cy) * r.uy) >= 0 ? 1 : -1;
  const frontS = side * (r.length / 2 - 0.1);
  for (const lat of [-0.28, 0.28]) {
    const p = at(frontS, lat * Math.min(W, 1.6));
    boxes.push({ x: p.x, y: base + 1.05, z: p.z, sx: 0.05, sy: 2.1, sz: Math.min(W, 1.6) * 0.28, yaw, tilt: 0, color: lit ? "#ffe39a" : "#b9c6ca" });
  }
  const sign = at(frontS, 0);
  boxes.push({ x: sign.x, y: base + 2.3, z: sign.z, sx: 0.06, sy: 0.14, sz: 0.5, yaw, tilt: 0, color: "#74e0b2", emissive: true });
  if (carHere) {
    const cl = Math.min(L, 2.1), cw = Math.min(W, 1.7);
    const c = at(side * (L / 2 - cl / 2 - 0.2) , 0);
    boxes.push({ x: c.x, y: base + 1.2, z: c.z, sx: cl, sy: 2.3, sz: cw, yaw, tilt: 0, color: "#9fb2b8" });
    const inner = at(side * (L / 2 - 0.3), 0);
    boxes.push({ x: inner.x, y: base + 1.05, z: inner.z, sx: 0.04, sy: 2.0, sz: cw * 0.8, yaw, tilt: 0, color: "#2a3b42" });
  }
  return boxes;
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
  return <instancedMesh ref={ref} args={[undefined, undefined, Math.max(1, boxes.length)]} frustumCulled={false}><boxGeometry /><meshStandardMaterial roughness={0.75} metalness={0.1} /></instancedMesh>;
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
    for (const c of geometry.connectors as Connector[]) {
      const stops = c.floor_ids.map((fid, i) => ({ floor: levelOf.get(fid)!, space: spaceById.get(c.space_ids[i]) })).filter(s => s.floor && s.space)
        .sort((a, b) => a.floor.level - b.floor.level);
      const lit = used.has(c.id);
      stops.forEach((stop, i) => {
        if (!visibleFloors.has(stop.floor.id) || stop.space!.polygon.length < 3) return;
        const base = elevation(stop.floor.id) + 0.02;
        if (c.kind === "stairs") {
          const next = stops[i + 1];
          if (!next) return;
          const realRise = next.floor.elevation_m - stop.floor.elevation_m;
          const shownRise = visibleFloors.has(next.floor.id) ? elevation(next.floor.id) - elevation(stop.floor.id) : realRise;
          const modelSpace = stop.space!;
          const lower = geometry.openings.filter(o=>o.floor_id===stop.floor.id&&o.space_ids.includes(stop.space!.id)).map(o=>o.position);
          const upper = geometry.openings.filter(o=>o.floor_id===next.floor.id&&o.space_ids.includes(next.space!.id)).map(o=>o.position);
          const shaft=geometry.scene?.stair_shafts?.find(s=>s.connector_id===c.id&&s.from_floor===stop.floor.id&&s.to_floor===next.floor.id);
          if(!shaft?.footprint)return; // Never stretch a bounding rectangle through neighbouring rooms.
          const frame = alignStairFrame(orientedRect(shaft.footprint),lower,upper);
          out.push(...stairBoxes(modelSpace,base,shownRise,lit,frame));
        } else {
          const opening = geometry.openings.find(o => o.floor_id === stop.floor.id && o.space_ids.includes(stop.space!.id));
          out.push(...liftBoxes(stop.space!, base, opening?.position ?? null, stop.floor.id === activeFloor, lit));
        }
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, spaceById, levelOf, elevations, visibleFloors, activeFloor, used]);
  return boxes.length ? <Instances boxes={boxes} /> : null;
}

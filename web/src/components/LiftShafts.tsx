import { useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Connector, Geometry, Space, XY } from "../lib/types";
import { orientedRect, slotSpace } from "./Connectors3D";

/** Lifts: one car per lift that travels to the floor being looked at, steel landing doors on every stop that are shut unless the
 *  car is there, and doors that slide open when it arrives. Everything is generated from the lift spaces; no car data is supplied. */

/** While Guide me rides a lift, the camera drives the car so both rise together. Set by RouteCamera, read here every frame. */
export const rideState: { lift: null | { nodes: string[]; y: number } } = { lift: null };

const CAR_SPEED_M_S = 3.2, OPEN_BAND_M = 0.25;
const smooth = (t: number) => t * t * (3 - 2 * t);

interface Stop { key: string; y: number; space: Space; front: 1 | -1; lit: boolean }

function useLifts(geometry: Geometry, elevations: Record<string, number>, visibleFloors: Set<string>, used: Set<string>) {
  return useMemo(() => {
    const spaces = new Map(geometry.spaces.map(s => [s.id, s]));
    const floors = new Map(geometry.floors.map(f => [f.id, f]));
    const sharing = new Map<string, string[]>();
    for (const c of geometry.connectors as Connector[]) c.floor_ids.forEach((fid, i) => {
      const key = `${fid}|${c.space_ids[i]}`;
      sharing.set(key, [...(sharing.get(key) ?? []), c.id]);
    });
    return (geometry.connectors as Connector[]).filter(c => c.kind === "lift").map(c => {
      const stops: Stop[] = [];
      c.floor_ids.forEach((fid, i) => {
        const floor = floors.get(fid), base = spaces.get(c.space_ids[i]);
        if (!floor || !base || base.polygon.length < 3) return;
        const group = sharing.get(`${fid}|${base.id}`) ?? [c.id];
        const space = slotSpace(base, group.indexOf(c.id), group.length, "lift", /stair|lift/.test(base.type));
        const r = orientedRect(space.polygon);
        const door = geometry.openings.find(o => o.floor_id === fid && o.space_ids.includes(base.id))?.position;
        const front: 1 | -1 = door && ((door[0] - r.cx) * r.ux + (door[1] - r.cy) * r.uy) < 0 ? -1 : 1;
        stops.push({ key: `${c.id}|${fid}`, y: (elevations[fid] ?? 0) + 0.02, space, front, lit: used.has(c.id) });
      });
      return { id: c.id, stops, floorIds: c.floor_ids };
    });
  }, [geometry, elevations, visibleFloors, used]);
}

function Landing({ stop, carY }: { stop: Stop; carY: { current: number } }) {
  const r = useMemo(() => orientedRect(stop.space.polygon), [stop.space]);
  const left = useRef<THREE.Mesh>(null), right = useRef<THREE.Mesh>(null);
  const yaw = Math.atan2(r.uy, r.ux), wDoor = Math.min(r.width, 1.6), leaf = wDoor * 0.27, frontS = stop.front * (r.length / 2 - 0.1);
  const { invalidate } = useThree();
  const open = useRef(0);
  useFrame((_, dt) => {
    const target = Math.abs(carY.current - stop.y) < OPEN_BAND_M ? 1 : 0;
    if (Math.abs(open.current - target) > 0.002) {
      open.current += Math.sign(target - open.current) * Math.min(Math.abs(target - open.current), dt * 1.8);
      invalidate();
    }
    const slide = smooth(open.current) * leaf * 0.92;
    if (left.current) left.current.position.z = -(leaf / 2 + slide);
    if (right.current) right.current.position.z = leaf / 2 + slide;
  });
  const colour = stop.lit ? "#ffe39a" : "#b9c6ca";
  return (
    <group position={[r.cx + frontS * r.ux, stop.y, -(r.cy + frontS * r.uy)]} rotation={[0, yaw, 0]}>
      <mesh ref={left} position={[0, 1.05, -leaf / 2]} castShadow><boxGeometry args={[0.05, 2.1, leaf]} /><meshStandardMaterial color={colour} metalness={0.5} roughness={0.35} /></mesh>
      <mesh ref={right} position={[0, 1.05, leaf / 2]} castShadow><boxGeometry args={[0.05, 2.1, leaf]} /><meshStandardMaterial color={colour} metalness={0.5} roughness={0.35} /></mesh>
      <mesh position={[0, 2.3, 0]}><boxGeometry args={[0.06, 0.14, 0.5]} /><meshStandardMaterial color="#74e0b2" emissive="#2f9d72" emissiveIntensity={0.8} /></mesh>
    </group>
  );
}

function LiftCar({ stops, y, target }: { stops: Stop[]; y: { current: number }; target: number | null }) {
  const group = useRef<THREE.Group>(null);
  const { invalidate } = useThree();
  const stop = stops[0];
  const r = useMemo(() => (stop ? orientedRect(stop.space.polygon) : null), [stop]);
  useFrame((_, dt) => {
    const riding = rideState.lift && stops.some(st => rideState.lift!.nodes.includes(st.space.id));
    if (riding) y.current = rideState.lift!.y;
    else if (target != null) {
      const d = target - y.current;
      if (Math.abs(d) > 0.005) { y.current += Math.sign(d) * Math.min(Math.abs(d), CAR_SPEED_M_S * dt); invalidate(); }
    }
    if (group.current) group.current.position.y = y.current;
  });
  if (!stop || !r) return null;
  const cl = Math.min(Math.max(0.9, r.length - 0.5), 2.0), cw = Math.min(Math.max(0.9, r.width - 0.5), 1.6);
  const yaw = Math.atan2(r.uy, r.ux), s = stop.front, off = s * (r.length / 2 - cl / 2 - 0.2);
  return (
    <group ref={group} position={[r.cx + off * r.ux, y.current, -(r.cy + off * r.uy)]} rotation={[0, yaw, 0]}>
      <mesh position={[0, 1.15, 0]} castShadow><boxGeometry args={[cl, 2.25, cw]} /><meshStandardMaterial color="#c7d6db" emissive="#5d7f8c" emissiveIntensity={0.35} metalness={0.3} roughness={0.4} /></mesh>
    </group>
  );
}

export function LiftShafts({ geometry, elevations, visibleFloors, activeFloor, used }: { geometry: Geometry; elevations: Record<string, number>; visibleFloors: Set<string>; activeFloor: string; used: Set<string> }) {
  const lifts = useLifts(geometry, elevations, visibleFloors, used);
  const carYs = useRef(new Map<string, { current: number }>());
  const { gl } = useThree();
  useFrame(() => { gl.domElement.dataset.liftCars = JSON.stringify(Object.fromEntries([...carYs.current].map(([id, v]) => [id, Math.round(v.current * 100) / 100]))); });
  return (
    <>
      {lifts.map(l => {
        if (!carYs.current.has(l.id)) carYs.current.set(l.id, { current: l.stops[0]?.y ?? 0 });
        const carY = carYs.current.get(l.id)!;
        const target = l.floorIds.includes(activeFloor) ? (elevations[activeFloor] ?? 0) + 0.02 : null;
        return (
          <group key={l.id}>
            {l.stops.filter((_, i) => visibleFloors.has(l.floorIds[i])).map(s => <Landing key={s.key} stop={s} carY={carY} />)}
            <LiftCar stops={l.stops} y={carY} target={target} />
          </group>
        );
      })}
    </>
  );
}

export type { XY };

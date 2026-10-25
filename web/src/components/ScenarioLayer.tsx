import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { centroid } from "../lib/geometry";
import type { Geometry, XY } from "../lib/types";
import { clock, type ScenarioScene } from "../navigator/scenarios/clock";

/** Scenario visual layer inside the 3D canvas: people dots (one InstancedMesh), door flow arrows, queue and exit columns, fire room and an
 *  illustrative smoke column. It reads the shared scenario clock and only asks for a frame when the time changes; floors are never re-merged. */
const CAP = typeof matchMedia !== "undefined" && matchMedia("(max-width:1023px)").matches ? 150 : 300;
const DOT = new THREE.Color("#ffe08a"), DOT_MOVING = new THREE.Color("#ffffff");
const tmp = new THREE.Object3D();

const jitter = (i: number): [number, number] => { const r = Math.min(2.4, 0.38 * Math.sqrt(i + 0.5)), a = i * 2.399963; return [Math.cos(a) * r, Math.sin(a) * r]; };

export function ScenarioLayer({ geometry, elevations, visibleFloors }: { geometry: Geometry; elevations: Record<string, number>; visibleFloors: Set<string> }) {
  const [scene, setScene] = useState<ScenarioScene | null>(() => clock.get().scene);
  const invalidate = useThree(s => s.invalidate), gl = useThree(s => s.gl);
  const dirty = useRef(true);
  const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => clock.subscribe(() => {
    const st = clock.get();
    setScene(old => (old === st.scene ? old : st.scene));
    if (reduced && st.playing) return;  // reduced motion: static frames, redrawn on pause or seek
    dirty.current = true; invalidate();
  }), [invalidate, reduced]);

  const spaces = useMemo(() => new Map(geometry.spaces.map(s => [s.id, s])), [geometry]);
  const openings = useMemo(() => new Map(geometry.openings.map(o => [o.id, o])), [geometry]);
  const anchor = (id: string): [number, number, number] | null => {
    const s = spaces.get(id); if (!s) return null;
    const p: XY = s.anchor ?? centroid(s.polygon);
    return [p[0], (elevations[s.floor_id] ?? 0) + 0.35, -p[1]];
  };
  const shown = (id: string) => { const s = spaces.get(id); return !!s && visibleFloors.has(s.floor_id); };

  /** Static parts of a flow result: scale (people per dot), initial headcount per room, door flow rates, exits. */
  const plan = useMemo(() => {
    if (scene?.kind !== "flow") return null;
    const initial: Record<string, number> = {};
    for (const m of scene.schedule) { initial[m.from_space] = (initial[m.from_space] ?? 0) + m.persons; initial[m.to_space] = (initial[m.to_space] ?? 0) - m.persons; }
    for (const [sp, n] of Object.entries(scene.stranded)) initial[sp] = (initial[sp] ?? 0) + n;
    const people = Object.entries(initial).filter(([k]) => k !== "outside").reduce((a, [, v]) => a + Math.max(0, v), 0);
    const doors = new Map<string, { persons: number; from: number; to: number; dir: [number, number]; at: [number, number, number] }>();
    for (const m of scene.schedule) {
      const o = openings.get(m.element); if (!o || !visibleFloors.has(o.floor_id)) continue;
      const a = anchor(m.from_space), d = doors.get(o.id) ?? { persons: 0, from: Infinity, to: 0, dir: [0, 0] as [number, number], at: [o.position[0], (elevations[o.floor_id] ?? 0) + 0.2, -o.position[1]] as [number, number, number] };
      d.persons += m.persons; d.from = Math.min(d.from, m.depart_s); d.to = Math.max(d.to, m.arrive_s);
      if (a) { d.dir[0] += (d.at[0] - a[0]) * m.persons; d.dir[1] += (d.at[2] - a[2]) * m.persons; }
      doors.set(o.id, d);
    }
    return { initial, scale: Math.max(1, people / CAP), doors: [...doors.entries()] };
  }, [scene, openings, visibleFloors, elevations]); // eslint-disable-line react-hooks/exhaustive-deps

  const dots = useRef<THREE.InstancedMesh>(null);
  const smoke = useRef<THREE.Mesh>(null);
  const exitBars = useRef<Map<string, THREE.Mesh>>(new Map());
  const [count, setCount] = useState(0);
  useEffect(() => { const host = (gl.domElement.closest("[data-testid=building-scene]") as HTMLElement | null) ?? gl.domElement; host.dataset.scenarioDots = String(count); host.dataset.scenarioKind = scene?.kind ?? ""; }, [count, scene, gl]);
  useEffect(() => () => { const host = (gl.domElement.closest("[data-testid=building-scene]") as HTMLElement | null) ?? gl.domElement; delete host.dataset.scenarioDots; delete host.dataset.scenarioKind; }, [gl]);
  useEffect(() => { dirty.current = true; invalidate(); }, [scene, visibleFloors, invalidate]);

  useFrame(() => {
    if (!dirty.current || !dots.current || !scene) return;
    dirty.current = false;
    const { t } = clock.get(), mesh = dots.current;
    let n = 0;
    const put = (x: number, y: number, z: number, moving: boolean) => {
      if (n >= CAP) return;
      tmp.position.set(x, y, z); tmp.updateMatrix(); mesh.setMatrixAt(n, tmp.matrix); mesh.setColorAt(n, moving ? DOT_MOVING : DOT); n++;
    };
    if (scene.kind === "flow" && plan) {
      const left: Record<string, number> = { ...plan.initial };
      for (const m of scene.schedule) { if (m.depart_s <= t) left[m.from_space] -= m.persons; if (m.arrive_s <= t) left[m.to_space] += m.persons; }
      // People walking: room anchor -> door -> next room anchor.
      for (const m of scene.schedule) {
        if (m.depart_s > t || m.arrive_s <= t) continue;
        const a = anchor(m.from_space), b = m.to_space === "outside" ? null : anchor(m.to_space), o = openings.get(m.element);
        if (!a || !shown(m.from_space)) continue;
        const door: [number, number, number] | null = o ? [o.position[0], (elevations[o.floor_id] ?? 0) + 0.35, -o.position[1]] : null;
        const end = b ?? door ?? a, k = Math.max(1, Math.round(m.persons / plan.scale));
        for (let i = 0; i < k; i++) {
          const f = Math.min(1, Math.max(0, (t - m.depart_s) / Math.max(0.1, m.arrive_s - m.depart_s) - i * 0.04));
          const [jx, jz] = jitter(i).map(v => v * 0.25);
          let p: [number, number, number];
          if (door) { const h = f < 0.5 ? f * 2 : (f - 0.5) * 2, s0 = f < 0.5 ? a : door, s1 = f < 0.5 ? door : end; p = [s0[0] + (s1[0] - s0[0]) * h, s0[1] + (s1[1] - s0[1]) * h, s0[2] + (s1[2] - s0[2]) * h]; }
          else p = [a[0] + (end[0] - a[0]) * f, a[1] + (end[1] - a[1]) * f, a[2] + (end[2] - a[2]) * f];
          put(p[0] + jx, p[1], p[2] + jz, true);
        }
      }
      // People still in rooms: a small cluster around the room anchor.
      for (const [id, v] of Object.entries(left)) {
        if (id === "outside" || v < 0.5 || !shown(id)) continue;
        const a = anchor(id)!, k = Math.max(1, Math.round(v / plan.scale));
        for (let i = 0; i < k; i++) { const [jx, jz] = jitter(i); put(a[0] + jx, a[1], a[2] + jz, false); }
      }
      const T = Math.max(1, clock.get().T);
      for (const [id, mesh] of exitBars.current) {
        const out = scene.schedule.reduce((acc, m) => acc + (m.element === id && m.to_space === "outside" && m.arrive_s <= t ? m.persons : 0), 0);
        const h = Math.max(0.05, Math.min(4, out / Math.max(1, scene.byExit[id] ?? 1) * 3)); mesh.scale.set(1, h, 1); mesh.position.y = (mesh.userData.base as number) + h / 2;
      }
      if (smoke.current) { const f = Math.min(1, t / T); smoke.current.scale.set(1 + f * 0.6, 0.2 + f * 3.2, 1 + f * 0.6); smoke.current.position.y = (smoke.current.userData.base as number) + (0.2 + f * 3.2) / 2; (smoke.current.material as THREE.MeshBasicMaterial).opacity = 0.18 + f * 0.3; }
    } else if (scene.kind === "rooms") {
      const frames = Object.values(scene.rooms)[0]?.length ?? 1, idx = Math.min(frames - 1, Math.round(t / scene.step_s));
      const total = Object.values(scene.rooms).reduce((a, r) => a + (r[0] ?? 0), 0), scale = Math.max(1, total / CAP);
      for (const [id, series] of Object.entries(scene.rooms)) {
        const v = series[idx] ?? 0; if (v < 0.5 || !shown(id)) continue;
        const a = anchor(id); if (!a) continue;
        const k = Math.max(1, Math.round(v / scale));
        for (let i = 0; i < k; i++) { const [jx, jz] = jitter(i); put(a[0] + jx, a[1], a[2] + jz, false); }
      }
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    if (n !== count) setCount(n);
  });

  if (!scene) return null;
  const hazard = scene.kind === "flow" && scene.hazard ? spaces.get(scene.hazard) : undefined;
  const hazardAt = hazard && visibleFloors.has(hazard.floor_id) ? anchor(hazard.id) : null;
  const exits = scene.kind === "flow" ? Object.keys(scene.byExit).map(id => openings.get(id)).filter((o): o is NonNullable<typeof o> => !!o && visibleFloors.has(o.floor_id)) : [];
  return <group>
    <instancedMesh ref={dots} args={[undefined, undefined, CAP]} frustumCulled={false} renderOrder={120}>
      <sphereGeometry args={[0.16, 8, 6]} />
      <meshBasicMaterial toneMapped={false} depthTest={false} />
    </instancedMesh>
    {hazardAt && <group>
      <mesh position={[hazardAt[0], hazardAt[1] - 0.25, hazardAt[2]]} rotation={[-Math.PI / 2, 0, 0]} renderOrder={110}>
        <ringGeometry args={[1.2, 1.6, 32]} /><meshBasicMaterial color="#ff3b30" transparent opacity={0.85} depthTest={false} side={THREE.DoubleSide} />
      </mesh>
      {/* Smoke is illustrative only: neither engine models smoke or fire spread. */}
      <mesh ref={smoke} userData={{ base: hazardAt[1] - 0.3 }} position={[hazardAt[0], hazardAt[1], hazardAt[2]]} renderOrder={111}>
        <cylinderGeometry args={[1.1, 1.5, 1, 20, 1, true]} /><meshBasicMaterial color="#5a5f66" transparent opacity={0.2} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>}
    {plan?.doors.map(([id, d]) => {
      const rate = d.persons / Math.max(1, d.to - d.from), w = Math.min(1.4, 0.25 + rate * 0.6), len = Math.hypot(d.dir[0], d.dir[1]) || 1;
      const yaw = Math.atan2(d.dir[0] / len, d.dir[1] / len), slow = scene.kind === "flow" && scene.bottleneck.includes(id);
      return <mesh key={id} position={[d.at[0], d.at[1] + 0.3, d.at[2]]} rotation={[Math.PI / 2, 0, -yaw]} renderOrder={115}>
        <coneGeometry args={[w / 2, 0.9, 3]} /><meshBasicMaterial color={slow ? "#f2a33a" : "#7fd4a8"} transparent opacity={0.9} depthTest={false} />
      </mesh>;
    })}
    {exits.map(o => <mesh key={o.id} ref={m => { if (m) exitBars.current.set(o.id, m); else exitBars.current.delete(o.id); }} userData={{ base: (elevations[o.floor_id] ?? 0) + 0.1 }} position={[o.position[0], (elevations[o.floor_id] ?? 0) + 0.1, -o.position[1]]} renderOrder={116}>
      <boxGeometry args={[0.5, 1, 0.5]} /><meshBasicMaterial color="#34c77b" transparent opacity={0.9} depthTest={false} />
    </mesh>)}
    {scene.kind === "rooms" && scene.queues.filter(q => visibleFloors.has(q.floor_id)).map(q => {
      const h = Math.min(4, 0.3 + q.queue * 0.08);
      return <mesh key={q.id} position={[q.x, (elevations[q.floor_id] ?? 0) + h / 2 + 0.1, -q.y]} renderOrder={116}>
        <cylinderGeometry args={[0.35, 0.35, h, 12]} /><meshBasicMaterial color="#f2a33a" transparent opacity={0.85} depthTest={false} />
      </mesh>;
    })}
  </group>;
}

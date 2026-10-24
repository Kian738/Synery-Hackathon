import { Line, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import * as THREE from "three";
import { bounds, zoneOf } from "../lib/geometry";
import type { Asset, Geometry, Route, Space } from "../lib/types";

/** The building in metres, y up: x = plan x, z = -plan y, y = elevation. The same frame an AR session would
 *  use once the phone knows where it is (see docs/BACKLOG.md), so this scene is the base for AR. */

const ZONE_HEX: Record<string, string> = {
  circulation: "#f4f5f4", hall: "#efe9d6", office: "#e3e9ee", lab: "#dfeae5", service: "#ebe4ea", core: "#c9cfcc",
};
const WALL_HEIGHT = 2.6;

/** Height and colour of furniture by type: enough to read a room at a glance. */
function furnitureLook(a: Asset): { h: number; color: string } {
  const t = a.type;
  if (a.category === "machine") return { h: 1.8, color: "#56646b" };
  if (/server_rack|shelf|bookshelf|wardrobe|cabinet|locker|fridge/.test(t)) return { h: 1.9, color: "#8a959b" };
  if (/printer|oven|press|cnc|lathe|robot|conveyor|forklift|compressor/.test(t)) return { h: 1.6, color: "#56646b" };
  if (/table|desk|bench|counter|workbench/.test(t)) return { h: 0.75, color: "#b39a74" };
  if (/chair|stool|seat/.test(t)) return { h: 0.85, color: "#3f4a50" };
  if (/sofa|couch|armchair/.test(t)) return { h: 0.8, color: "#7d6f8f" };
  if (/bed/.test(t)) return { h: 0.55, color: "#c8bfb0" };
  if (/plant/.test(t)) return { h: 1.2, color: "#3d7a52" };
  if (/toilet|sink|shower|bath/.test(t)) return { h: 0.8, color: "#ffffff" };
  if (a.category === "equipment") return { h: 1.2, color: "#6b7a82" };
  return { h: 0.7, color: "#9aa4a9" };
}

function shapeOf(space: Space): THREE.Shape {
  const shape = new THREE.Shape();
  space.polygon.forEach(([x, y], i) => (i ? shape.lineTo(x, y) : shape.moveTo(x, y)));
  return shape;
}

function Room({ space, elevation, dim, highlighted }: { space: Space; elevation: number; dim: boolean; highlighted: boolean }) {
  const slab = useMemo(() => new THREE.ExtrudeGeometry(shapeOf(space), { depth: 0.12, bevelEnabled: false }), [space]);
  const walls = useMemo(() => {
    // Vertical quads along the outline: cheap walls that read well from any angle.
    const positions: number[] = [];
    const pts = space.polygon;
    for (let i = 0; i < pts.length; i++) {
      const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length];
      positions.push(x0, 0, -y0, x1, 0, -y1, x1, WALL_HEIGHT, -y1, x0, 0, -y0, x1, WALL_HEIGHT, -y1, x0, WALL_HEIGHT, -y0);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    g.computeVertexNormals();
    return g;
  }, [space]);
  const edges = useMemo(() => new THREE.EdgesGeometry(walls, 30), [walls]);
  const zone = zoneOf(space);
  return (
    <group position={[0, elevation, 0]}>
      <mesh geometry={slab} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.12, 0]} receiveShadow>
        <meshStandardMaterial color={highlighted ? "#f5c400" : ZONE_HEX[zone]} transparent opacity={dim ? 0.25 : 1} />
      </mesh>
      {!dim && (
        <>
          <mesh geometry={walls}>
            <meshStandardMaterial color="#e9ecea" side={THREE.DoubleSide} transparent opacity={0.28} depthWrite={false} />
          </mesh>
          <lineSegments geometry={edges}>
            <lineBasicMaterial color="#1c2226" transparent opacity={0.55} />
          </lineSegments>
        </>
      )}
    </group>
  );
}

function Furniture({ assets, elevation }: { assets: Asset[]; elevation: number }) {
  return (
    <group position={[0, elevation, 0]}>
      {assets.map((a) => {
        const look = furnitureLook(a);
        const w = a.footprint?.width_m ?? 0.5, d = a.footprint?.depth_m ?? 0.5;
        return (
          <mesh key={a.id} position={[a.position[0], look.h / 2, -a.position[1]]} rotation={[0, ((a.footprint?.rotation_deg ?? 0) * Math.PI) / 180, 0]} castShadow>
            <boxGeometry args={[w, look.h, d]} />
            <meshStandardMaterial color={look.color} />
          </mesh>
        );
      })}
    </group>
  );
}

export function Building3D({ geometry, floorId, route, highlights, showAll, exaggerate = 1.6 }: {
  geometry: Geometry; floorId: string; route?: Route | null; highlights?: Set<string>; showAll: boolean; exaggerate?: number;
}) {
  const floors = useMemo(() => [...geometry.floors].sort((a, b) => a.level - b.level), [geometry]);
  const elevation = (id: string) => (floors.find((f) => f.id === id)?.elevation_m ?? 0) * exaggerate;
  const active = floors.find((f) => f.id === floorId);
  const visible = showAll ? floors : floors.filter((f) => f.level <= (active?.level ?? 0));
  const box = useMemo(() => bounds(geometry.spaces.flatMap((s) => s.polygon)), [geometry]);
  const cx = (box.minX + box.maxX) / 2, cz = -(box.minY + box.maxY) / 2;
  const span = Math.max(box.maxX - box.minX, box.maxY - box.minY, 10);

  const routeLines = useMemo(() => {
    if (!route) return [] as THREE.Vector3[][];
    const runs: THREE.Vector3[][] = [];
    let run: THREE.Vector3[] = [];
    route.polyline.forEach((p: any) => {
      const v = new THREE.Vector3(p.x, elevation(p.floor_id) + 0.35, -p.y);
      if (p.gap && run.length) {
        // Floor change: a vertical connector line from the end of one floor to the start of the next.
        const last = run[run.length - 1];
        runs.push(run);
        if (Math.abs(last.y - v.y) > 0.5) runs.push([last, new THREE.Vector3(last.x, v.y, last.z)]);
        run = [];
      }
      run.push(v);
    });
    if (run.length) runs.push(run);
    return runs.filter((r) => r.length > 1);
  }, [route, floors, exaggerate]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Canvas shadows camera={{ position: [cx + span * 0.7, (active ? elevation(active.id) : 0) + span * 0.75, cz + span * 0.9], fov: 40, near: 0.1, far: span * 20 }}
      style={{ background: "#e6e8e6" }} aria-label="3D view of the building">
      <ambientLight intensity={0.75} />
      <directionalLight position={[cx + span, span * 1.5, cz + span * 0.5]} intensity={1.1} castShadow />
      {visible.map((f) => {
        const dim = f.id !== floorId && !showAll ? true : false;
        const spaces = geometry.spaces.filter((s) => s.floor_id === f.id);
        const items = geometry.assets.filter((a) => a.floor_id === f.id);
        return (
          <group key={f.id}>
            {spaces.map((s) => <Room key={s.id} space={s} elevation={elevation(f.id)} dim={dim} highlighted={!!highlights?.has(s.id)} />)}
            {!dim && <Furniture assets={items} elevation={elevation(f.id)} />}
          </group>
        );
      })}
      {routeLines.map((pts, i) => (
        <group key={i}>
          <Line points={pts} color="#1c2226" lineWidth={9} />
          <Line points={pts} color="#f5c400" lineWidth={5} />
        </group>
      ))}
      <OrbitControls target={[cx, active ? elevation(active.id) : 0, cz]} maxPolarAngle={Math.PI / 2.05} enableDamping makeDefault />
    </Canvas>
  );
}

export default Building3D;

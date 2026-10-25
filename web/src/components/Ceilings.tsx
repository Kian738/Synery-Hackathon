import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Geometry } from "../lib/types";

/** Roofs: the top cover of every indoor footprint that has no floor above it (the top storey and wings lower than their neighbours).
 *  Where a floor does lie above, that floor's plate is the ceiling. Drawn in Guide me; the overview stays open so rooms can be seen. */
export function Roofs({ geometry }: { geometry: Geometry }) {
  const meshes = useMemo(() => (geometry.scene?.roofs ?? []).map(r => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(r.vertices.flatMap(p => [p[0], r.elevation_m, -p[1]]), 3));
    g.computeVertexNormals();
    return { key: `${r.floor_id}-${r.elevation_m}`, g };
  }), [geometry]);
  useEffect(() => () => meshes.forEach(m => m.g.dispose()), [meshes]);
  return <>{meshes.map(m => <mesh key={m.key} geometry={m.g} receiveShadow><meshStandardMaterial color="#c9d2d1" roughness={0.95} side={THREE.DoubleSide} /></mesh>)}</>;
}

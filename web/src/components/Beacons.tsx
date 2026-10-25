import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

export interface BeaconPoint { id: string; x: number; y: number; z: number }

/** Answers that point at things ("where is the printer", "these rooms") mark them in the 3D view: a pulsing ring on the floor, a slim beam of
 *  light and a small arrow above, so the eye finds them without reading a list. Limited by the caller to a handful of points. */
export function Beacons({ points, color = "#ffd45c" }: { points: BeaconPoint[]; color?: string }) {
  const group = useRef<THREE.Group>(null);
  const { invalidate } = useThree();
  useFrame(({ clock }) => {
    const g = group.current;
    if (!g || !g.children.length) return;
    const t = clock.elapsedTime;
    g.children.forEach((child, i) => {
      const ring = child.getObjectByName("ring") as THREE.Mesh | undefined, arrow = child.getObjectByName("arrow") as THREE.Mesh | undefined;
      const k = (t * 0.75 + i * 0.17) % 1;
      if (ring) { ring.scale.setScalar(0.45 + k * 1.7); (ring.material as THREE.MeshBasicMaterial).opacity = 0.75 * (1 - k); }
      if (arrow) arrow.position.y = 3.55 + Math.sin(t * 3 + i) * 0.12;
    });
    invalidate();
  });
  return (
    <group ref={group}>
      {points.map(p => (
        <group key={p.id} position={[p.x, p.y, p.z]}>
          <mesh name="ring" rotation={[-Math.PI / 2, 0, 0]} renderOrder={5}><ringGeometry args={[0.42, 0.52, 40]} /><meshBasicMaterial color={color} transparent depthWrite={false} /></mesh>
          <mesh position={[0, 1.7, 0]} renderOrder={4}><cylinderGeometry args={[0.04, 0.04, 3.4, 8]} /><meshBasicMaterial color={color} transparent opacity={0.3} depthWrite={false} /></mesh>
          <mesh name="arrow" position={[0, 3.55, 0]} rotation={[Math.PI, 0, 0]} renderOrder={6}><coneGeometry args={[0.2, 0.38, 4]} /><meshBasicMaterial color={color} /></mesh>
        </group>
      ))}
    </group>
  );
}

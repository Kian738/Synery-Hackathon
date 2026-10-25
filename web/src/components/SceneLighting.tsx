import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import * as THREE from "three";

/** Daylight rig for the building: a warm key light that casts soft shadows over the whole model, a cool fill from the opposite side,
 *  sky/ground bounce, and a distance fog tinted like the background so the model sits in a place instead of a void.
 *  `interior` (Guide me) swaps the sun for even, brighter ambient light so corridors never go dark. */
export function SceneLighting({ cx, cz, span, interior }: { cx: number; cz: number; span: number; interior: boolean }) {
  const { scene, gl } = useThree();
  useEffect(() => {
    gl.shadowMap.enabled = true;
    gl.shadowMap.type = THREE.PCFSoftShadowMap;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = interior ? 1.05 : 1.12;
    const background = new THREE.Color("#0d1419");
    scene.background = background;
    scene.fog = interior ? null : new THREE.Fog(background, span * 2.2, span * 6);
    return () => { scene.fog = null; };
  }, [scene, gl, span, interior]);
  const reach = Math.max(span * 0.9, 30);
  return (
    <>
      <hemisphereLight args={["#dbe9ff", "#3b4540", interior ? 1.35 : 0.95]} />
      <ambientLight intensity={interior ? 0.95 : 0.35} />
      <directionalLight
        position={[cx + span * 0.7, Math.max(60, span * 0.9), cz + span * 0.55]}
        intensity={interior ? 0.8 : 2.1}
        color="#fff3e0"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.04}
        shadow-camera-left={-reach}
        shadow-camera-right={reach}
        shadow-camera-top={reach}
        shadow-camera-bottom={-reach}
        shadow-camera-near={1}
        shadow-camera-far={span * 4 + 120}
        target-position={[cx, 0, cz]}
      />
      <directionalLight position={[cx - span * 0.6, Math.max(25, span * 0.4), cz - span * 0.5]} intensity={0.55} color="#bcd8f2" />
    </>
  );
}

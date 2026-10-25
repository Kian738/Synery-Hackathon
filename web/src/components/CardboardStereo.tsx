import { useEffect, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

/**
 * Side-by-side stereo for a phone in a Cardboard-style viewer (no WebXR). Renders after everything else
 * (priority 1 takes over R3F's own render), one half of the canvas per eye. No lens distortion in v1.
 * eyeSep 0.064 m is a typical adult interpupillary distance, not a measured one.
 */
export function CardboardStereo({ eyeSep = 0.064 }: { eyeSep?: number }) {
  const { gl, scene, camera, size } = useThree();
  const stereo = useMemo(() => { const s = new THREE.StereoCamera(); s.eyeSep = eyeSep; return s; }, [eyeSep]);
  useEffect(() => {
    gl.autoClear = false;
    gl.domElement.dataset.stereo = "cardboard";
    return () => { gl.autoClear = true; gl.setScissorTest(false); gl.setViewport(0, 0, size.width, size.height); delete gl.domElement.dataset.stereo; };
  }, [gl, size.width, size.height]);
  useFrame(() => {
    const cam = camera as THREE.PerspectiveCamera, aspect = cam.aspect, w = Math.floor(size.width / 2), h = size.height;
    cam.aspect = w / h; cam.updateProjectionMatrix(); cam.updateMatrixWorld();
    stereo.update(cam);
    gl.setScissorTest(false); gl.clear();
    gl.setScissorTest(true);
    gl.setScissor(0, 0, w, h); gl.setViewport(0, 0, w, h); gl.render(scene, stereo.cameraL);
    gl.setScissor(w, 0, w, h); gl.setViewport(w, 0, w, h); gl.render(scene, stereo.cameraR);
    gl.setScissorTest(false); gl.setViewport(0, 0, size.width, size.height);
    cam.aspect = aspect; cam.updateProjectionMatrix();
  }, 1);
  return null;
}

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { ribbon, type Pt } from "./ar";

/** One AR session: the walked line of the current floor drawn as a ribbon on the floor, starting where the person stands, facing where
 *  the phone pointed when they pressed "Start here". WebXR immersive-ar (Android Chrome); the caller checks support first.
 *  Floor and position are assumed, not tracked: AR is meant for decision points, with the instruction card as the source of truth. */
export function ArRoute({ path, headingDeg, onEnd }: { path: Pt[]; headingDeg: number; onEnd: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let session: XRSession | null = null, renderer: THREE.WebGLRenderer | null = null, stopped = false;
    (async () => {
      try {
        const xr = (navigator as unknown as { xr: XRSystem }).xr;
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.xr.enabled = true;
        const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera();
        scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.4));
        const { positions, indices } = ribbon(path, { origin: path[0], headingDeg });
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setIndex(indices);
        scene.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0xffd45c, transparent: true, opacity: 0.85, side: THREE.DoubleSide })));
        session = await xr.requestSession("immersive-ar", { requiredFeatures: ["local-floor"], optionalFeatures: ["dom-overlay"], domOverlay: host.current ? { root: host.current } : undefined } as XRSessionInit);
        if (stopped) { await session.end(); return; }
        session.addEventListener("end", () => { if (!stopped) onEnd(); });
        await renderer.xr.setSession(session);
        renderer.setAnimationLoop(() => renderer!.render(scene, camera));
      } catch (e) { setError(e instanceof Error ? e.message : "AR could not start on this phone."); }
    })();
    return () => { stopped = true; renderer?.setAnimationLoop(null); session?.end().catch(() => undefined); renderer?.dispose(); };
  }, [path, headingDeg, onEnd]);
  return <div ref={host} className="cmp-ar" role="dialog" aria-label="Route in AR">
    <p>Hold the phone up toward where you are walking. The yellow line is your route.</p>
    {error && <p className="cmp-error" role="alert">{error}</p>}
    <button className="cmp-btn primary" onClick={onEnd}>Exit AR</button>
  </div>;
}

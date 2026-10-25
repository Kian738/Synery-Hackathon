import { useFrame, useThree } from "@react-three/fiber";
import { XROrigin, useXR } from "@react-three/xr";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { GuideCard } from "../lib/guideCard";
import { vrPose } from "../lib/xr";

/** The headset side of Guide me. While a VR session is on:
 *  - the rig (XROrigin) stands where the walk is and faces along the path; the headset adds natural looking around on top;
 *  - a panel follows the gaze gently, 1.3 m ahead and a little below the horizon, with the same card as the screen (action, place, metres to go);
 *  - the controller trigger (or a pinch) plays and pauses the walk.
 *  The panel is drawn on a 2D canvas, so no font is downloaded. Not verified on a physical headset from here. */
export function VrRig({ card, onToggle }: { card: GuideCard | null; onToggle: () => void }) {
  const session = useXR(s => s.session);
  const origin = useRef<THREE.Group>(null);
  const panel = useRef<THREE.Mesh>(null);
  const { gl } = useThree();
  const canvas = useMemo(() => { const c = document.createElement("canvas"); c.width = 1024; c.height = 400; return c; }, []);
  const texture = useMemo(() => { const t = new THREE.CanvasTexture(canvas); t.colorSpace = THREE.SRGBColorSpace; return t; }, [canvas]);
  const drawn = useRef("");
  const tools = useMemo(() => ({ head: new THREE.Vector3(), q: new THREE.Quaternion(), fwd: new THREE.Vector3(), target: new THREE.Vector3() }), []);
  useEffect(() => { vrPose.active = !!session; return () => { vrPose.active = false; }; }, [session]);
  useEffect(() => {
    if (!session) return;
    const select = () => onToggle();
    session.addEventListener("select", select);
    return () => session.removeEventListener("select", select);
  }, [session, onToggle]);
  useFrame((_, dt) => {
    const rig = origin.current;
    if (rig && vrPose.active) { rig.position.set(vrPose.x, vrPose.y, vrPose.z); rig.rotation.set(0, vrPose.yaw, 0); }
    const mesh = panel.current;
    if (!mesh || !session) return;
    const key = card ? `${card.index}|${card.arrived}|${card.remaining}` : "none";
    if (key !== drawn.current) { drawn.current = key; paint(canvas, card); texture.needsUpdate = true; }
    const cam = gl.xr.getCamera();
    cam.getWorldPosition(tools.head); cam.getWorldQuaternion(tools.q);
    tools.fwd.set(0, 0, -1).applyQuaternion(tools.q); tools.fwd.y = 0;
    if (tools.fwd.lengthSq() < 1e-4) return;
    tools.fwd.normalize();
    tools.target.copy(tools.head).addScaledVector(tools.fwd, 1.3); tools.target.y = tools.head.y - 0.42;
    if (mesh.position.lengthSq() === 0) mesh.position.copy(tools.target); else mesh.position.lerp(tools.target, 1 - Math.exp(-dt * 6));
    mesh.lookAt(tools.head.x, mesh.position.y, tools.head.z);
  });
  return (
    <>
      <XROrigin ref={origin} />
      {session && <mesh ref={panel} renderOrder={50}><planeGeometry args={[0.8, 0.312]} /><meshBasicMaterial map={texture} transparent depthTest={false} toneMapped={false} /></mesh>}
    </>
  );
}

function paint(canvas: HTMLCanvasElement, card: GuideCard | null) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const { width: w, height: h } = canvas;
  g.clearRect(0, 0, w, h);
  g.fillStyle = "rgba(16,25,30,0.9)"; g.beginPath(); g.roundRect(0, 0, w, h, 48); g.fill();
  if (!card) return;
  g.textBaseline = "alphabetic";
  g.fillStyle = "#8fa6af"; g.font = "600 34px system-ui, sans-serif";
  g.fillText(card.arrived ? "Finished" : `Step ${card.index} of ${card.total}`, 48, 74);
  g.fillStyle = "#f4f8f9"; g.font = "800 66px system-ui, sans-serif";
  g.fillText(card.arrived ? "You have arrived" : (card.step?.headline || card.step?.text || "").slice(0, 26), 48, 164);
  g.fillStyle = "#d6e2e6"; g.font = "500 42px system-ui, sans-serif";
  g.fillText((card.step?.target ?? "").slice(0, 34), 48, 232);
  if (card.after && !card.arrived) { g.fillStyle = "#7f959e"; g.font = "400 32px system-ui, sans-serif"; g.fillText(`After that: ${(card.after.headline ?? card.after.short).toLowerCase()}`.slice(0, 48), 48, 330); }
  if (!card.arrived) {
    g.fillStyle = "#1d2c33"; g.beginPath(); g.roundRect(w - 330, 80, 282, 150, 36); g.fill();
    g.fillStyle = "#ffe39a"; g.textAlign = "center";
    if (card.remaining >= 3) { g.font = "800 100px system-ui, sans-serif"; g.fillText(String(card.remaining), w - 215, 190); g.font = "600 40px system-ui, sans-serif"; g.fillStyle = "#c9b36a"; g.fillText("m", w - 90, 190); }
    else { g.font = "800 60px system-ui, sans-serif"; g.fillText("now", w - 189, 177); }
    g.textAlign = "start";
  }
}

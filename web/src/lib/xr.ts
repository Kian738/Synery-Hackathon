import { createXRStore } from "@react-three/xr";

/** One WebXR store for the whole app. `emulate: false`: no injected headset emulator, a real headset or nothing. */
export const xrStore = createXRStore({ emulate: false, foveation: 0.5 });

/** Where the walk puts the person: the VR rig follows this pose (feet on the floor, facing along the path) while a headset is on. */
export const vrPose = { active: false, x: 0, y: 0, z: 0, yaw: 0 };

export async function vrSupported(): Promise<boolean> {
  try {
    const xr = (navigator as Navigator & { xr?: { isSessionSupported?: (mode: string) => Promise<boolean> } }).xr;
    return Boolean(await xr?.isSessionSupported?.("immersive-vr"));
  } catch { return false; }
}

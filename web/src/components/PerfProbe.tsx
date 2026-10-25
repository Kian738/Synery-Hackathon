import { useFrame, useThree } from "@react-three/fiber";

/** Writes the renderer's own counters onto the canvas element (`data-perf-*`), so tests and `?perf=1` can read draw calls,
 *  triangles and frame time without a profiler. Cheap: a few property reads per rendered frame. */
export function PerfProbe() {
  const { gl } = useThree();
  let last = performance.now();
  useFrame(() => {
    const now = performance.now(), el = gl.domElement, info = gl.info;
    el.dataset.perfCalls = String(info.render.calls);
    el.dataset.perfTriangles = String(info.render.triangles);
    el.dataset.perfGeometries = String(info.memory.geometries);
    el.dataset.perfFrameMs = (now - last).toFixed(1);
    last = now;
  });
  return null;
}

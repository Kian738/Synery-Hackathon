import { test, expect } from "@playwright/test";
import { getAssetVisual, KNOWN_ASSET_TYPES } from "../src/scene-assets/catalog";
import { coplanarFaces } from "../src/scene-assets/zfight";
import type { Lod } from "../src/scene-assets/parts";

// Pure data: every model, both levels of detail, three footprints. Prints the offenders so a fix is a one-line change.
const SIZES: [number, number][] = [[0.5, 0.5], [1.2, 0.6], [2.4, 1.0]];

test("no two differently coloured model parts share a face plane", () => {
  const bad: string[] = [];
  for (const type of KNOWN_ASSET_TYPES) for (const lod of ["overview", "interior"] as Lod[]) for (const [w, d] of SIZES) {
    const v = getAssetVisual({ type, footprint: { width_m: w, depth_m: d } }, lod);
    const hits = coplanarFaces(v.parts, w, d);
    if (hits.length) bad.push(`${type}/${lod}/${w}x${d}: ${hits.slice(0, 3).map(h => `#${h.a}~#${h.b} ${h.axis}${h.side}@${h.at.toFixed(3)}`).join(", ")} (${hits.length})`);
  }
  console.log(`${bad.length} offenders\n${bad.join("\n")}`);
  expect(bad).toEqual([]);
});

test("the guard never reshapes a part by more than 15 mm per axis", () => {
  const bad: string[] = [];
  for (const type of KNOWN_ASSET_TYPES) for (const lod of ["overview", "interior"] as Lod[]) for (const [w, d] of SIZES) {
    const fp = { footprint: { width_m: w, depth_m: d } };
    const raw = getAssetVisual({ type, ...fp }, lod, false).parts, fixed = getAssetVisual({ type, ...fp }, lod, true).parts;
    expect(fixed.length).toBe(raw.length);
    raw.forEach((p, i) => [0, 1, 2].forEach(k => {
      const size = k === 0 ? w : k === 2 ? d : 1, q = fixed[i];
      const moved = Math.max(Math.abs(p.position[k] - q.position[k]) * size, Math.abs(p.scale[k] - q.scale[k]) * size);
      if (moved > 0.015) bad.push(`${type}/${lod}/${w}x${d} part ${i} axis ${k}: ${(moved * 1000).toFixed(1)} mm`);
    }));
  }
  expect(bad).toEqual([]);
});

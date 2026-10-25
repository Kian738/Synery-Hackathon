import { test, expect } from "@playwright/test";
import { facingDegrees } from "../src/lib/facing";
import type { Asset } from "../src/lib/types";

const a = (id: string, type: string, x: number, y: number, rot = 0) => ({ id, type, space_id: "s", position: [x, y], footprint: { width_m: 0.5, depth_m: 0.5, rotation_deg: rot } }) as unknown as Asset;
/** Scene direction of the model front (local -Z) for a Y rotation in degrees; plan y is scene -z. */
const frontPlan = (deg: number) => { const r = (deg * Math.PI) / 180; return [-Math.sin(r), Math.cos(r)]; };

test("a chair faces the nearest desk, whatever the dataset rotation says", () => {
  for (const rot of [0, 90, 200]) {
    const chair = a("c", "chair", 0, 0, rot), desk = a("d", "desk", 2, 0), far = a("f", "desk", 0, -2.5);
    const [fx, fy] = frontPlan(facingDegrees(chair, [chair, desk, far]));
    expect(fx).toBeCloseTo(1, 5); expect(fy).toBeCloseTo(0, 5);
  }
});
test("no table in reach keeps the measured rotation; wall-backed items are untouched", () => {
  const chair = a("c", "chair", 0, 0, 30), desk = a("d", "desk", 9, 0), sofa = a("s", "sofa", 0, 0, 40);
  expect(facingDegrees(chair, [chair, desk])).toBe(210);
  expect(facingDegrees(sofa, [sofa, a("t", "tv_stand", 1, 0)])).toBe(220);
  expect(facingDegrees(a("w", "wardrobe", 0, 0, 40), [])).toBe(220);
});

import { test, expect } from "@playwright/test";
import { facingDegrees, facingTable, FACING_OFFSET_DEG } from "../src/lib/facing";
import type { Asset } from "../src/lib/types";

const a = (id: string, type: string, x: number, y: number, rot = 0, w = 0.5, d = 0.5) => ({ id, type, space_id: "s", position: [x, y], footprint: { width_m: w, depth_m: d, rotation_deg: rot } }) as unknown as Asset;
/** Plan direction of the model front (local -Z) after a scene Y rotation; plan y is scene -z. */
const front = (deg: number) => { const r = (deg * Math.PI) / 180; return [-Math.sin(r), Math.cos(r)]; };
const room: [number, number][] = [[0, 0], [6, 0], [6, 4], [0, 4]];

test("a chair tucked at a desk turns to the desk's own axis, never to its corner", () => {
  const desk = a("d", "desk", 0, 0, 30, 1.6, 0.8);
  const ux = [Math.cos(Math.PI / 6), Math.sin(Math.PI / 6)], uy = [-Math.sin(Math.PI / 6), Math.cos(Math.PI / 6)];
  const chair = a("c", "chair", 0.3 * ux[0] + 0.7 * uy[0], 0.3 * ux[1] + 0.7 * uy[1], 123);
  const [fx, fy] = front(facingDegrees(chair, [chair, desk]));
  expect(fx).toBeCloseTo(-uy[0], 5); expect(fy).toBeCloseTo(-uy[1], 5);
});

test("a chair away from every desk, and every non wall-backed item, keeps the measured rotation", () => {
  const far = a("d", "desk", 5, 0, 0, 1.6, 0.8), chair = a("c", "chair", 0, 0, 30);
  expect(facingDegrees(chair, [chair, far])).toBe(30 + FACING_OFFSET_DEG);
  for (const type of ["armchair", "lecture_seating_row", "desk", "bed", "toilet", "sink"]) { const o = a("o", type, 0.3, 2, 40); expect(facingDegrees(o, [o], room)).toBe(40 + FACING_OFFSET_DEG); }
});

test("a wall-backed item whose back is not on the wall turns square to the wall, back against it", () => {
  // vending machine at rotation 0 beside the west wall (x = 0): measured front points -y, along the wall
  const vm = a("v", "vending_machine", 0.3, 2, 0, 0.6, 0.6);
  const [fx, fy] = front(facingDegrees(vm, [vm], room));
  expect(fx).toBeCloseTo(1, 5); expect(fy).toBeCloseTo(0, 5);                 // faces east, into the room
  // already correct (front into the room, back on the west wall): untouched
  const ok = a("o", "vending_machine", 0.3, 2, 90, 0.6, 0.6);
  expect(facingDegrees(ok, [ok], room)).toBe(90 + FACING_OFFSET_DEG);
  // far from every wall: untouched
  const mid = a("m", "vending_machine", 3, 2, 0, 0.6, 0.6);
  expect(facingDegrees(mid, [mid], room)).toBe(FACING_OFFSET_DEG);
});

test("table: the room's items are resolved per room", () => {
  const vm = a("v", "vending_machine", 0.3, 2, 0, 0.6, 0.6);
  const t = facingTable([vm], new Map([["s", room]]));
  const [fx] = front(t.get("v")!);
  expect(fx).toBeCloseTo(1, 5);
});

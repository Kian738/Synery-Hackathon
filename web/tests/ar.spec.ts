import { test, expect } from "@playwright/test";
import { arSupport, nextTurn, ribbon, toArLocal, turnAngle } from "../src/companion/ar";

const close = (a: number[], b: number[]) => a.forEach((v, i) => expect(v).toBeCloseTo(b[i], 6));

test("plan metres map into the phone's frame: ahead is -Z, right is +X", () => {
  const here = { origin: [10, 20] as [number, number], headingDeg: 0 };       // facing north
  close(toArLocal([10, 25], here), [0, 0, -5]);                                 // 5 m north is straight ahead
  close(toArLocal([13, 20], here), [3, 0, 0]);                                  // 3 m east is to the right
  const east = { origin: [10, 20] as [number, number], headingDeg: 90 };        // facing east
  close(toArLocal([14, 20], east), [0, 0, -4]);
  close(toArLocal([10, 17], east), [3, 0, 0]);                                  // south is to the right when facing east
  close(toArLocal([10, 20], east), [0, 0, 0]);
});

test("the ribbon has two vertices per point, two triangles per segment, and sits above the floor", () => {
  const r = ribbon([[0, 0], [0, 4], [3, 4]], { origin: [0, 0], headingDeg: 0 });
  expect(r.positions.length).toBe(3 * 6);
  expect(r.indices.length).toBe(6 * 2);
  expect(Math.max(...r.indices)).toBe(5);
  for (let i = 1; i < r.positions.length; i += 3) expect(r.positions[i]).toBeGreaterThan(0);
});

test("turn angle and next turn tell the person where to go", () => {
  expect(turnAngle(0, [[0, 0], [5, 0]])).toBeCloseTo(90, 6);     // east while facing north: turn right
  expect(turnAngle(90, [[0, 0], [0, 5]])).toBeCloseTo(-90, 6);   // north while facing east: turn left
  expect(turnAngle(350, [[0, 0], [0, 5]])).toBeCloseTo(10, 6);   // wraps correctly
  expect(turnAngle(0, [[0, 0]])).toBeNull();
  const turn = nextTurn([[0, 0], [0, 3], [4, 3]], { origin: [0, 0], headingDeg: 0 })!;
  expect(turn.distance).toBeCloseTo(5, 6);
  close(turn.direction, [0, -1]);
});

test("AR support follows what the browser reports, and fails closed", async () => {
  expect(await arSupport({})).toEqual({ ar: false, vr: false });                                         // iOS Safari: no WebXR
  expect(await arSupport({ xr: { isSessionSupported: async m => m === "immersive-ar" } })).toEqual({ ar: true, vr: false });
  expect(await arSupport({ xr: { isSessionSupported: async () => { throw new Error("blocked"); } } })).toEqual({ ar: false, vr: false });
});

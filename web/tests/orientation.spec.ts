import { test, expect } from "@playwright/test";
import { quaternionFromOrientation, recentered, rotate, yawOf } from "../src/companion/orientation";

/** Pure maths for Cardboard VR head tracking (no browser). For each screen angle, the pose that holds the phone
 *  upright with the screen level must give a level camera (up = +Y, forward horizontal), and turning (alpha) must
 *  read as a yaw of the same size. Real phones may still differ in axis signs (iOS vs Android): not provable here. */
const LEVEL: Record<number, [number, number]> = { 0: [90, 0], 90: [0, -90], 180: [-90, 0], 270: [0, 90] };   // [beta, gamma]
const close = (a: number[], b: number[]) => a.forEach((v, i) => expect(v).toBeCloseTo(b[i], 5));
const deg = (r: number) => (r * 180) / Math.PI;
const wrap = (d: number) => ((d + 540) % 360) - 180;

test("portrait, upright, alpha 0 is the identity (looks down -Z)", () => {
  close(quaternionFromOrientation(0, 90, 0, 0), [0, 0, 0, 1]);
});

for (const angle of [0, 90, 180, 270]) {
  test(`screen angle ${angle}: level pose has a level horizon and alpha turns the view`, () => {
    const [beta, gamma] = LEVEL[angle];
    for (const alpha of [0, 40, 200]) {
      const q = quaternionFromOrientation(alpha, beta, gamma, angle);
      close(rotate(q, [0, 1, 0]), [0, 1, 0]);
      expect(rotate(q, [0, 0, -1])[1]).toBeCloseTo(0, 5);
    }
    const turn = wrap(deg(yawOf(quaternionFromOrientation(40, beta, gamma, angle)) - yawOf(quaternionFromOrientation(0, beta, gamma, angle))));
    expect(turn).toBeCloseTo(40, 4);
    // tilting the phone up raises the view
    const tilted = angle === 0 ? quaternionFromOrientation(0, 100, 0, 0) : angle === 180 ? quaternionFromOrientation(0, -100, 0, 180) : quaternionFromOrientation(0, 0, angle === 90 ? -100 : 100, angle);
    expect(rotate(tilted, [0, 0, -1])[1]).toBeGreaterThan(0.1);
  });
}

test("recentering makes the current heading straight ahead and keeps pitch", () => {
  const q = quaternionFromOrientation(123, 100, 0, 0);
  const r = recentered(q, yawOf(q));
  const f = rotate(r, [0, 0, -1]);
  expect(f[0]).toBeCloseTo(0, 5);
  expect(f[1]).toBeCloseTo(rotate(q, [0, 0, -1])[1], 5);
  expect(f[2]).toBeLessThan(0);
});

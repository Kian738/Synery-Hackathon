import { expect, test } from "@playwright/test";
import { rideMode } from "../src/lib/rideMode";

const flight = [{ x: 0, y: 0 }, { x: 0, y: 1 }, { x: 0, y: 2 }];
test("rideMode walks only clean flights", () => {
  expect(rideMode({ kind: "stairs", from: { x: 0, y: -0.3 }, to: { x: 0, y: 0.5 }, flight: [{ x: 0, y: 0 }, { x: 0, y: 0.6 }] })).toBe("walk");
  expect(rideMode({ kind: "lift", from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, flight })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, flight: null })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 0 }, to: { x: 5, y: 0 }, flight })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 1 }, to: { x: 0, y: 1 }, flight })).toBe("interlude");
});

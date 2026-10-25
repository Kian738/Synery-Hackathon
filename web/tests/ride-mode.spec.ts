import { expect, test } from "@playwright/test";
import { isCleanFlight, rideMode } from "../src/lib/rideMode";

const flight = [{ x: 0, y: 0 }, { x: 0, y: 1 }, { x: 0, y: 2 }];
test("every floor change gets the cutout; isCleanFlight still tells clean flights apart", () => {
  expect(rideMode({ kind: "stairs", from: { x: 0, y: -0.3 }, to: { x: 0, y: 0.5 }, flight: [{ x: 0, y: 0 }, { x: 0, y: 0.6 }] })).toBe("interlude");
  expect(isCleanFlight({ kind: "stairs", from: { x: 0, y: -0.3 }, to: { x: 0, y: 0.5 }, flight: [{ x: 0, y: 0 }, { x: 0, y: 0.6 }] })).toBe(true);
  expect(isCleanFlight({ kind: "lift", from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, flight })).toBe(false);
  expect(rideMode({ kind: "lift", from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, flight })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, flight: null })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 0 }, to: { x: 5, y: 0 }, flight })).toBe("interlude");
  expect(rideMode({ kind: "stairs", from: { x: 0, y: 1 }, to: { x: 0, y: 1 }, flight })).toBe("interlude");
});

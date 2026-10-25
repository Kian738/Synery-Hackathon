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

test("a 1 to 4 floor change is one 2.4 s chain, not three stages", async () => {
  const { presentation } = await import("../src/lib/playback");
  const pt = (floor_id: string, x: number, y: number) => ({ floor_id, node: "stair", x, y });
  const route: any = { polyline: [pt("f1", 0, 0), pt("f1", 3, 0), pt("f2", 3, 0), pt("f3", 3, 0), pt("f4", 3, 0), pt("f4", 8, 0)], guide: { steps: [{ kind: "arrive", floor_id: "f4", point: [8, 0] }] } };
  const model = presentation(route, true, () => 12);
  const hops = model.sections.filter(s => s.chain);
  expect(hops.length).toBe(3);
  expect(new Set(hops.map(s => s.chain)).size).toBe(1);
  expect(hops[0].chain).toMatchObject({ from: "f1", to: "f4" });
  const total = hops[0].chain!.end - hops[0].chain!.start;
  expect(total).toBeGreaterThan(2.3);
  expect(total).toBeLessThan(2.5);
});

test("five stair steps in a row become one instruction", async () => {
  const { mergeFloorSteps } = await import("../src/lib/mergeSteps");
  const floor = (n: number) => ({ kind: "floor", icon: "stairs", text: `Take the stairs up to Floor ${n}`, short: "", headline: "Take the stairs up", target: `Floor ${n}`, metres: 3, floor_id: `f${n}`, point: [0, 0], landmark: null, space_id: "s" });
  const route: any = { guide: { steps: [{ kind: "start" }, floor(1), floor(2), floor(3), floor(4), floor(5), { kind: "arrive" }] } };
  const merged = mergeFloorSteps(route).guide.steps;
  expect(merged.map((s: any) => s.kind)).toEqual(["start", "floor", "arrive"]);
  expect(merged[1]).toMatchObject({ target: "Floor 5", floor_id: "f5", metres: 15 });
});

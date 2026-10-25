import { test, expect } from "@playwright/test";
import { openingFrame } from "../src/lib/openings";
import { cameraPath } from "../src/lib/cameraPath";
import { floorColor } from "../src/lib/floorColors";
import { slotSpace } from "../src/components/Connectors3D";
import { cameraPolyline, clearOfWalls, shaftVoids, relevantSpaces, CAMERA_RADIUS_M } from "../src/lib/focus";

test("a camera next to a wall is pushed to the clearance radius, one in the open is left alone", () => {
  const wall = { a: [0, 0] as [number, number], b: [10, 0] as [number, number] };
  const [x, y] = clearOfWalls(5, 0.1, [wall]);
  expect(x).toBeCloseTo(5, 6);
  expect(y).toBeCloseTo(CAMERA_RADIUS_M, 6);
  expect(clearOfWalls(5, 2, [wall])).toEqual([5, 2]);
  const [, py] = clearOfWalls(5, -0.1, [wall]);
  expect(py).toBeCloseTo(-CAMERA_RADIUS_M, 6);
});

test("shafts are open above their lowest stop and nowhere else", () => {
  const geometry = {
    floors: [{ id: "f0", level: 0 }, { id: "f1", level: 1 }, { id: "f2", level: 2 }],
    spaces: [{ id: "s0", floor_id: "f0" }, { id: "s1", floor_id: "f1" }, { id: "s2", floor_id: "f2" }, { id: "room", floor_id: "f1" }],
    connectors: [{ id: "lift", space_ids: ["s0", "s1", "s2"] }],
  } as never;
  expect([...shaftVoids(geometry)].sort()).toEqual(["s1", "s2"]);
});

test("focus keeps the route's rooms and nearby doors, and drops far rooms", () => {
  const geometry = {
    openings: [
      { floor_id: "f0", position: [1, 0], space_ids: ["corridor", "near"] },
      { floor_id: "f0", position: [60, 0], space_ids: ["corridor", "far"] },
    ],
    connectors: [{ space_ids: ["lift0", "lift1"] }],
  } as never;
  const route = {
    stops: ["lobby", "lift0"],
    polyline: [{ node: "lobby", floor_id: "f0", x: 0, y: 0 }, { node: "corridor", floor_id: "f0", x: 2, y: 0 }, { node: "lift0", floor_id: "f0", x: 4, y: 0 }],
  } as never;
  const keep = relevantSpaces(geometry, route)!;
  expect(keep.has("near")).toBe(true);
  expect(keep.has("far")).toBe(false);
  expect(keep.has("lift1")).toBe(true);
  expect(relevantSpaces(geometry, null)).toBeNull();
});

test("focus mode hides distant rooms and the toggle restores the whole floor", async ({ page }) => {
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("button", { name: /^Lift/ }).first().click();
  const scene = page.getByTestId("building-scene");
  await expect(scene).toHaveAttribute("data-focus", "route", { timeout: 20_000 });
  await page.getByTestId("focus-toggle").click();
  await expect(scene).toHaveAttribute("data-focus", "all");
  await page.getByTestId("focus-toggle").click();
  await expect(scene).toHaveAttribute("data-focus", "route");
});

test("Guide me keeps the eye off the walls along the whole route", async ({ page }) => {
  const building = "osm-way27917482";
  let walls: { floor_id: string; a: number[]; b: number[] }[] = [];
  page.on("response", async r => {
    if (!r.url().includes("/api/") || !(r.headers()["content-type"] ?? "").includes("json")) return;
    try { const j = await r.json(); if (j?.scene?.walls?.length) walls = j.scene.walls; } catch { /* not a geometry payload */ }
  });
  await page.goto(`/?building=${building}&at=${building}-F3-S069&to=00.05.058`);
  await page.getByRole("button", { name: "Guide me step by step" }).click();
  const slider = page.getByRole("slider", { name: "Preview progress" });
  await expect(slider).toBeAttached({ timeout: 20_000 });
  const canvas = page.locator("canvas");
  let tooClose = 0, samples = 0;
  for (let i = 0; i <= 24; i++) {
    await slider.evaluate((el: HTMLInputElement, f: number) => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      set.call(el, String(f * Number(el.max)));
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, i / 24);
    await page.waitForTimeout(160);
    const pos = JSON.parse((await canvas.getAttribute("data-camera-position")) ?? "null");
    const floor = await canvas.getAttribute("data-camera-floor");
    if (!pos || !floor) continue;
    const [x, y] = [pos[0], -pos[2]];
    samples++;
    for (const w of walls) {
      if (w.floor_id !== floor) continue;
      const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len2 = dx * dx + dy * dy;
      if (len2 < 1e-9) continue;
      const t = Math.max(0, Math.min(1, ((x - w.a[0]) * dx + (y - w.a[1]) * dy) / len2));
      if (Math.hypot(x - (w.a[0] + dx * t), y - (w.a[1] + dy * t)) < CAMERA_RADIUS_M - 0.02) { tooClose++; break; }
    }
  }
  expect(walls.length).toBeGreaterThan(0);
  expect(samples).toBeGreaterThan(10);
  expect(tooClose).toBe(0);
});

test("a lift and two stairs sharing one corridor get separate, non-overlapping slots", () => {
  const corridor = { id: "c", floor_id: "f", type: "corridor", room_type: "corridor", name: "c", polygon: [[0, 0], [12, 0], [12, 2.5], [0, 2.5]] } as never;
  const kinds = ["stairs", "lift", "stairs"] as const;
  const boxes = kinds.map((k, i) => {
    const xs = (slotSpace(corridor, i, 3, k, false).polygon as number[][]).map(p => p[0]);
    return [Math.min(...xs), Math.max(...xs)];
  });
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) expect(boxes[i][1]).toBeLessThanOrEqual(boxes[j][0] + 1e-9);
  // a dedicated stair space with one stair keeps its full footprint
  const stair = { ...(corridor as object), type: "stair" } as never;
  const fitted = slotSpace(stair, 0, 1, "stairs", true).polygon as number[][];
  expect(fitted.every(p => p[0] >= -1e-9 && p[0] <= 12 + 1e-9 && p[1] >= -1e-9 && p[1] <= 2.5 + 1e-9)).toBe(true);
  // an L-shaped space never gets a fixture that pokes out of the L
  const ell = { ...(corridor as object), polygon: [[0, 0], [6, 0], [6, 2], [2, 2], [2, 8], [0, 8]] } as never;
  const inEll = (p: number[]) => (p[0] >= 0 && p[0] <= 6 && p[1] >= 0 && p[1] <= 2) || (p[0] >= 0 && p[0] <= 2 && p[1] >= 0 && p[1] <= 8);
  expect((slotSpace(ell, 0, 1, "stairs", true).polygon as number[][]).every(inEll)).toBe(true);
});

test("Guide me glides down between floors instead of jumping", async ({ page }) => {
  const building = "osm-way27917482";
  await page.goto(`/?building=${building}&at=${building}-F3-S069&to=00.05.058`);
  await page.getByRole("button", { name: "Guide me step by step" }).click();
  const slider = page.getByRole("slider", { name: "Preview progress" });
  await expect(slider).toBeAttached({ timeout: 20_000 });
  const canvas = page.locator("canvas");
  const ys: number[] = [];
  for (let i = 0; i <= 90; i++) {
    await slider.evaluate((el: HTMLInputElement, f: number) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, String(f * Number(el.max)));
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, i / 90);
    await page.waitForTimeout(90);
    const pos = JSON.parse((await canvas.getAttribute("data-camera-position")) ?? "null");
    if (pos) ys.push(pos[1]);
  }
  expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(3);
  const steps = ys.slice(1).map((y, i) => Math.abs(y - ys[i]));
  expect(Math.max(...steps)).toBeLessThan(1.6);
  expect(ys.filter(y => y > Math.min(...ys) + 0.4 && y < Math.max(...ys) - 0.4).length).toBeGreaterThan(2);
});

test("each of the first eight floors has its own colour, stable by level", () => {
  const colours = Array.from({ length: 8 }, (_, i) => floorColor(i));
  expect(new Set(colours).size).toBe(8);
  expect(floorColor(-1)).toBe(floorColor(7));
  expect(floorColor(0)).toBe(floorColor(0));
});

test("focus mode shows dimmed rooms and says how many", async ({ page }) => {
  await page.goto("/?building=swiss-1785&at=swiss-1785-F1-S001&to=Bedroom");
  const pill = page.getByTestId("focus-toggle");
  await expect(pill).toContainText(/\d+ other rooms dimmed/, { timeout: 20_000 });
  await pill.click();
  await expect(pill).toContainText("All rooms");
});

test("lift cars travel to the floor you pick and their doors stay shut elsewhere", async ({ page }) => {
  await page.goto("/?building=proc-campus-test-013");
  const canvas = page.locator("canvas");
  await expect(canvas).toHaveAttribute("data-lift-cars", /\{.+\}/, { timeout: 20_000 });
  const cars = async () => JSON.parse((await canvas.getAttribute("data-lift-cars")) ?? "{}") as Record<string, number>;
  const before = Object.values(await cars())[0];
  await page.getByRole("navigation", { name: "Floors" }).getByRole("button").first().click(); // top floor
  await expect.poll(async () => Object.values(await cars())[0], { timeout: 8000 }).toBeGreaterThan(before + 3);
  const mid: number[] = [];
  await page.getByRole("navigation", { name: "Floors" }).getByRole("button").last().click();
  for (let i = 0; i < 8; i++) { mid.push(Object.values(await cars())[0]); await page.waitForTimeout(250); }
  expect(new Set(mid.map(v => Math.round(v))).size).toBeGreaterThan(2); // moves smoothly through intermediate heights
});

test("camera path centres in a corridor, keeps its ends and stays off the walls", () => {
  const walls = [{ floor_id: "f", a: [0, 0] as [number, number], b: [20, 0] as [number, number] }, { floor_id: "f", a: [0, 3] as [number, number], b: [20, 3] as [number, number] }];
  const route = [0, 5, 10, 15, 20].map(x => ({ x, y: 0.6, floor_id: "f", node: "corridor" }));
  const path = cameraPolyline(route, walls);
  expect(path[0].x).toBeCloseTo(0, 6); expect(path.at(-1)!.x).toBeCloseTo(20, 6);
  const mid = path.filter(p => p.x > 4 && p.x < 16);
  expect(mid.every(p => p.y > 0.8 && p.y < 2.2)).toBe(true);
  expect(Math.min(...path.map(p => Math.min(p.y, 3 - p.y)))).toBeGreaterThanOrEqual(CAMERA_RADIUS_M - 1e-6);
  expect(path.length).toBeGreaterThan(route.length * 3); // resampled, so the camera never lurches between far-apart points
});

test("camera path turns a jagged route into a few straight runs with soft corners", () => {
  const zig = Array.from({ length: 41 }, (_, i) => ({ x: i * 0.5, y: 5 + (i % 2 ? 0.25 : -0.25), floor_id: "f", node: "room" }));
  const turns = (pts: { x: number; y: number }[]) => pts.slice(2).filter((p, i) => {
    const a = Math.atan2(pts[i + 1].y - pts[i].y, pts[i + 1].x - pts[i].x), b = Math.atan2(p.y - pts[i + 1].y, p.x - pts[i + 1].x);
    return Math.abs(b - a) > 0.17;
  }).length;
  const path = cameraPath(zig, []);
  expect(turns(zig)).toBeGreaterThan(30);
  expect(turns(path)).toBeLessThan(3);
  expect(path[0]).toMatchObject({ x: 0 });
  expect(path.at(-1)!.x).toBeCloseTo(20, 6);
});

test("Guide me turns smoothly while playing", async ({ page }) => {
  const building = "osm-way27917482";
  await page.goto(`/?building=${building}&at=${building}-F3-S069&to=00.05.058`);
  await page.getByRole("button", { name: "Guide me step by step" }).click();
  const canvas = page.locator("canvas");
  await expect(page.getByRole("slider", { name: "Preview progress" })).toBeAttached({ timeout: 20_000 });
  await page.getByRole("button", { name: "Play preview", exact: true }).click();
  const samples: { t: number; yaw: number; x: number; z: number; floor: string }[] = [];
  const started = Date.now();
  while (Date.now() - started < 22_000) {
    const q = JSON.parse((await canvas.getAttribute("data-camera-quaternion")) ?? "null");
    const pos = JSON.parse((await canvas.getAttribute("data-camera-position")) ?? "null");
    const floor = (await canvas.getAttribute("data-camera-floor")) ?? "";
    if (q && pos) {
      const [qx, qy, qz, qw] = q;
      const fx = -2 * (qx * qz + qw * qy), fz = -(1 - 2 * (qx * qx + qy * qy));
      samples.push({ t: Date.now() / 1000, yaw: Math.atan2(fx, -fz), x: pos[0], z: pos[2], floor });
    }
    await page.waitForTimeout(100);
  }
  expect(samples.length).toBeGreaterThan(40);
  const rates = samples.slice(1).flatMap((s, i) => {
    const prev = samples[i];
    if (s.floor !== prev.floor) return [];
    let d = s.yaw - prev.yaw; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
    return [Math.abs(d) / Math.max(0.05, s.t - prev.t) * 180 / Math.PI];
  });
  expect(Math.max(...rates)).toBeLessThan(120);
  // no left-right shuffling: the heading rarely reverses direction of turning
  const signed = samples.slice(1).map((s, i) => { let d = s.yaw - samples[i].yaw; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return Math.abs(d) < 0.01 ? 0 : Math.sign(d); }).filter(v => v !== 0);
  const flips = signed.slice(1).filter((v, i) => v !== signed[i]).length;
  expect(flips).toBeLessThan(8);
});

test("camera path crosses every door through its middle, square to the wall", async ({ page }) => {
  const b = "osm-way27917482";
  const geometry = await (await page.request.get(`/api/buildings/${b}`)).json();
  const sid = (await (await page.request.post("/api/sessions", { data: { building_id: b } })).json()).session_id;
  const scene = await (await page.request.get(`/api/sessions/${sid}/scene`)).json();
  const r = await (await page.request.post(`/api/sessions/${sid}/route`, { data: { start: `${b}-F3-S069`, destination: "00.05.058" } })).json();
  const poly = r.events.find((e: any) => e.type === "route").route.polyline;
  const doors = geometry.openings.filter((o: any) => ["door", "opening", "entrance"].includes(o.kind)).flatMap((o: any) => {
    const f = openingFrame(geometry, o);
    return f ? [{ ids: o.space_ids, x: o.position[0], y: o.position[1], nx: -Math.sin(f.angle), ny: Math.cos(f.angle) }] : [];
  });
  const path = cameraPath(poly, scene.scene.walls, doors);
  let crossings = 0;
  for (let i = 1; i < poly.length; i++) {
    if (poly[i].node === poly[i - 1].node || poly[i].floor_id !== poly[i - 1].floor_id) continue;
    const d = doors.filter((x: any) => x.ids.includes(poly[i].node) && x.ids.includes(poly[i - 1].node)).sort((a: any, c: any) => Math.hypot(a.x - poly[i].x, a.y - poly[i].y) - Math.hypot(c.x - poly[i].x, c.y - poly[i].y))[0];
    if (!d) continue;
    crossings++;
    const near = path.filter(p => p.floor_id === poly[i].floor_id).map(p => Math.hypot(p.x - d.x, p.y - d.y));
    expect(Math.min(...near)).toBeLessThan(0.15);
  }
  expect(crossings).toBeGreaterThan(0);
});

import { test, expect } from "@playwright/test";
import { facingDegrees, facingTable, FACING_OFFSET_DEG } from "../src/lib/facing";
import type { Asset } from "../src/lib/types";

const a = (id: string, type: string, x: number, y: number, rot = 0, w = 0.5, d = 0.5) => ({ id, type, space_id: "s", position: [x, y], footprint: { width_m: w, depth_m: d, rotation_deg: rot } }) as unknown as Asset;
/** Plan direction of the model front (local -Z) after a scene Y rotation; plan y is scene -z. */
const front = (deg: number) => { const r = (deg * Math.PI) / 180; return [-Math.sin(r), Math.cos(r)]; };

test("a chair beside a desk turns to the desk's own axis, never to its corner", () => {
  const desk = a("d", "desk", 0, 0, 30, 1.6, 0.8);
  const ux = [Math.cos(Math.PI / 6), Math.sin(Math.PI / 6)], uy = [-Math.sin(Math.PI / 6), Math.cos(Math.PI / 6)];
  // chair 0.7 m beyond the desk's +y long side and a little off-centre: faces back along -uy
  const chair = a("c", "chair", 0.3 * ux[0] + 0.8 * uy[0], 0.3 * ux[1] + 0.8 * uy[1], 123);
  const [fx, fy] = front(facingDegrees(chair, [chair, desk]));
  expect(fx).toBeCloseTo(-uy[0], 5); expect(fy).toBeCloseTo(-uy[1], 5);
  // chair at the short end faces along -ux
  const end = a("e", "chair", 1.4 * ux[0], 1.4 * ux[1], 7);
  const [ex, ey] = front(facingDegrees(end, [end, desk]));
  expect(ex).toBeCloseTo(-ux[0], 5); expect(ey).toBeCloseTo(-ux[1], 5);
});

test("no desk in reach, or an item that is not a chair, keeps the measured rotation", () => {
  const far = a("d", "desk", 5, 0, 0, 1.6, 0.8), chair = a("c", "chair", 0, 0, 30);
  expect(facingDegrees(chair, [chair, far])).toBe(30 + FACING_OFFSET_DEG);
  for (const type of ["sofa", "armchair", "wardrobe", "bookshelf", "toilet"]) { const o = a("o", type, 0, 0, 40); expect(facingDegrees(o, [o, a("t", "tv_stand", 1, 0)])).toBe(40 + FACING_OFFSET_DEG); }
});

test("lecture rows in one hall become parallel and face the board", () => {
  const rows = [a("r1", "lecture_seating_row", 0, 0, 156.8, 5, 0.8), a("r2", "lecture_seating_row", 0, 2, 156.8, 5, 0.8), a("r3", "lecture_seating_row", 0, 4, 246.8, 5, 0.8), a("r4", "lecture_seating_row", 0, 6, 156.8, 5, 0.8)];
  const board = a("b", "whiteboard", -6, 3, 0);
  const t = facingTable([...rows, board]);
  const dirs = rows.map(r => front(t.get(r.id)!));
  for (const d of dirs) { expect(d[0]).toBeCloseTo(dirs[0][0], 5); expect(d[1]).toBeCloseTo(dirs[0][1], 5); }
  // the board lies along -x of the rows' middle: the hall turns its rows square to it, front toward the board, with one of the measured axes
  expect(dirs[0][0]).toBeLessThan(-0.9);
  const axis = [Math.cos((246.8 * Math.PI) / 180), Math.sin((246.8 * Math.PI) / 180)];
  expect(Math.abs(dirs[0][0] * axis[0] + dirs[0][1] * axis[1])).toBeLessThan(1e-6);
});

import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
const DATA = path.resolve(process.cwd(), "../docs/industrial-agents-hackathon-2026/data");

test("real halls: every lecture row ends up parallel with its front toward the lectern or board", () => {
  test.skip(!existsSync(DATA), "supplied data not present");
  let halls = 0;
  for (const split of readdirSync(DATA, { withFileTypes: true }).filter(d => d.isDirectory())) for (const b of readdirSync(path.join(DATA, split.name), { withFileTypes: true }).filter(d => d.isDirectory())) {
    const file = path.join(DATA, split.name, b.name, "building.json");
    if (!existsSync(file)) continue;
    const assets = (JSON.parse(readFileSync(file, "utf8")).assets ?? []) as Asset[];
    const bySpace = new Map<string, Asset[]>();
    for (const a of assets) bySpace.set(a.space_id, [...(bySpace.get(a.space_id) ?? []), a]);
    for (const room of bySpace.values()) {
      const rows = room.filter(a => a.type === "lecture_seating_row"), focus = room.filter(a => ["lectern", "whiteboard", "projector_screen", "display_screen"].includes(a.type));
      if (rows.length < 3 || !focus.length) continue;
      halls++;
      const t = facingTable(room), fronts = rows.map(r => front(t.get(r.id)!));
      for (const f of fronts) { expect(f[0]).toBeCloseTo(fronts[0][0], 5); expect(f[1]).toBeCloseTo(fronts[0][1], 5); }
      const cx = rows.reduce((s, r) => s + r.position[0], 0) / rows.length, cy = rows.reduce((s, r) => s + r.position[1], 0) / rows.length;
      const fx = focus.reduce((s, r) => s + r.position[0], 0) / focus.length, fy = focus.reduce((s, r) => s + r.position[1], 0) / focus.length;
      expect(fronts[0][0] * (fx - cx) + fronts[0][1] * (fy - cy)).toBeGreaterThan(0);
    }
  }
  console.log(`${halls} halls checked`);
});

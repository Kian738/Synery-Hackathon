import { test, expect } from "@playwright/test";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { getAssetVisual, INTERIOR_MAX_PARTS, KNOWN_ASSET_TYPES, OVERVIEW_MAX_PARTS } from "../src/scene-assets/catalog";
import { contactSheetSvg, partHalfExtents } from "../src/scene-assets/contact-sheet";
import type { Lod } from "../src/scene-assets/parts";

// Pure data tests: no browser, no server. They read the supplied (gitignored, read-only) building files.
const DATA = path.resolve(process.cwd(), "../docs/industrial-agents-hackathon-2026/data");

interface Seen { categories: Set<string>; sizes: [number, number][]; count: number }
function inventory(): Map<string, Seen> {
  const out = new Map<string, Seen>();
  for (const split of readdirSync(DATA, { withFileTypes: true }).filter(d => d.isDirectory())) {
    for (const b of readdirSync(path.join(DATA, split.name), { withFileTypes: true }).filter(d => d.isDirectory())) {
      const file = path.join(DATA, split.name, b.name, "building.json");
      if (!existsSync(file)) continue;
      for (const a of JSON.parse(readFileSync(file, "utf8")).assets ?? []) {
        const s = out.get(a.type) ?? { categories: new Set(), sizes: [], count: 0 };
        s.categories.add(a.category); s.count++;
        if (a.footprint && s.sizes.length < 400) s.sizes.push([a.footprint.width_m, a.footprint.depth_m]);
        out.set(a.type, s);
      }
    }
  }
  return out;
}
const haveData = existsSync(DATA);
const inv = haveData ? inventory() : new Map<string, Seen>();
const median = (v: number[]) => [...v].sort((a, b) => a - b)[Math.floor(v.length / 2)];
const mk = (type: string, w?: number, d?: number, extra: object = {}) => ({ type, ...(w === undefined ? {} : { footprint: { width_m: w, depth_m: d ?? w, rotation_deg: 0 } }), ...extra });
const LODS: Lod[] = ["overview", "interior"];
const HEX = /^#[0-9a-f]{6}$/i;

function footprints(type: string): [number, number][] {
  const s = inv.get(type)?.sizes ?? [];
  if (!s.length) return [[0.5, 0.5], [1, 0.5], [2, 1]];
  const ws = s.map(x => x[0]), ds = s.map(x => x[1]);
  return [[Math.min(...ws), Math.min(...ds)], [median(ws), median(ds)], [Math.max(...ws), Math.max(...ds)], ...s.slice(0, 6)];
}

test.describe("asset catalogue", () => {
  test("covers every supplied asset type, keyed by type rather than category", () => {
    test.skip(!haveData, "supplied building data not present");
    const missing = [...inv.keys()].filter(t => !KNOWN_ASSET_TYPES.includes(t)).sort();
    expect(missing, `types without a visual: ${missing.join(", ")}`).toEqual([]);
    expect(inv.size).toBeGreaterThanOrEqual(90);
    for (const t of inv.keys()) expect(getAssetVisual(mk(t, 1, 1), "interior").fallback, t).toBe(false);
    // washing_machine appears as both equipment and fixture: category must not matter.
    const multi = [...inv].filter(([, s]) => s.categories.size > 1).map(([t]) => t);
    expect(multi.length).toBeGreaterThan(0);
    for (const t of multi) expect(getAssetVisual({ ...mk(t, 0.6), category: "fixture" } as never, "interior")).toEqual(getAssetVisual({ ...mk(t, 0.6), category: "equipment" } as never, "interior"));
  });

  test("every type is finite, non-negative, grounded, inside its footprint and within part budgets", () => {
    const types = haveData ? [...inv.keys()] : [...KNOWN_ASSET_TYPES];
    const issues: string[] = [];
    for (const type of types) for (const [w, d] of footprints(type)) for (const lod of LODS) {
      const v = getAssetVisual(mk(type, w, d), lod);
      const cap = lod === "overview" ? OVERVIEW_MAX_PARTS : INTERIOR_MAX_PARTS;
      const tag = `${type} ${w}x${d} ${lod}`;
      if (!v.parts.length || v.parts.length > cap) issues.push(`${tag}: ${v.parts.length} parts (cap ${cap})`);
      if (v.illustrative !== true) issues.push(`${tag}: not marked illustrative`);
      for (const p of v.parts) {
        const nums = [...p.position, ...p.scale, ...(p.rotation ?? [])];
        if (!nums.every(Number.isFinite)) issues.push(`${tag}: non-finite transform`);
        if (p.scale.some(s => s < 0) || p.scale.some(s => s === 0)) issues.push(`${tag}: degenerate scale ${p.scale}`);
        if (!HEX.test(p.color)) issues.push(`${tag}: bad colour ${p.color}`);
        if (!["box", "cylinder", "sphere"].includes(p.shape)) issues.push(`${tag}: bad shape`);
        const h = partHalfExtents(p, w, d);
        if (p.position[1] - h[1] < -0.001) issues.push(`${tag}: ${p.shape} below the floor`);
        if (p.position[1] + h[1] > 4) issues.push(`${tag}: part reaches ${(p.position[1] + h[1]).toFixed(2)} m`);
        // Ground-contact geometry stays inside the footprint; no documented overhangs exist.
        if (Math.abs(p.position[0]) * w + h[0] > w / 2 + 0.002 || Math.abs(p.position[2]) * d + h[2] > d / 2 + 0.002) issues.push(`${tag}: ${p.shape} leaves the footprint`);
      }
    }
    expect(issues.slice(0, 20)).toEqual([]);
  });

  test("output is deterministic and depends only on type, footprint size and LOD", () => {
    for (const type of ["chair", "microscope", "lab_bench", "internal_stairs", "no_such_type"]) for (const lod of LODS) {
      const a = getAssetVisual(mk(type, 1.2, 0.7), lod);
      const b = getAssetVisual({ ...mk(type, 1.2, 0.7), id: "other", name: "Other", position: [9, 9], space_id: "s", floor_id: "f", category: "machine" } as never, lod);
      expect(JSON.parse(JSON.stringify(b))).toEqual(JSON.parse(JSON.stringify(a)));
      // Rotation and world position are the integrator's job; the local parts must not change with them.
      const rotated = getAssetVisual({ type, footprint: { width_m: 1.2, depth_m: 0.7, rotation_deg: 137 } }, lod);
      expect(rotated).toEqual(a);
    }
    expect(() => { (getAssetVisual(mk("chair", 0.5), "interior").parts as unknown[]).push(1); }).toThrow();
  });

  test("unknown future types get a visibly generic fallback without an invented identity", () => {
    for (const type of ["quantum_widget", "", "CHAIR_OF_DOOM", "chair_lift"]) {
      const v = getAssetVisual(mk(type, 1, 0.6), "interior");
      expect(v.fallback, type).toBe(true);
      expect(v.family).toBe("generic");
      expect(v.illustrative).toBe(true);
      expect(v.parts.length).toBeGreaterThan(0);
    }
    // Type names are matched exactly (case/space insensitive), never by substring.
    expect(getAssetVisual(mk("Lab Bench", 3, 0.8), "interior").fallback).toBe(false);
    expect(getAssetVisual(mk("chair_lift", 1, 1), "overview").family).toBe("generic");
    // The fallback does not borrow another type's silhouette.
    const fallback = JSON.stringify(getAssetVisual(mk("mystery", 1, 1), "interior").parts);
    for (const t of KNOWN_ASSET_TYPES) expect(JSON.stringify(getAssetVisual(mk(t, 1, 1), "interior").parts), t).not.toBe(fallback);
    // Category alone never decides identity.
    expect(getAssetVisual({ ...mk("mystery", 1, 1), category: "machine" } as never, "interior").fallback).toBe(true);
  });

  test("missing, tiny, invalid and huge footprints still produce usable parts", () => {
    const bad: (object | undefined)[] = [
      undefined, null as never, {}, { width_m: 0, depth_m: 0 }, { width_m: -3, depth_m: 2 }, { width_m: Number.NaN, depth_m: Infinity },
      { width_m: 0.001, depth_m: 0.001 }, { width_m: 0.06, depth_m: 3.4 }, { width_m: 5.2, depth_m: 0.15 }, { width_m: 1e6, depth_m: 1e6 },
    ];
    for (const type of KNOWN_ASSET_TYPES) for (const fp of bad) for (const lod of LODS) {
      const v = getAssetVisual({ type, footprint: fp as never }, lod);
      expect(v.parts.length, `${type} ${JSON.stringify(fp)} ${lod}`).toBeGreaterThan(0);
      expect(v.parts.length).toBeLessThanOrEqual(lod === "overview" ? OVERVIEW_MAX_PARTS : INTERIOR_MAX_PARTS);
      for (const p of v.parts) expect([...p.position, ...p.scale].every(Number.isFinite), `${type} ${JSON.stringify(fp)}`).toBe(true);
    }
    expect(getAssetVisual({ type: "chair" } as never, "interior")).toEqual(getAssetVisual(mk("chair", 0.5, 0.5), "interior"));
  });

  test("silhouettes are varied rather than boxes with different heights", () => {
    const sig = (type: string) => JSON.stringify(getAssetVisual(mk(type, 1, 1), "interior").parts.map(p => [p.shape, p.position, p.scale, p.rotation]));
    const families = new Set<string>();
    const bySig = new Map<string, string>();
    for (const t of KNOWN_ASSET_TYPES) {
      const f = getAssetVisual(mk(t, 1, 1), "interior").family, s = sig(t);
      families.add(f);
      expect(bySig.get(s) ?? f, `${t} reuses the geometry of a different family`).toBe(f);
      bySig.set(s, f);
    }
    expect(families.size).toBeGreaterThanOrEqual(60);
    const priority = ["oscilloscope_station", "microscope", "lab_bench", "fume_hood", "printer", "3d_printer", "industrial_3d_printer", "multifunction_printer", "projector", "projector_screen", "fire_extinguisher", "eyewash_station", "defibrillator", "cnc_lathe", "cnc_mill", "milling_machine", "drill_press", "press_brake", "chair", "office_chair", "desk", "toilet", "sink", "bathtub", "shower", "bookshelf", "pallet_rack", "bed", "single_bed", "sofa", "plant"];
    for (const t of priority) {
      const parts = getAssetVisual(mk(t, ...(inv.get(t) ? [median(inv.get(t)!.sizes.map(s => s[0])), median(inv.get(t)!.sizes.map(s => s[1]))] : [1, 0.6])), "interior").parts;
      expect(parts.length, t).toBeGreaterThanOrEqual(4);
      expect(new Set(parts.map(p => p.color)).size, `${t} colours`).toBeGreaterThanOrEqual(2);
    }
    // Round things are round.
    for (const t of ["plant", "boiler", "fire_extinguisher", "eyewash_station", "compressor", "waste_basket"]) expect(getAssetVisual(mk(t, 0.6), "overview").parts.some(p => p.shape !== "box"), t).toBe(true);
  });

  test("overview LOD is never richer than interior LOD and stays small for common types", () => {
    for (const t of KNOWN_ASSET_TYPES) {
      const o = getAssetVisual(mk(t, 1, 0.8), "overview").parts.length, i = getAssetVisual(mk(t, 1, 0.8), "interior").parts.length;
      expect(o, t).toBeLessThanOrEqual(i);
    }
    for (const t of ["chair", "dining_chair", "office_chair", "desk", "plant", "nightstand", "bed"]) expect(getAssetVisual(mk(t, 0.8, 0.8), "overview").parts.length, t).toBeLessThanOrEqual(5);
    if (inv.size) { // average per instance over the real inventory
      let parts = 0, assets = 0;
      for (const [t, s] of inv) { parts += getAssetVisual(mk(t, ...footprintMedian(s)), "overview").parts.length * s.count; assets += s.count; }
      expect(parts / assets, "mean overview parts per supplied asset").toBeLessThan(5);
    }
  });

  test("honest geometry: stairs follow their footprint and elongated vehicles use the long axis", () => {
    const stairs = getAssetVisual(mk("internal_stairs", 1.35, 3), "interior").parts;
    expect(stairs.length).toBeGreaterThanOrEqual(6);
    const tops = stairs.filter(p => p.shape === "box").map(p => p.position[1] + p.scale[1] / 2);
    expect(Math.max(...tops)).toBeLessThan(2.4);
    const fork = getAssetVisual(mk("forklift", 2.5, 1.2), "interior").parts;
    expect(Math.min(...fork.map(p => p.position[0] - p.scale[0] / 2))).toBeLessThan(-0.45); // forks reach the -X end
    // Wall/ceiling-mounted items declare no ground contact, so they need no support to stay in bounds.
    expect(getAssetVisual(mk("projector", 0.4, 0.3), "interior").parts.every(p => p.position[1] > 1.5)).toBe(true);
  });

  test("optional contact sheet", () => {
    const out = process.env.ASSET_CONTACT_SHEET;
    test.skip(!out, "set ASSET_CONTACT_SHEET=<file.svg> to write the review sheet");
    const items = KNOWN_ASSET_TYPES.map(type => { const [w, d] = footprintMedian(inv.get(type)); return { type, width: w, depth: d }; });
    writeFileSync(out!, contactSheetSvg(items, { columns: 6, cell: 130 }));
  });
});

function footprintMedian(s?: Seen): [number, number] {
  return s?.sizes.length ? [median(s.sizes.map(x => x[0])), median(s.sizes.map(x => x[1]))] : [0.6, 0.6];
}

// Deterministic procedural visual catalogue for supplied asset types.
// Pure data: no three.js, no textures, no network. See docs/parallel/assets-handoff.md for the integration contract.
import type { Asset } from "../lib/types";
import * as F from "./families";
import { separateCoplanar } from "./zfight";
import { PALETTE as P, PartBuilder, type AssetPart, type AssetVisual, type Lod } from "./parts";

export type { AssetPart, AssetVisual, Lod } from "./parts";
export const OVERVIEW_MAX_PARTS = 8;
export const INTERIOR_MAX_PARTS = 48;
/** Footprint assumed when the supplied one is missing or unusable (matches the existing renderer default). */
export const DEFAULT_FOOTPRINT_M = 0.5;

type AssetInput = Pick<Asset, "type"> & { footprint?: Partial<NonNullable<Asset["footprint"]>> | null };

interface Entry { family: string; build: F.Build }
const e = (family: string, build: F.Build): Entry => ({ family, build });

const BOOKS = ["#8a4f4f", "#4f6f8a", "#c2a85a", "#5f8a6b", "#7d6a9a"];
const PAPER = ["#e4e9e8", "#cfd7d6", "#e8e2cf"];
const GOODS = ["#b99363", "#9a7a52", "#cfd7d6"];

const TABLE = (h: number, o: Omit<NonNullable<Parameters<typeof F.table>[0]>, "h"> = {}) => F.table({ h, ...o });

const ENTRIES: Record<string, Entry> = {
  // seating
  chair: e("chair", F.chair()),
  dining_chair: e("chair", F.chair({ color: P.wood, leg: P.woodDark, back: 0.9 })),
  outdoor_chair: e("chair", F.chair({ color: P.metal, leg: P.metalDark, arms: true })),
  office_chair: e("office-chair", F.officeChair()),
  armchair: e("armchair", F.armchair()),
  sofa: e("sofa", F.sofa()),
  lecture_seating_row: e("lecture-seating", F.lectureSeatingRow()),
  bench: e("bench", TABLE(0.45, { style: "panels", top: P.wood, leg: P.metalDark, topT: 0.05 })),
  // beds
  bed: e("bed", F.bed(false)),
  single_bed: e("bed", F.bed(true)),
  // tables and desks
  desk: e("desk", F.desk()),
  meeting_table: e("table", TABLE(0.74, { style: "panels", top: P.laminate, inset: 0.15 })),
  seminar_table: e("table", TABLE(0.74, { style: "legs", top: P.laminate })),
  canteen_table: e("table", TABLE(0.75, { style: "legs", top: P.laminate })),
  dining_table: e("table", TABLE(0.75, { style: "legs", top: P.wood, leg: P.woodDark })),
  reading_table: e("table", TABLE(0.75, { style: "legs", top: P.wood, leg: P.woodDark })),
  coffee_table: e("table", TABLE(0.42, { style: "legs", top: P.woodDark, leg: P.black })),
  outdoor_table: e("table", TABLE(0.74, { style: "pedestal", top: P.metal, leg: P.metalDark })),
  workbench: e("workbench", F.workbench()),
  inspection_bench: e("workbench", F.workbench({ steel: true })),
  assembly_station: e("workbench", F.workbench({ assembly: true })),
  packing_station: e("workbench", F.workbench({ packing: true })),
  lab_bench: e("lab-bench", F.labBench()),
  reception_desk: e("reception-desk", F.receptionDesk()),
  kitchen_counter: e("counter", F.counter({ kitchen: true })),
  serving_counter: e("counter", F.counter({ serving: true, h: 0.9 })),
  lectern: e("lectern", F.lectern()),
  // storage
  bookshelf: e("bookshelf", F.bookshelf({ h: 1.8, levels: 5, color: P.woodDark, fills: BOOKS })),
  shelf: e("shelf", F.bookshelf({ h: 1.6, levels: 4, color: P.metal, fills: GOODS, posts: true })),
  paper_shelf: e("shelf", F.bookshelf({ h: 1.6, levels: 4, color: P.wood, fills: PAPER })),
  pallet_rack: e("pallet-rack", F.palletRack()),
  filing_cabinet: e("cabinet", F.cabinet({ h: 1.3, body: P.metal, front: P.steel, rows: 4, handle: P.black })),
  locker: e("locker", F.cabinet({ h: 1.8, body: P.metalDark, front: P.steel, cols: 3, handle: P.black, vents: true })),
  wardrobe: e("wardrobe", F.cabinet({ h: 2.0, body: P.woodDark, front: P.wood, cols: 2, handle: P.steel, plinth: true })),
  built_in_wardrobe: e("wardrobe", F.cabinet({ h: 2.4, body: P.offWhite, front: P.white, cols: 3, handle: P.steel })),
  shoe_cabinet: e("cabinet", F.cabinet({ h: 1.0, body: P.woodDark, front: P.wood, rows: 3, handle: P.steel, plinth: true })),
  tool_cabinet: e("cabinet", F.cabinet({ h: 0.95, body: P.red, front: "#a63a34", rows: 5, handle: P.steelLight, top: P.metal, wheels: true })),
  chemical_cabinet: e("safety-cabinet", F.cabinet({ h: 1.9, body: P.yellow, front: "#e6c850", cols: 2, handle: P.black, plinth: true, band: P.black })),
  nightstand: e("cabinet", F.cabinet({ h: 0.5, body: P.woodDark, front: P.wood, rows: 2, handle: P.steel, top: P.woodDark })),
  tv_stand: e("cabinet", F.cabinet({ h: 0.45, body: P.woodDark, front: P.wood, cols: 2, handle: P.steel, plinth: true })),
  coat_rack: e("coat-rack", F.coatRack()),
  waste_basket: e("bin", F.wasteBasket()),
  plant: e("plant", F.plant()),
  // kitchen and office appliances
  fridge: e("fridge", F.fridge()),
  dishwasher: e("dishwasher", F.dishwasher()),
  stove: e("stove", F.stove()),
  microwave: e("microwave", F.microwave()),
  coffee_machine: e("coffee-machine", F.coffeeMachine()),
  water_dispenser: e("water-dispenser", F.waterDispenser()),
  vending_machine: e("vending-machine", F.vendingMachine()),
  atm: e("atm", F.atm()),
  washing_machine: e("washing-machine", F.washingMachine()),
  printer: e("printer", F.printer()),
  multifunction_printer: e("copier", F.multifunctionPrinter()),
  "3d_printer": e("3d-printer", F.printer3d()),
  industrial_3d_printer: e("3d-printer-large", F.industrialPrinter3d()),
  // lab and electronics
  oscilloscope_station: e("oscilloscope", F.oscilloscopeStation()),
  microscope: e("microscope", F.microscope()),
  fume_hood: e("fume-hood", F.fumeHood()),
  soldering_station: e("soldering-station", F.solderingStation()),
  server_rack: e("server-rack", F.serverRack()),
  ups_unit: e("ups", F.upsUnit()),
  electrical_panel: e("electrical-panel", F.electricalPanel()),
  // safety
  fire_extinguisher: e("fire-extinguisher", F.fireExtinguisher()),
  defibrillator: e("defibrillator", F.defibrillator()),
  eyewash_station: e("eyewash", F.eyewashStation()),
  hand_dryer: e("hand-dryer", F.handDryer()),
  // display and projection
  projector: e("projector", F.projector()),
  projector_screen: e("projector-screen", F.projectorScreen()),
  display_screen: e("display", F.displayScreen()),
  whiteboard: e("whiteboard", F.whiteboard()),
  // sanitary
  toilet: e("toilet", F.toilet()),
  sink: e("sink", F.sink()),
  bathtub: e("bathtub", F.bathtub()),
  shower: e("shower", F.shower()),
  // stairs
  internal_stairs: e("stairs", F.stairs()),
  // machines and workshop
  cnc_lathe: e("cnc-lathe", F.cncLathe()),
  cnc_mill: e("cnc-mill", F.cncMill()),
  milling_machine: e("milling-machine", F.millingMachine()),
  drill_press: e("drill-press", F.drillPress()),
  press_brake: e("press-brake", F.pressBrake()),
  laser_cutter: e("laser-cutter", F.laserCutter()),
  waterjet_cutter: e("waterjet", F.waterjetCutter()),
  injection_moulding_machine: e("injection-moulding", F.injectionMouldingMachine()),
  robot_cell: e("robot-cell", F.robotCell()),
  conveyor: e("conveyor", F.conveyor()),
  forklift: e("forklift", F.forklift()),
  pallet_jack: e("pallet-jack", F.palletJack()),
  forklift_charging_station: e("charging-station", F.forkliftChargingStation()),
  compressor: e("compressor", F.compressor()),
  boiler: e("boiler", F.boiler()),
  hvac_unit: e("hvac", F.hvacUnit()),
  curing_oven: e("oven", F.curingOven()),
  powder_station: e("powder-booth", F.powderStation()),
  welding_station: e("welding-booth", F.weldingStation()),
  coordinate_measuring_machine: e("cmm", F.coordinateMeasuringMachine()),
};

const GENERIC: Entry = { family: "generic", build: F.genericBlock() };

/** Every type the catalogue draws specifically, in stable order. */
export const KNOWN_ASSET_TYPES: readonly string[] = Object.freeze(Object.keys(ENTRIES).sort());

const normalize = (t: unknown) => (typeof t === "string" ? t.trim().toLowerCase().replace(/[\s-]+/g, "_") : "");
const isKnown = (t: string) => Object.prototype.hasOwnProperty.call(ENTRIES, t);

const dimension = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.min(Math.max(v, 0.05), 60) : DEFAULT_FOOTPRINT_M);

const cache = new Map<string, AssetVisual>();
const CACHE_LIMIT = 4000;

const freeze = (v: AssetVisual): AssetVisual => {
  v.parts.forEach(p => { Object.freeze(p.position); Object.freeze(p.scale); if (p.rotation) Object.freeze(p.rotation); Object.freeze(p); });
  Object.freeze(v.parts);
  return Object.freeze(v);
};

/**
 * Parts for one asset. Output depends only on the normalized type, the footprint width/depth and the LOD, so equal
 * inputs return the same frozen object (safe to share across thousands of instances). Never mutate the result.
 */
export function getAssetVisual(asset: AssetInput, lod: Lod): AssetVisual {
  const type = normalize(asset.type);
  const w = dimension(asset.footprint?.width_m), d = dimension(asset.footprint?.depth_m);
  const key = `${type}|${w}|${d}|${lod}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const known = isKnown(type);
  const entry = known ? ENTRIES[type] : GENERIC;
  const b = new PartBuilder(w, d, lod === "interior");
  entry.build(b);
  if (!b.parts.length) b.box(0, 0, 0, w, 0.5, d, P.generic);
  const visual = freeze({ family: entry.family, illustrative: true, fallback: !known, parts: separateCoplanar(b.parts, w, d) });
  if (cache.size >= CACHE_LIMIT) cache.clear();
  cache.set(key, visual);
  return visual;
}

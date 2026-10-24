# Package A: asset visual catalogue — READY

Status: **READY** for Codex to integrate. No file outside the owned paths was edited; `Building3D.tsx` was only read.

## Files

| Path | Role |
|---|---|
| `web/src/scene-assets/catalog.ts` | public API: `getAssetVisual`, `KNOWN_ASSET_TYPES`, part budgets |
| `web/src/scene-assets/parts.ts` | `AssetPart` / `AssetVisual` / `Lod` types, palette, metre-based `PartBuilder` (clips ground geometry to the footprint) |
| `web/src/scene-assets/families.ts` | the silhouettes (builders shared across the 96 types) |
| `web/src/scene-assets/contact-sheet.ts` | dependency-free SVG review sheet (not imported by the app) |
| `web/src/scene-assets/contact-sheet.png` | rendered sheet: all 96 types, overview and interior side by side (811 KB; regenerate, do not hand-edit) |
| `web/tests/asset-catalog.spec.ts` | 9 data tests; no browser or server needed |

No new dependencies, textures, network assets or generated images.

## Interface

```ts
import { getAssetVisual, KNOWN_ASSET_TYPES, OVERVIEW_MAX_PARTS, INTERIOR_MAX_PARTS } from "../scene-assets/catalog";

getAssetVisual(asset: Pick<Asset,"type"> & { footprint?: … }, lod: "overview" | "interior")
  : { family: string; illustrative: true; fallback: boolean; parts: AssetPart[] }

AssetPart = { shape: "box" | "cylinder" | "sphere"; position: [x,y,z]; scale: [x,y,z]; color: string; rotation?: [x,y,z] }
```

Two deviations from the brief, both deliberate:

- The brief says to import `Asset` from `../../lib/types`. From `web/src/scene-assets/` that path does not exist; the real module is `web/src/lib/types.ts`, so `catalog.ts` uses `import type { Asset } from "../lib/types"`. The parameter is `Pick<Asset,"type">` plus an optional footprint, so a full `Asset` is accepted and tests can pass small objects.
- The result is **frozen and shared**: equal (type, width, depth, lod) inputs return the same object (cache of 4000 entries, cleared when full). Never mutate it. This makes 85k instances cheap to resolve (a full pass over all 280 buildings takes about 0.5 s including JSON parsing).

### Coordinate convention (exactly as briefed)

- Origin: footprint centre on the floor. Y up. Forward / operator / access side is local **-Z**; backs and wall sides are +Z.
- `position.x/z` and `scale.x/z` are **fractions of the supplied width/depth**. `position.y` and `scale.y` are **illustrative metres**. `position` is the part centre; `scale` is the full size.
- Unit shapes: box side 1; cylinder diameter 1, height 1, axis Y (`scale.x`/`scale.z` are the two diameters); sphere diameter 1.
- Rotations are radians, three.js Euler order XYZ, applied about the part centre **before** translation and **after** scale. Only a few parts rotate: lying cylinders (`rotation: [0,0,π/2]` along X, `[π/2,0,0]` along Z), the microscope tube, robot arm segments, the lectern top, the ATM keypad and the multifunction-printer panel.
- Per part, in world space:

```ts
// asset: position [x, y] metres, footprint {width_m: w, depth_m: d, rotation_deg}; part from getAssetVisual
parent.position.set(asset.position[0], elevation, -asset.position[1]);
parent.rotation.set(0, THREE.MathUtils.degToRad(rotation_deg), 0);            // same as the current FurnitureBatch
local.position.set(part.position[0] * w, part.position[1], part.position[2] * d);
local.rotation.set(...(part.rotation ?? [0, 0, 0]));
local.scale.set(part.scale[0] * w, part.scale[1], part.scale[2] * d);
matrix = parent.matrix * local.matrix;   // then setMatrixAt on the instanced mesh for part.shape
```

Use `w = footprint.width_m` and `d = footprint.depth_m` exactly as supplied. If a footprint is missing the catalogue authored the parts for 0.5 x 0.5 m (the renderer default), so use 0.5 for both there too. The catalogue clamps authoring dimensions to 0.05 to 60 m, but because X/Z values are fractions the parts still fit the real footprint when it is tinier or larger.

### Instanced rendering

Keep three `InstancedMesh`es, one per shape (`boxGeometry`, `cylinderGeometry(0.5, 0.5, 1, 12)`, `sphereGeometry(0.5, 10, 8)`), sized by summing part counts per shape across the visible assets. In the full inventory the overview LOD yields 290,212 box / 36,102 cylinder / 3,594 sphere parts across 85,703 assets, so a typical floor is a few thousand instances. Colour is per part (`setColorAt`); the existing highlight and muted tinting (`lerp`) works unchanged. Choose the LOD per floor or per distance: `overview` for the cutaway view, `interior` for the eye-level view and for highlighted assets.

## What it covers

- All **96 asset types** in the supplied data (train, dev and test buildings, 85,703 assets). Types are keyed by `type`; category (`furniture`, `equipment`, `fixture`, `machine`) is never used. One type, `washing_machine`, appears under two categories and renders identically for both.
- Recognizable silhouettes were prioritised: oscilloscope station (bench plus scope, screen, knobs), microscope (stand, arm, tilted tube, stage, objectives), lab bench (worktop, cabinets, reagent riser), fume hood (sash frame, header, duct), printers, copier, 3D printers (frame, build plate, gantry), projector (ceiling mount), projector screen, whiteboard, display on a stand, fire extinguisher, eyewash station, defibrillator case, CNC lathe/mill, knee mill, drill press, press brake, waterjet, injection moulder, robot cell with arm and fence, chairs (plain, dining, office swivel, armchair), tables, desks with drawer pedestal, toilet, sink (one basin per about 0.7 m), bathtub, shower frame, bookshelves with books, steel shelving, pallet rack, beds with pillows, sofas with cushions, plants, vending machine, ATM, fridge, stove with hobs, and so on. See `contact-sheet.png`.
- Part counts, whole inventory, measured: overview mean **3.85** (max 8), interior mean **8.77** (max 26). Budgets enforced by tests: overview <= 8, interior <= 48. Overview keeps the top-down footprint and silhouette; interior adds legs, handles, drawers, screens, books and so on.
- `family` is the silhouette family (for example `chair`, `desk`, `cnc-lathe`), not the category. Several types share a family with different colours or proportions (`chair`, `dining_chair`, `outdoor_chair`).

## Fallback behaviour

Any type not in `KNOWN_ASSET_TYPES` (after trimming, lowercasing and turning spaces or dashes into `_`) returns `family: "generic"`, `fallback: true`: a low violet-grey plinth with a lighter cap and no domain detail. There is no substring or fuzzy matching (`chair_lift` is not a chair) and category is ignored, so the catalogue never fabricates an identity. Consider showing the raw `asset.type` in the tooltip when `fallback` is true.

## Assumptions the integrator should know

1. **Source rotation semantics are unverified.** The catalogue is authored in a local frame with forward -Z. In plan coordinates (Y north, three Z = -Y) that is north at `rotation_deg = 0`. I did not verify against the data that the dataset's zero rotation means "faces plan-north"; if it does not, only the Y rotation offset in the integrator needs a constant.
2. **Long-axis vehicles:** `forklift` and `pallet_jack` are long in X (their supplied footprints are 2.5 x 1.2 and 1.6 x 0.7); forks point to **-X** rather than -Z.
3. **Ground contact stays inside the footprint for every part.** No documented overhangs: `PartBuilder` clips boxes and shrinks cylinders and spheres, and the test measures rotated parts' bounds too. A few items are intentionally **not floor-supported** because they are wall or ceiling items with only a floor-plan point: `projector` (hung at about 2.1 to 2.6 m, mount plate included), `projector_screen` (0.9 to 2.4 m), `whiteboard`, `defibrillator`, `hand_dryer`, `electrical_panel`. Projector height assumes rooms are at least about 2.7 m high; the supplied data does not record mounting heights.
4. **Tabletop items stand on a slim pedestal** (microscope, printer, 3D printer, microwave, coffee machine) because the data gives a floor position, not a work surface. The pedestal is a generic support, not a claim that furniture exists there.
5. Dimensions in Y (door, table, cabinet heights) are typical illustrative values, not measurements. `illustrative: true` is always set; do not present these as surveyed objects. Stairs rise toward +Z with an assumed 0.17 m riser; the dataset does not record the up direction. STATUS.md already states that supplied stair assets are illustrative.
6. Colours are tuned for the dark navigator scene (see `PALETTE`); they are fixed hex strings, so theming changes need an edit in `parts.ts`.

## Checks run

- `npx playwright test tests/asset-catalog.spec.ts`: 9/9 per project (the contact-sheet test is skipped unless `ASSET_CONTACT_SHEET=<file.svg>` is set; 16 passed, 2 skipped across desktop and phone).
- `npx tsc --noEmit -p web`: clean (checked while Codex's concurrent edits were in the tree).
- Tests cover: coverage of the real supplied inventory (every type, none via fallback; category-independence); finite, positive, grounded, hex-coloured parts inside footprint with rotation-aware bounds across min/median/max and sampled real footprints for every type and both LODs; part budgets; determinism and independence from id, name, position, category and `rotation_deg`; frozen output; exact-match fallback (no substring identity, no borrowed silhouette); missing, zero, negative, NaN, infinite, 0.001 m, 3.4 m and 1e6 m footprints; family-level geometry duplication (no copy-paste silhouettes); minimum detail for the priority types; overview never richer than interior; mean overview parts per real asset below 5. There are no snapshot tests of the geometry.
- Reproduce the review sheet: `cd web && ASSET_CONTACT_SHEET=sheet.svg npx playwright test tests/asset-catalog.spec.ts --project=desktop`, then open the SVG in a browser or screenshot it (the committed PNG was made this way).
- `uv run fw check` was run once at the end of the session; results are in the combined summary in `docs/parallel/benchmark-handoff.md`.

## Limitations

- Procedural, low-poly and generic: these are recognisable categories, not models of the real equipment. No brand, model or condition is implied.
- Part geometry was reviewed visually on the contact sheet only; it has not been rendered inside the live scene with lighting, post-processing or the highlight tint. Expect small tweaks to colours once seen in context.
- The two-LOD design has no distance blending. Switching LOD per floor is cheap; switching per instance needs separate instanced meshes for each LOD.
- The footprint-bounds test samples at most 400 supplied footprints per type (plus min/median/max of those); the part-count statistics above cover all 85,703 assets.

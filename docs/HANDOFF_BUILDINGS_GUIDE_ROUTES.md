# Handout: buildings, Guide me, and "route not found" bugs

For whoever picks up the 3D/route correctness work while the UI redesign continues elsewhere. Read `AGENTS.md` first (rules, commands), then this file.
State when written: branch `codex/verified-building-demo`, commit `5e2a244`, all offline gates green (routes 2130/2130, solver 655/655, rules 661/661, walls 160/160, edits 72/72, differential 256/256; sunday 1329/1338 and e2e_basic 2122/2130 = diagnosed ambiguous questions in `eval/known_issues.json`).
Do not touch the UI layout/kit (`web/src/ui/`, `Navigator.tsx` chrome): another person is redoing it. Everything below lives in 3D, scene compile, camera, routing and tests.

## 0. Set up in five minutes
- `cd web && npm install && npx vite build` (serves from `web/dist`), then from the repo root `uv run uvicorn server.app:app --port 8000` (Windows: stop with `taskkill //F //FI "IMAGENAME eq uvicorn.exe"`). Open `http://localhost:8000/?building=<id>`.
- Useful URLs: `?building=osm-way27917482` (TUM CIT, 5 floors, the stress building), `proc-campus-test-013`, `swiss-460`, `swiss-921`, `swiss-1785`, `proc-factory-dev-003`; `&at=<space id>&to=<name>` opens a route directly (example: `?building=osm-way27917482&at=osm-way27917482-F3-S069&to=00.05.058`).
- Python checks: `uv run python -m pytest -q`; gates: `uv run python -m eval gates` (needs a clean, committed tree or the source-integrity check aborts); single suites: `uv run python -m eval.walls --split dev`, `eval.rules`, `eval.edits`, `eval.orientation`.
- Browser checks: `cd web && FLOORWISE_URL=http://127.0.0.1:8000 npx playwright test tests/<spec> --project=desktop`. Key specs: `focus-guide.spec.ts`, `camera-quality.spec.ts`, `asset-catalog.spec.ts`, `perf.spec.ts`, `ui-kit.spec.ts`.
- Rule that bit us repeatedly: a passing data attribute is not proof that it looks right. Screenshot it (Playwright MCP or `page.screenshot`) and look. Several "fixed" items below were only verified numerically.

## 1. Where things live
| Concern | Files |
|---|---|
| Route model (kit v1.1.0 rules, exact lengths) | `floorwise/core/graph.py`, `spacewalk.py`, `routing.py`, `docs/REQUIREMENTS.md` |
| Drawn walking line (taut string, furniture) | `floorwise/core/walk.py`, `walk_domain.py` |
| Step text | `floorwise/core/instructions.py` |
| Scene compile (walls, headers, roofs, slabs, stair shafts and plates) | `floorwise/core/scene.py`, `stair_scene.py` |
| 3D scene | `web/src/components/Building3D.tsx` (floors, walls, doors, camera, focus, detail LOD), `Connectors3D.tsx` (stairs, `stairBoxes`, `stairWalkLine`), `LiftShafts.tsx`, `Ceilings.tsx`, `SceneAssets.tsx`, `scene-assets/` (models) |
| Guide me camera | `web/src/lib/cameraPath.ts` (path), `lib/playback.ts` (timing, auto speed), `RouteCamera` inside `Building3D.tsx` (lens, heading, ride) |
| Focus/dimming, shaft voids | `web/src/lib/focus.ts` |
| Audits | `eval/walls.py`, `eval/orientation.py`, `tests/test_stair_plates.py`, `tests/test_stair_shaft_containment.py`, `web/tests/camera-quality.spec.ts` |

## 2. Issue area A: buildings (3D correctness)
Known, with what is verified and what is not.
1. **Stairs.**
   - swiss data types stair spaces as `corridor`, so floor plates stayed inside flights. Fixed for display by `compile_stair_plates` (cuts the flight footprint out of the arrival floor's plates; proven for ~40 buildings by `tests/test_stair_plates.py`). Spot-checked by eye on swiss-460 floor 2 only.
   - Many flights are withheld by `stair_scene.py` because no safe footprint exists (swiss-921: 9 of 10; swiss-460: the ground-to-floor-2 flight). Open question: draw a smaller honest flight, a landing block, or a labelled "stairs (not modelled)" marker instead of nothing. The user perceives nothing as "broken".
   - **swiss-460 has no level 1** (floors at levels 0, 2, 3, 4; elevations 0/6/9/12 m): the user's "basement broken" report is probably this gap. `Connectors3D` draws two storeys for a 6 m rise; check it looks sane and the floor rail does not imply a missing floor.
   - CIT earlier had a dark "trench" and floating wall pieces around stair shafts, and flights not meeting the upper landing. Re-check on CIT after any stair change; a user screenshot showed them.
   - Flights are Codex's code (`stair_scene.py`, `stairBoxes`): `git log -p` them before editing and keep the footprint-containment tests green.
2. **Floor missing in TUM 4107** (user screenshot, not reproduced). Plan: add a browser data attribute `data-floor-coverage` (drawn plate area vs union of space polygons minus stair/lift voids) and a test over 20 buildings. Suspects: `shaftVoids` (lift/stair spaces typed wrongly on the lowest stop), the focus filter `relevant`, `bare` floors in Guide me, plates with an unexpected hole.
3. **Lifts.** Landing doors, hollow car and travel animation exist (`LiftShafts.tsx`) but door open/close and the car moving are NOT verified by eye; the user saw doubled doors (data opening frame + our leaves + car face). Frames on lift/stair openings are suppressed in `Doorways`; check lifts mapped into corridor-typed spaces.
4. **Ceilings/roofs.** Rule: a ceiling where a floor lies above, a roof where nothing is above. `scene.roofs` are drawn in Guide me only (`Ceilings.tsx`); gaps between rooms and the overview toggle are open.
5. **Z-fighting / wall ends.** Duplicate wall edges are now drawn once; log depth buffer is on; look again at wall ends and doorway lintels in swiss-1785 and CIT.
6. **Models.** Orientation is calibrated from data (`FACING_OFFSET_DEG = 180`, `eval.orientation`). Re-check in the real scene: toilet/sink/vending machine/kitchen counter after the flip, `scene-assets/families.ts` contact sheet (`ASSET_CONTACT_SHEET=<file.svg> npx playwright test tests/asset-catalog.spec.ts -g "contact sheet"`, serve the svg and screenshot it). Part budgets are enforced by `asset-catalog.spec.ts`.
7. **Data oddities.** 8 residual "route crosses a wall" cases (resplan/swiss) in `eval.walls` (99.2 %, threshold 0.98): inspect before assuming a code bug.
8. **Performance** (done, keep it): CIT whole building was 15 M triangles, now ~0.4 M (far detail uses plain boxes; rounded geometry only near the orbit target). budgets are pinned in `perf.spec.ts`. Do not re-add per-instance heavy geometry or shadows for far objects.

## 3. Issue area B: Guide me
What exists: the camera path is its own line (not the drawn route): resampled, centred, string-pulled to straight runs, rounded corners, forced through every door midpoint square to the wall (`cameraPath.ts`). Heading is eased and limited to 80 degrees/s. The walking lens (near 0.05, FOV 70) is set in `RouteCamera` because the `Canvas` reads camera props only once (this caused the "clips into everything" bug: near plane was 0.66 m). Auto speed is always on (slow near doors, turns, stairs; fast on long clear stretches). Stairs are walked along `stairWalkLine`; lifts move the car with the camera (`rideState`).
Open and reported by the user:
1. **Stair ride view.** Numerically the camera descends smoothly inside the shaft (`focus-guide.spec.ts` "walks down the real stair flights"), but screenshots mid-ride showed plain walls or black. Debug interactively: add a `?debug=camera` overlay (camera path, stair walk line, distance to nearest wall) and look at pitch, shaft walls and voids at the ride start. The walk line may start 0.4 m outside the flight.
2. **Walking through walls / jagged lines.** `camera-quality.spec.ts` (35 routes, 6 buildings) shows 0 crossings and 0.26 m minimum clearance, yet the user still reported glitches at some doors and starts. Extend it to many more routes (all 280 buildings, 10 routes each), including routes that start or end inside tiny rooms, doorways at an angle, and lift/stair legs; fail on clearance < 0.3 m for more than a few frames.
3. **Camera starts facing a wall** in small rooms: pull the start back along the path and hold the first 0.6 s.
4. **Lift ride** looks plain; the car arriving, doors opening, camera entering is not choreographed.
5. **Focus**: Guide me has its own focus toggle (default off = whole building drawn); the plan is to keep "whole building" for recognition and make focus one click.
6. Player: the end-of-route edge case was fixed (`arrived` has a 0.011 s tolerance); Finish and chapter markers need a final check on phone widths.

## 4. Issue area C: routes that "obviously exist" but are not found
Verified facts first.
- The reported case "No route from Eingang Nord (Ground floor) to Corridor 3.400 (Floor 3) (closed: osm-way27917482-F0-S026)": the route exists (65.47 m). `osm-way27917482-F0-S026` is `MI Magistrale`, the CIT main corridor; closing it cuts the wings apart (`tests/test_edit_capabilities.py::test_closing_a_bridge_corridor...`). The UI only closes lifts/stairs, so the closure came through chat (`set_closed`). The UI now asks before a stranding closure, offers Undo, and the notice offers "Reopen". Still open: find out which user action closed it (chat transcript?), and whether a stale session or an LLM misreading ("X is closed" as an instruction) is to blame.
- Other legitimate "no route" reasons by design (Synery rules, `docs/REQUIREMENTS.md`): two parts that only meet outside have no route (no outside hop); step-free removes stairs and non-step-free openings; forklift needs openings of 3 m or more and non-bay aisles; production bays are destinations only; closed spaces are impassable. Check each before calling it a bug.
Method for a new report:
1. Reproduce through the API with explicit ids, not names: `POST /api/sessions {building_id}` then `POST /api/sessions/{id}/route {start, destination}`; compare with `plan_route(building, [a, b], Constraints())` in Python.
2. Print the active constraints (`Session.constraints()`, `Session.closed`, step-free flag, profile minimum door width). A leftover closure or profile width is the usual cause.
3. If it fails with no constraints: run the kit's own router (`eval/judge.py` `kit_map`, or `eval.differential`) on the same pair; our graph equals the kit's on all 280 buildings, so a failure there is a data fact, not a bug.
4. If the ids work but a name fails: it is resolution, not routing (`floorwise/core/resolve.py`, `agent/parse_rules.py`, ambiguous names such as "Büro"; `eval.roundtrip` and `eval.generated` catch these).
5. Add the case to `tests/` (or `eval/known_issues.json` only if it is genuinely unanswerable) so it cannot return.
Ideas worth doing: a diagnostic endpoint/tool `why_no_route(a, b)` that tests each constraint removal in turn and reports the single one that makes the route exist (closure X, step-free, door width); show that sentence instead of the bare "No route".

## 5. Definition of done / etiquette
- Each fix: a failing test or audit first, the fix, the audit green on all buildings (not only the one in the screenshot), before/after screenshots attached to the PR/commit message, `docs/BACKLOG.md` updated with what was verified by eye and what was not.
- Never regress: `eval gates` (clean tree), `uv run python -m pytest -q`, the Playwright list in `AGENTS.md` rule 12.
- Commit small, push the branch, no force-push, no new branches without asking. Windows: write scripts to files instead of long heredocs; `taskkill` for servers.
- Do not change route lengths or the `Answer:` line format: the benchmark scores them.

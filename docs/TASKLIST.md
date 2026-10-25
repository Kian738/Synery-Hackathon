# Task list

One place to see what is done, what is next and how each item is checked. Update it in the same commit as the work. Details and history live in `docs/BACKLOG.md` (open items) and `docs/STATUS.md` (evidence).

Status: `done` (verified), `open`, `partial` (works, a part is not verified by eye or on a device), `blocked`.

## Order of work (agreed 2026-10-25)
| # | Task | Status | Check |
|---|---|---|---|
| 0 | Task list, Markdown and repo cleanup | done | old audits and handoffs moved to `docs/archive/`; build junk untracked; dead functions removed |
| 1a | Z-fighting in the 90 procedural models | done | `web/tests/zfight.spec.ts` (coplanar face audit, 218 offenders found, 0 after the 3 mm recess in `scene-assets/zfight.ts`) |
| 1b | Orientation: wall-backed items | done | `eval.orientation --types all`: desks, wardrobes, sofas, fridges, shelves 97-100 % front at the wall. Toilet, sink, counter, bath stay 49-59 % (the nearest wall is often a cubicle partition: the metric is ambiguous, not the model) |
| 1c | Orientation: seating | done | dataset chair rotation carries no signal (19-22 % at every offset, `eval.orientation --relational`), so seating faces the nearest table or screen (`lib/facing.ts`, `web/tests/facing.spec.ts`) |
| 1d | Z-fighting at scene level (floors, ghost floors, plates, doorway sills, wall tops, lift leaves) | open | needs a flicker check by eye on swiss-1785, CIT, a factory from 6 angles; polygon offsets exist on floors and slabs |
| 2 | Routes not found where places look connected | partial | `eval.connectivity`: 53/280 buildings have rooms cut off, 25 had the default entrance in a small side part. Fixed: default start in the largest part (`tests/test_default_start.py`), "separate parts" explanation with nearest reachable place (`tests/test_disconnection.py`). Open: add the missing doors where a wall gap < 0.5 m (data decision), obvious-stair cases per building |
| 3 | Graphical stair bugs and Guide me | open | withheld flights (swiss-921), swiss-460 level gap, CIT trench, stair ride view, lift choreography |
| 4 | Voice with ElevenLabs | partial | `server/voice.py` proxy (TTS cached + char budget, STT), `lib/voice.ts` falls back to browser voice; tests `test_voice.py`, `voice.spec.ts` with stubbed server. Needs `ELEVENLABS_API_KEY` in `.env`; real audio and latency NOT verified (no key here) |
| 5 | Testing | open | one `scripts/verify_all` run, visual baselines, flaky-test hunt, coverage |

## Status 2026-10-25 (after the hotfix round)
| Task | Status | Evidence |
|---|---|---|
| Model z-fight guard, reworked (details keep faces, bodies step back 2.2 mm together, capped at 15 mm) | done | `zfight.spec.ts` 0 offenders + reshape cap; contact sheet read |
| Wall-backed items turn square to their wall when the measured back is off it; chairs snap to a desk axis within 0.7 m; lecture rows keep measured rotation | done | `lib/facing.ts`, `facing.spec.ts`, 3 types excluded by measurement |
| Floor overlap stripes: shared part drawn as a blend of both room colours | done | `scene.overlaps`, `eval.overlaps` (41 buildings), `test_scene_overlaps.py`, CIT screenshot |
| C: map opens whole building, route focuses itself, Find/Share/Save removed, icons told apart | done | `flow-c.spec.ts`, icon test in `test_instruction_style.py` |
| D: Guide me card (headline, target, distance cue, next preview), spoken form distance-first | done | step fields in `core/instructions.py`, tests, desktop + phone screenshots |
| B: loader, small model details | done | screenshot of loader; catalogue tests |
| Lift car back z-fight | partial | car now clear of walls by construction; not looked at from behind in the app |
| Testing phase (gold bank, journeys, audit, rigour) | in progress | `eval.gold` (phrasing robustness), `eval.audit_all`, `normalize.py` |
| Scope: This floor / Whole building + "Route only" modifier; route turns it on, map opens whole building | done | `flow-c.spec.ts`, `focus-guide.spec.ts` |
| Guide me: ahead-card with live metre countdown, stair ride joins real entry/exit and keeps 0.47 m off walls, look-around by drag, thicker line | done | `focus-guide.spec.ts` (walls clearance test), screenshots |
| Open-air bridges/stairs: 1.1 m fences, no roof; overlap walls and wide-opening walls dropped; fewer withheld walking previews (92 to 35 of 1681) | done | `test_scene_rails.py`, `withheld` audit script numbers in commit message |
| Route planning speed: A* inside a room, rails once per space | done | CIT cold 10.5 s to 3.5 s; gates unchanged |
| Editing: add a door between X and Y by name, once per pair, placed clear of furniture and corners, undo exact, edit flashes the rooms | done | `tests/test_door_e2e.py` (5 buildings), `test_edit_capabilities.py` |
| Request activity bar (named status + stopwatch) | done | `lib/activity.ts`, `ActivityBar.tsx`; no skeleton cards yet |
| Journeys, axe a11y, properties on 280 buildings, gold bank in gates | done | `journeys.spec.ts`, `a11y.spec.ts`, `test_properties.py`, `eval.gold` |
| E phone HTTPS | partial | `scripts/phone_https.ps1` + PHONE_DEMO.md; no physical phone tried |
| Scenario research | done | `docs/SCENARIO_RESEARCH.md` (existing `floorwise/evacuation` min-cost-flow found; gap = per-person queue simulator on RouteGraph, door ranking, heat maps) |
| G Evacuation stress test: per-person queue simulation on the navigation graph (SFPE door flow, pre-movement, speeds), bottleneck + crowding KPIs, door and new-exit ideas proved by a second run, panel with time scrubber, density heat map on the floors, queue pins | done | `floorwise/stress/`, `server/stress.py`, `tests/test_stress_sim.py` (door flow ~0.92 p/s per metre, doubling), `test_stress_api.py`, `web/tests/stress.spec.ts`; 2D plan heat map and 6 more scenario presets not done |
| F VR in Guide me (WebXR rig, gaze panel, trigger plays), installable app (manifest, icons), safe areas | partial | builds and non-VR specs pass; **not tried on a headset or a phone**; bottom-sheet snap points not built |
| Gates 2026-10-25 | done | all 16 offline gates + 2 gold gates green (routes 2130/2130, e2e_basic 2122/2130 known, gold 3755/3755 + holdout 1530/1530) |
| Videogame mode on PC (WASD + mouse look on the VR scene) | open | later, as agreed |

## Older open items
- TUM 4107 missing floor (`data-floor-coverage` test), loading animation, whole building as default view, left panel declutter.
- Lab and phone companion on the control kit; entity chips with "Show all N on map"; per-call tool timeline.
- Lift door open/close and car travel checked by eye; real AR on a device; live LLM scoring (no API key here).
- Gates: `eval gates` aborts with "Edit check failed" when files change during the run (source-integrity). Run it on a clean, committed tree.

## Cleanup candidates not done yet
- Dead CSS in `web/src/styles.css`: `.model-toolbar`, `.mode-switch`, `.scene-navigation`, `.stage-toggle` (no component uses them; the rules are mixed into live media queries, so remove with a screenshot pass).
- `cameraPolyline` in `web/src/lib/focus.ts` is only used by one test (the camera uses `lib/cameraPath.ts`).
- `docs/parallel/*` are code-referenced contracts (phone, assets, benchmark): keep. `scenario-handoff.md` and `codex-third-pass-handoff.md` can be archived once their links are fixed.
- `SUBMISSION/BENCHMARK.md` duplicates `BENCHMARK.md`: keep both, add an equality test.

## Stairs analysis 2026-10-25
- 464 flights had no safe footprint in 87 buildings; a relaxed second fit (4 cm clearance, 0.8 x 1.1 m) brings it to 350 in 79. The rest (139 storey pairs: 114 with no overlap at all, 25 under 0.8 m2) are stair spaces on consecutive floors that do not stand above each other in the data (centroids up to 15 m apart), so no honest flight exists; they keep the stair icon and a glide. val.audit_all lists them.
- Ride measured by web/tests/stair-ride.spec.ts in 6 buildings: eye inside the stair space, 0.28 m off walls, feet within the stair's height range, no jumps.


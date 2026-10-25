# Backlog

## Next up: review of 2026-10-24 (everything asked for that is not done yet)

The route-rule change from Synera (kit 1.1.0) took priority, so these are written down instead of half done. Status: **todo** = nobody has started; **codex** = the other agent's working tree already contains a start (RoomText, roomMentions, floor-slab tests); check `git status` before touching the same files.

### Benchmarks and evaluation
- **todo**: independent oracles for the geometry kinds (largest room, area totals, shared walls, stacking, 3D distance) written from the README definitions, compared on all buildings; today they are verified against gold (655/655) and metamorphic invariance only.
- **todo**: wording robustness beyond perturbations: run the paraphrase and LLM-parser suites on Claude again with the new rule fields (forklift, bays, closed places, avoid) and add rule-bearing question variants to `robust`.
- **todo**: confirm the five open interpretations in `docs/REQUIREMENTS.md` with Synera on site (without stairs, forklift aisle, production bay, rules on errands/tours, answer format on Sunday); then promote them from "assumed" to "verified".
- **todo**: run `generated` and `rules` on the whole of train, dev and test nightly (about 15 minutes) and chart the trend in the Lab.
- **todo**: Lab: show known versus unexplained misses and the known-issues evidence next to each run.

### Chat and AI engineering
- **codex**: room, floor and item mentions in chat replies become links that highlight and select them (`RoomText.tsx`, `roomMentions.ts`).
- **todo**: tool calls shown properly again (name, arguments in plain words, result summary, errors) in the chat transcript.
- **todo**: select several components (for example "5 3D printers") and highlight exactly those in the 3D view and the plan, from chat and from the scene, with a list that mirrors the selection.
- **todo**: chat intelligence pass: use the deterministic dispatcher for everything it can answer, ask back only on real ambiguity, say what was understood, keep answers short with links, and add an eval for each of these behaviours.

### Rendering and look
- **todo**: stairs, lifts and connector interiors drawn at their real sizes (footprints and floor heights from the data) instead of illustrative blocks.
- **codex**: roofs and ceilings where there should be none (TUM CIT atrium), z-fighting and flicker between floor slabs, coplanar walls.
- **todo**: colour language for navigation: one colour per room kind (bathrooms, kitchens, labs, offices, stairs and lifts, production bays) used in the plan, the 3D floor tint, chips and chat links, always paired with an icon and a word; accessible in light and dark.
- **todo**: use the extra data we have (room type, area, assets, door widths, step-free) as additional senses: sound cues for floor changes, haptics on the phone, and a legend that explains the colours.
- **todo**: something other projects do not have: a "what changes if" visual (closure ghost routes, door-width what-if heat) as a first-class 3D view, and an evidence atlas as a hero screen.

### UX consistency
- **todo**: guide player controls (the 2x / 4x speed menu): replace the native dropdown (white text on white background in legacy Chrome) with the same segmented control used elsewhere; one component set for all buttons, selects and chips.
- **todo**: audit light and dark mode on every screen with screenshots at 1440 and 390 px, and fix tokens so no control depends on browser defaults.

# Later work: positioning, AR and others

Ordered by value for the jury and by effort. Sources are in `reports/Indoor wayfinding agent UX.md`, section 5.

## Knowing where the user is

| Approach | Accuracy | Works in a browser? | Effort | Verdict |
|---|---|---|---|---|
| **QR code at doors and entrances** (`?at=<space id>`) | exact, at the scan | yes, on every phone | hours; deep links already work | **do first** |
| Tap "I'm here" on the plan / start picker | exact | yes | done | done |
| **BLE beacons** (trilateration on signal strength) | 2–5 m | Chrome on Android only, behind a flag; never on iOS Safari | days, plus hardware | native app only |
| **WiFi RTT / fingerprinting** | RTT 1–2 m; fingerprinting 3–5 m | **no**: browsers expose no WiFi scans; iOS apps can't read WiFi signal strength | survey per building | native Android app only |
| Visual positioning (camera matches a prior scan: MultiSet, Immersal) | under 0.1 m | MultiSet WebXR, Android only | needs the building scanned first | for a pilot site |
| Pedestrian dead reckoning (phone motion sensors) | drifts a few % of distance | yes (DeviceMotion) | medium | only to carry position between QR scans |
| Visual-inertial "SLAM" | very good locally, drifts globally | provided by ARCore/ARKit inside WebXR on Android | comes with AR | use it between QR scans |

**The honest answer to "BLE and WiFi SLAM":** a web app can't see WiFi networks at all, and Bluetooth scanning only works experimentally on Android Chrome. Both need beacons or a site survey per building. In the browser, the realistic stack is:

1. a QR scan at a door, which gives an exact position;
2. ARCore's own motion tracking, which follows the phone between scans;
3. another QR scan when the route passes a door, to correct drift.

BLE and WiFi are for a native-app phase with the site owner, who installs the beacons and does the survey.

## AR route overlay

The base is in place: `web/src/components/Building3D.tsx` renders the building in metres (x east, y up, z = −north). An AR session places that same scene at the scanned door.

1. **Android Chrome:** WebXR `immersive-ar` with `local-floor`, a hit-test and a DOM overlay.
   - When the session starts, align the plan with the QR door's position and the wall direction.
   - Draw floor chevrons every metre along the route, plus a destination pin.
   - Ask for a re-scan when tracking is lost.
2. **iPhone:** iOS Safari has no WebXR `immersive-ar`. Fall back to the 2D plan with a compass arrow (DeviceOrientation), or use an App Clip (e.g. Needle Go) later.
3. **UX:** AR only at decision points ("raise the phone at the junction"), never for walking with the phone held up (research: less spatial memory, battery drain).

## Other items

- **Several buildings:** join `building.json` files with outdoor walkway edges between their entrances (graph change only).
- **Live map updates:** "this machine is now in 0.21" works through `move_item`. Barcode or RFID input could call the same endpoint.
- **Forklift / wide loads:** min door width and step-free are in place. Add aisle blocking per hall zone (close a space or opening) from the UI.
- **Floor plans from real scans:** Raster2Seq (MIT, CubiCasa5K checkpoint) as a fallback for non-generated plans, on a Linux GPU, timeboxed.
- **Voice:** server-side ElevenLabs TTS, or Groq Whisper for speech-to-text, to replace the browser APIs.
- **Lovable:** the code you were given (`COMM-INDUSTRIAL-QHYD`) looks like a credit/promo code, not an API key. Redeem it on lovable.dev. Lovable then works on this repo through GitHub sync: prompt in Lovable, then pull. It uses the same stack (Vite + React + Tailwind).


## Current implementation audit (25 October)

Supersedes earlier todo labels where they conflict: normal chat is Claude-first; token-free dispatch is not the product policy. Streaming and result reopening are implemented and covered by offline transport/UI contracts. Speed choices are visible segmented buttons (0.5×/1×/2×/4×). Tools groups secondary controls, including explicit-input scenarios. The Lab tracks raw scores and historical evidence rather than a guessed overall grade.

Still open: refresh every critical live case after the final integration, complete three graded uninterrupted rehearsals, independent general-polygon wall/stacking oracles beyond gold/hand cases, general plan import quality, physical phone/audio/projector validation, and three unfamiliar teammate trials. These must not be marked done from a backend-only test or a different source fingerprint. See TESTING_GUIDE.md for the exact profiles and challenge prompts.

## Consolidated UI review

See UX_AUDIT_50_AND_EXPLORATION.md for the fifty repair entries and twenty contextual additions. The concurrent focus-camera prototype was rejected: moving a camera away from the validated walking path and interpolating between unverified landing coordinates does not establish collision-safe navigation. Its source is preserved locally under runs/gemini-review. General exterior views require genuine OSM references. Physical phone tests and browser visual acceptance remain open; earlier checklist entries must not imply these passed.

Update 2026-10-25 (later): also done: stairs and lifts that share a space (swiss-921: lift + stairs mapped into one corridor) get separate
compact fixtures (`slotSpace`), only real stair/lift spaces lose their floor plate, a daylight rig with soft shadows and fog
(`SceneLighting.tsx`), edit tools with undo (see STATUS). Still open: UI buttons for undo/remove-door, floor identity colour,
chat one-line response summary, walk-up-the-flight camera.

## 2026-10-25 UI pass 3 (done) and open list

Done: hidden rooms in focus mode are drawn as dim footprints and the pill says "N other rooms dimmed" with a "Show all rooms" button (hiding used to look like a bug);
Guide me draws the whole building; floor identity colour (`lib/floorColors.ts`: wall outlines in 3D and the rail dots); toilet, sink, shower rebuilt; stairs/lifts fitted inside
their room outline, landing at the door; lifts no longer draw a second door; duplicate walls drawn once (z-fighting); Guide me camera keeps 45 cm from walls, wider view, larger near plane;
chat surface restyled (rounded composer, pill chips, bubble for the user); scope control and Tools popover restyled; page zoom disabled.

Open, in priority order:
1. **Testing (next focus):** frozen-snapshot gate run (the shared tree trips the source-integrity check); visual regression screenshots for 3D models (contact sheet exists, no baseline); Guide me
   stair walk-through on real buildings; chat history test `chat stays usable through multiple replies` fails (history shows 1 of 2 turns: conversation grouping logic, not CSS); phone viewport runs of the new controls.
2. **Whole UI design pass:** one component kit (buttons, pills, popovers, panels), tokens for radius/spacing/colour, dark/light parity, Lab and phone companion on the same kit.
3. Chat redesign proper: one-line response summary, tool timings behind a click, streaming without layout jumps (layout fixed; real streaming not exercised without an API key).
4. Undo / remove-door buttons in the UI (backend, REST and chat tools exist).
5. More model polish: kitchen counter, stove, fridge, beds, wardrobes; check every footprint orientation (toilet tank beside the bowl in some buildings = asset rotation).
6. Guide me: camera follows the real stair flight (now a smooth glide between landings); lift ride with car animation.
7. Several buildings linked by walkways (data has single buildings).

Update 2026-10-25 (lifts): `LiftShafts.tsx`: one animated car per lift travels (3.2 m/s) to the floor being looked at; landing doors are shut unless the car is on that floor and slide open on arrival.
No door frames are drawn on stairwell openings. Test: `tests/focus-guide.spec.ts` (car travels, passes through intermediate heights). Not verified by eye: the door leaves opening/closing.
Still open: lift ride in Guide me should move the car with the camera; stair flights cut through some oddly shaped stair spaces (another agent edits `stairBoxes`, re-check after merge).

## Master list of everything asked in the 2026-10-25 UI sessions (status as of this edit)

Colours and identity
- [done] Room-type colours (`roomKinds.ts`), corridors white, no standing legend.
- [done] Floor identity colour: wall outlines in 3D and the floor-rail dots (`floorColors.ts`).
- [open] Floor colour also on the plan view and on the guide player chapter markers.
- [open] Tooltip / on-demand key that names a room type colour (no space-taking legend).

Focus / clarity
- [done] Focus mode (route rooms + doors within 5 m), dimmed ghost footprints for the rest, pill "N other rooms dimmed - Show all rooms".
- [done] Guide me draws the whole building. [open] Optional "dim the rest" toggle inside Guide me.
- [open] Make hidden-room state obvious on the floor plan and in the exploded view too.
- [done] Scope control (This floor / Route floors / Whole building / Spread) out of the Tools dropdown.

Stairs, lifts, doors
- [done] Stairs and lifts at real size, fitted inside their room, landing at the door, no door frames on stairwell openings.
- [done] Lift car per lift travels to the viewed floor; landing doors shut unless the car is there.
- [in progress] Lift looks: doubled doors (landing leaves + car door + wall frame), car visibility while moving.
- [open] Stair flights in odd-shaped or very long shafts (CIT): clean flights, no trench, no floating wall pieces; one owner for `stairBoxes` (another agent edits it too).
- [open] Lift car moves with the camera during a Guide me ride; stairs walked step by step.

Guide me
- [done] Camera 45 cm off walls, wider view, larger near plane, smooth glide between floors.
- [open] Camera too close at doorways/start; pull the start back and look along the route; no clipping through wall ends.
- [open] Player restyle finished (done: round buttons, speed segments); check phone layout.

3D models
- [done] Rounded edges, AO gradient, detailed LOD below 2500 items per floor, chair, toilet, sink, shower rebuilt.
- [open] Kitchen counter, stove, fridge, beds, wardrobes, sofas; check orientation (toilet tank beside bowl = rotated asset).
- [open] Visual regression baselines (contact sheet) for every type.

UI system
- [open] Whole-UI design pass: one component kit (buttons, pills, popovers, panels), radius/spacing/colour tokens, dark/light parity, Lab and phone on the same kit.
- [open] Chat redesign proper (one-line response summary, tool timings behind a click, no layout jump while streaming).
- [done] Page cannot scroll past the app; page zoom disabled.
- [open] Undo / remove-door buttons in the UI.

Testing (next focus)
- [open] Frozen-snapshot gate run (shared tree trips the source-integrity check).
- [open] Failing: `chat stays usable through multiple replies` (history shows 1 of 2 turns).
- [open] Browser tests for lift doors open/close, guide stair walk, focus pill on phone, colour identity.
- [open] Edit-agent paths through the live LLM (needs API key): add/remove door, add/remove/move item, undo.

Update 2026-10-25 (camera path, closures):
- [done] Guide me camera uses its own path (`cameraPolyline`): resampled, centred in corridors and doorways, smoothed, 45 cm off walls. The drawn route stays the shortest one and stays visible.
- [done] "No route ... (closed: ...)" was a real closure (the main corridor `MI Magistrale` was closed in the session, the route itself is 65 m). A red "Closed: <name> - Reopen" chip now shows whenever anything is closed.
- [done] Guide player end-of-route edge case (slider max rounding stopped playback 0.005 s short of "arrived").
- [open] Guide me player/viewer REWRITE (layout, controls, chapters, captions, phone) as one component kit piece; current player is a restyle only.
- [open] Walk DOWN/UP the real stair flight in Guide me (camera follows the flight, pitch from tread slope); today it glides straight between landings.
- [open] Error copy for "no route": name the closed place and offer Reopen inside the message, not only the chip.
- [open] Closures leaking in unnoticed: ask before closing a corridor from a room tap; show an undo toast.

## Reported by the user, NOT fixed or NOT verified by the user (2026-10-25, last prompts)
(Everything I called "done" above that the user has not confirmed is unverified; the items below are known broken.)
1. Stair model looks wrong / terribly buggy (odd ramps, trench, floating walls, flights through odd-shaped shafts; in CIT and others).
2. Lift doors look doubled and do not close when the car is elsewhere (the wooden opening frame plus our steel leaves plus data openings; my change only removed frames on lift-typed spaces, lifts mapped into corridors keep them).
3. Lift car does not visibly animate when switching floors or during a Guide me ride.
4. Guide me walks through walls, glitches into the elevator; the camera still follows jagged lines and swings left/right; wants a straight, centred line.
5. Ceilings missing where a floor exists above (rule: a ceiling/roof exists exactly when there is a floor above that spot).
6. Stairs and lifts rendered per building: clipping out of walls/bounds.
7. Guide me: walk down/up the real stair flight; Guide me player rewrite.
8. Whole-UI design unification; chat redesign proper; model quality for kitchen/shower/etc.; z-clipping at wall ends.
9. Testing: frozen gates; visual baselines; lift door open/close test; guide stair walk test.

## 2026-10-25 plan execution, step 1 and part of 4 (what changed, what is verified)
Changed (verified by tests, and by screenshots only where noted):
- Guide me camera path rebuilt (`lib/cameraPath.ts`): resample, centre, string-pull to long straight runs, rounded corners. Unit test: a zigzag route becomes <3 turns. Verified by test.
- Camera heading: average look-ahead, eased and limited to 80 deg/s; no per-frame wall pushing. Playwright test (real-time playback): max yaw rate < 120 deg/s, few left/right reversals. Verified by test, NOT judged by the user.
- Guide me now draws the whole building (other floors without furniture); before, only the current floor existed and descending showed a black void. Seen in screenshots.
- The full-screen "Changing floors" card hid the ride; it is a small caption now. Seen in screenshot.
- Ride is kept inside the stair/lift shaft outline. NOT seen working: my screenshots of the ride show a plain wall/slab, so the stairs may still not be visible during the ride.
- Roofs from `scene.roofs` are drawn in Guide me (were not rendered at all). Not verified by eye in a building with a missing-roof case.
Still open from the plan (not done): lift doors at the opening plane / doubled doors / car animation visibility (step 2); stair geometry rewrite (step 3); ceiling gaps between rooms and overview ceiling toggle (step 4); cramped starts (camera starts 0.4 m from a wall in small rooms; needs a pulled-back start); step 5 items.

## 2026-10-25 later: door-aware camera, lift ride, notices
Done: camera path passes every door through its midpoint, square to the wall, with straight lead-in/out (`cameraPath` + `Door`); test `camera path crosses every door through its middle`. "Reopen closed places" button inside the no-route notice (the closure on `MI Magistrale` is session state set from the UI; nothing closes it automatically; who closed it is unknown). Guide me lift ride: the car rises with the camera (`rideState`), landing doors follow it. Button language: toolbar, notices, player Finish share radii (pill/10 px).
Seen: a stair ride at CIT t=13 s renders amber treads; overview stairs render. The user reported stairs "not rendered at all" in Guide me: not reproduced, may be a stale build or Codex's in-progress stair work (Codex owns stairs).
Not verified by eye: lift ride in Guide me (car + camera together), door passing in a long playback, Finish button look.
Open: camera still starts ~0.4 m from a wall in small rooms; stair ride start looks at a plain slab for ~1 s; whole-UI uniformity (many more buttons use older styles: Lab, phone companion, plan view).

## 2026-10-25 UI kit rebuild (phases 1-3 partly, 4 started)
Done and tested (`ui-kit.spec.ts`, desktop + phone): kit tokens and primitives; stage chrome as four docks; Layers and Tools popovers; floor rail compact/expanding with floor colours and route ring; focus-on-route toggle also in Guide me and the camera now applies it there; closed places listed in Layers with Reopen (badge on the button); chat panel Step-free / Read aloud / chips / primary button on the same control class; page zoom blocked (test updated); phone layout: icon-only top bar, rail on the right.
Updated tests for the new controls: navigator, product, visual-workspace, demo capture, review-third-pass (whole building now drawn in Guide me).
Open from the plan: Guide me walking the real stair flight (Codex owns stairs; needs `stairWalkLine`); camera start still faces a wall in tiny rooms; floor rail count badges (matches per floor); remaining screens not on the kit (Lab, phone companion, plan view controls, ExploreTools, ScenarioPanel, dialogs, composer mic/send); `!important` patch blocks still in styles.css for the guide player/notices; chat-history test still failing (grouping logic); lift/door/ceiling items above.

## 2026-10-25 integration pass (branch codex/verified-building-demo; origin/master merged)
Merged: team PRs #9-#16 (scenario engine, exit limits, responder route, sensitivity). Policy kept: plan_scenario needs explicit occupants and a passage rate; master's scenario tests were updated to supply them. Master's navigator/ScenarioPanel (live replay with guided beats) is NOT ported onto Codex's components/ScenarioPanel: open item "port the live replay and guided beats".
Done since the plan: auto-speed Guide me with toggle; Guide me focus default off; plan-view preview arrow carries the walking heading; stair walk line (tested numerically); item orientation fixed from data (eval.orientation); hollow lift cars; richer sofa/bed/toilet; building menu popover, compact header, conversation chrome and composer on the kit; camera path quality test (35 routes, 0 wall crossings, min clearance 0.26 m: the backend camera path planned for Phase 1 was not needed).
Unverified or wrong (see the user's reports): the view during a stair ride shows plain walls and black in my screenshots even though the camera positions are inside the stairwell: needs interactive debugging (suspects: wall/floor-void drawing around the shaft, pitch); stairs inside corridor-typed spaces in swiss/resplan buildings (white flights in corridors, floor plate inside the flight: needs `stair_scene` voids cut from the upper floor plate); toilet/sink/vending-machine models in the real scene (contact sheet looks fine, scene render not re-checked after the 180 degree fix); lift door open/close by eye; plan-view preview arrow by eye; compact layout at 1280x720; "Expand building view" only collapses the chat panel to its input bar (works, label could be clearer); master push not done on purpose (only this branch is pushed).

## 2026-10-25 later session (camera lens, atlas, directions, AR, scenarios)
Done and tested: Guide me lens (near 0.05, fov 70, restored on exit; the Canvas reads camera props once, so the walking camera sets its own lens in `RouteCamera`); route focus default (multi-floor routes open as Route floors, session-remembered); clearer step wording + Now/Next route card (`tests/test_instruction_style.py`); Building Atlas with generated isometric thumbnails (`server/thumb.py`, `tests/test_building_thumbs.py`, `web/tests/atlas.spec.ts`); phone AR overlay helpers, route path in the companion protocol (server-validated), `ArRoute` session, compass turn arrow (`web/tests/ar.spec.ts`, `tests/test_companion.py`); plan view uses room-kind colours and a floor-colour frame; scenario invariants (`tests/test_scenario_invariants.py`).
Gates on the merged tree before these changes: routes 2130/2130, solver 655/655, parsers 100 %, e2e 653/655, e2e_basic 2122/2130, sunday 1329/1338 (diagnosed), generated 150/150, rules 661/661, roundtrip 236/236, walls 160/160, edits 72/72, robust 630/630, metamorphic 860/860, walkability 160/160, differential 256/256. `origin/master` was not benchmarked separately: it is an ancestor of this branch (merged), and the merged tree is at least as good on every gate this branch had.
Unverified / not done: real AR on a device (no Android phone here: only geometry and feature detection are tested); VR preview walk (not started); the stair ride is only checked numerically and in two screenshots; ScenarioPanel live replay port; per-call tool timeline in chat; entity chips with multi-select; corridor-typed stair voids; "Show all N on map"; Lab and companion kit sweep (companion still uses its own CSS); live LLM scoring (no API key).

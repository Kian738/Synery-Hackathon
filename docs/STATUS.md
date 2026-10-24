# Status: what works, what is untested, what is missing

Last updated: 2026-10-25 (cognitive-load audit and submission release checks). **verified** = measured by an eval or test in this repo; **live-tested** = ran against a real LLM; **untested** = written but never run; **missing** = not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | find items and rooms by name, type, number | verified | `e2e_basic` locate 553/553, count 239/239 |
| 1 Locate | show them on a view | verified | complete visual events, linked views and desktop/phone regression tests |
| 2 Route | shortest route, step-free, closures, tours | verified against kit 1.1.0 | `routes` 2130/2130 to the cm, every `space_path` and `element_path` identical; `differential` graph-equal to the kit on all 280 buildings |
| 2 Route | avoid X and Y, soft avoid, no stairs/lifts, min door width | verified in unit tests | `tests/test_core.py`; no gold exists |
| 2 Route | drawn routes (inside rooms, taut string around furniture, no entrance hop) | validated | 3 of 216 walked dev pairs withheld; furniture-blocked doors drawn as the official walk and flagged (see the kit 1.1.0 section below) |
| 3 Scale | multi-floor (stairs, lifts) | verified | `routes`, `solver` |
| 3 Scale | several buildings linked by walkways | **missing** | data has single buildings |
| 4 Build | rebuild from plan images | partial; latest strict dev check passes 22/122 floors | room recall 0.938, matched IoU 0.940, door recall 0.817, floor-only exit-connected share 0.304; assisted true-bound calibration, not a predicted jury score |
| 4 Build | scale without a scale bar | user gives one width; **door-width estimate missing** | |
| 4 Build | room names from images | vision labeller **untested** (Claude only; Groq models here have no vision) | |
| 4 Edit | add door (preview → apply), close/reopen, move item | verified (session tests); preview/undo UI partial | |
| 5 Extend | voice in/out | browser speech only; Groq Whisper/Orpheus available, not wired | |
| 5 Extend | 3D building view (rooms, walls, furniture by type, route across floors) | done (`Building3D.tsx`), base for AR |
| 5 Extend | AR, BLE/WiFi positioning | **missing**: see `docs/BACKLOG.md` (QR + WebXR on Android first; BLE/WiFi need a native app) | |

## Benchmark

| Item | Status |
|---|---|
| 9 benchmark kinds | verified: kit evaluator dev 138/138; train+dev 653/655 (2 = 9-way duplicate name "Büro") |
| test submission | `submissions/team_floorwise_test.csv`, 145/145 parsed by rules, 0 fallbacks |
| Sunday command | `fw bench` / `run_benchmark`, CSV or JSON (route node IDs, lengths). The Sunday file format is not yet announced; the adapter is flexible |
| unknown wording | LLM parser fallback: **Claude Haiku 39/40** (< 1 cent), Groq 36/40 |
| unknown question kinds | chat agent fallback, live on Groq; not evaluated |

## Interaction (25 %)

| Item | Status |
|---|---|
| chat agent with tools | live-tested on Groq and Claude; five Claude route/closure repetitions verified |
| flaws seen before the protocol fixes | asked back when both matches were in the same room; skipped `remember_person`. Both are fixed: the ask-gate is in `Session.place`, and the prompt was rewritten |
| research-backed behaviour | done: nearest-match ask-gate, answer-first header (prompt + UI route sign), landmark chunking and floor-change steps (`instructions.py`), spoken overview of 4 parts or fewer, step mode with next/repeat/back |
| live check (Groq, via web SSE) | wheelchair + location → `remember_person`, nearest toilet without asking, header line, 2 steps, alternative mentioned |
| interaction suite on Groq | 7 of 8 scenarios score 4.7–5.0; the judge is a lenient open model |
| interaction suite on Claude (partial: 4 of 8 conversations before the machine ran low on memory and the run was stopped) | first_day 4.5, wheelchair 3.8, technician 4.3, facility_manager 4.2. Real findings, all fixed since: totals did not match the step distances (now walking metres); newcomers were shown room codes (now: assume the main entrance, describe by kind); "keep it short" ignored (now max 3 one-line steps); the judge could not see tool results (now in the transcript). **Re-run needed** |

## UI

| Item | Status |
|---|---|
| Navigator (rebuilt) | signage design; categories; tap a room for "Go here" / "I'm here"; route sign + steps; step mode; voice; closures from the room card; deep links `?at=&to=&step_free=1` |
| Benchmark Lab `/lab` | overview with CIs and trends, launch any suite with live logs, runs list, drill-down (question, expected, reply, trace, places and route on the plan), compare runs, dataset browser |
| Playwright UI tests | 18/18 (desktop 1440 px + phone 390 px), `fw ui-test` |
| Lab front page | inspection sheet: every check in plain words, target vs result, pass/fail, cost, run button, "see failures" |
| UX audit fixes | start defaults to the main entrance (one-tap categories), start picker, floors in their own column, map key on demand, labels sized in screen pixels, examples built from the building's data |
| Playwright | 28/28 (14 flows × desktop + phone) |
| not yet ported to the new UI | draft import is now ported, with source reference overlay and explicit confirmation |

## Known risks

1. Sunday format is unknown, and question kinds outside our 15 families have unknown quality.
2. Claude state checks and sampled transcript review now exist; hardware voice and uncoached on-site usability are still unverified.
3. Building from scanned (non-generated) plans is weak.


## Verified building demo: milestone 1

- Profile-aware closure impact verified: factory Office lift reports general 0 cut off, step-free 29/56, and reopening reconnects 29.
- Door-width repair verified on campus print room: O0015, 0.9 to 1.1 m, preview does not mutate; apply restores graph connectivity. This is a hypothetical edit requiring physical work, not certification of a trolley path.
- Weak-point analysis groups closures by stranded room sets. Unlike the handoff's assumption, ordinary room doors are also weak points (one room each on the demo factory).
- Claude now has typed tools for exact counts, shared walls, 3D distance, errands, read-only door effects and weak points.
- Human routes no longer fall back to free outside hops. Exact furniture validation withholds guidance when a safe modeled passage cannot be established.
- Offline check: 21 unit tests; route model 2130/2130; solver and train/dev parser 655/655; test parser 145/145; e2e 653/655; basic train+dev 2124/2130; robust 630/630; metamorphic 898/898.
- Walkability: 134 validated routes, 26 cases with guidance withheld, zero invalid routes in 160 sampled pairs. This is not 100% route availability. Earlier 145/149 results omitted unreachable cases and tolerated dataset-blocked furniture crossings.
- Normal Claude coffee requests succeeded; the reported white-screen crash has not yet been reproduced. Frontend recovery/validation work is in progress. Voice remains unverified on physical hardware.


## Verified building demo: milestone 2

- Reproduced the white-screen failure in the browser: conversation auto-scroll returned a value from a React effect, which React later called as a cleanup function. The effect now returns nothing; repeated-message regression and live Claude coffee request pass. Error boundaries retain recovery UI.
- New dark 3D Navigator has batched floor geometry, instanced asset footprints, opening gaps, closure markers, ghost previous route, room picking, eye-level preview, manual waypoints and reduced-motion static guidance.
- Fresh-server Playwright run: 46/46 desktop + phone tests, including streaming errors, empty routes, promise-returning scroll API, 29/56 closure impact, verified widening/apply, reduced motion and microphone denial. Physical microphone/speaker performance remains unverified.
- All 280 buildings compile to schematic scenes in a local survey (3.38 seconds before the stricter per-side opening check). Unmatched opening references are reported; eye-level preview is disabled for routes using them. No as-built completeness claim.
- Independent official-router differential: 7200/7200 length/reachability/closed-element comparisons across all 240 train/dev buildings. Command: fw eval differential.
- Demo route remeasured after stricter path validation: Lab 2.17 to Lab 4.26 step-free is 49.7 m; after closing Lift 2 it is 96.1 m. These replace the PDF's earlier 49.5/95.6 m values.
- Draft PNG import and source-image reference overlay are restored. Source overlay is not a calibrated registration; inferred doors require review. SVG-first parsing is not implemented.
- Newly added compound-place tool intersects room type, floor, contained asset and above/below filters. No office with a coffee machine is fabricated.


## Final implementation verification

The updated effect is verified in a real browser and with a promise-returning scroll API regression. Unit tests also cover step-distance sums, profile-triggered rerouting, exact route-node output and independent closure routing. Rehearsal on the new session-context prompt passed an additional route/closure pair plus unsupported and dangerous-request state checks. Current map context is refreshed each turn and never overrides an explicit requested origin.

The recorded deterministic fallback and screenshots are under runs/demo; the capture uses real backend geometry and operations with a scripted chat transport. It has no live Claude or microphone audio. The three-minute speaking script is docs/DEMO.md. SVG-first import, the optional bridge/articulation proof, undo UI, a slide deck, physical voice tests, projector checks and Sunday release execution remain outside this completed app milestone; no claims are made that they shipped.

## UX overhaul milestone 1 (2026-10-24)

Implemented a shared preview timeline, frame-independent progress, bounded camera rotation, seek/speed controls, distinct arrival state, landmark guidance, explicit floor scopes, persistent manual-position markers, a linked expandable plan, and a collapsed route itinerary. Preview never changes declared location. Verified: `fw check` (27 unit tests and all offline gates; existing ambiguous-name misses unchanged); 40 initial desktop/phone checks passed, four corrected-flow checks passed on rerun, and two new seek/arrival/replay checks passed. Physical voice and uncoached teammate testing remain manual.

## UX overhaul milestones 2–3 (2026-10-24)

The building workspace now has linked/focused plan and model selection, manual location/facing separate from preview position, compact mobile guidance with an expandable stage, camera memory, instanced oriented door frames, illustrative ceilings and recognizable equipment. Duplicate/coplanar display walls are unioned without changing analytical geometry. Supplied stair assets are illustrative; unsurveyed connector interiors use landing transitions, not invented continuous flights.

Chat now dispatches supported counts, item rankings, highlights, area queries and references deterministically, including without an API key. Unknown simple wording uses the configured parser; edits, complex constraints and multi-step work use the full agent. Required parser fields are checked before execution. All geometry facts stay deterministic. Specialized tool schemas load on demand on both providers.

Complete visual result events and session-scoped paged results support every question family. Search no longer limits computed highlights to 12. New analytics include inclusive, labeled chair-family counts, optional floor/room counts, room rankings with ties, AND equipment/minimum-count filters, and area/count groups. Source capacity, bookings, access and windows remain unavailable rather than inferred. Per-turn usage includes cache tokens and latency; price estimates require explicit `FLOORWISE_MODEL_PRICES_JSON` rates (USD per million tokens).

The eval ledger now creates unique run directories and gates identify their own process's summaries, fixing same-second evidence overwrites. Latest verification details and the 25-issue mapping are in `docs/UX_AUDIT.md`. Physical voice, projector/FPS measurement and the three-person uncoached study remain manual; no claim of having completed them is made.

### Latest measured evidence

- `fw check`: 57 unit tests passed; all offline gates passed. Routing 2130/2130, solver/parser 655/655, test parser 145/145, robustness 630/630, metamorphic 898/898, differential 240/240. The eight pre-existing ambiguous-name e2e misses are unchanged.
- `fw ui-test`: 64 desktop/phone checks passed; the two opt-in recording cases are skipped in routine runs.
- All 280 supplied buildings compiled successfully: 175,456 display-wall segments in 11.11 seconds total on this machine. This is compilation throughput, not an FPS measurement.
- Live Claude and Groq passed unfamiliar-count wording and closure tools; the final closure smoke passed with deferred tool schemas on both providers. Known simple chat questions are verified to make zero model calls.
- Visual audit evidence: `runs/ux-overhaul/`; complete issue mapping and human acceptance script: `docs/UX_AUDIT.md`.

The updated deterministic fallback recording passed its opt-in capture test and is saved at `runs/demo/fallback.webm`, including a real zero-model chair-ranking turn after the scripted route/closure/fix transport. It is not a live voice recording.

## CIT walking regression and straight corridors (2026-10-24)

Fixed grid-region connectivity to match the pathfinder's no-corner-cutting rule. The reported CIT route 03.05.061 → 00.05.058 now produces validated walking geometry. Empty, convex, elongated corridors use a verified central straight run with door approaches instead of raster-induced slalom. Source graph/benchmark distances and obstacle collision checks are unchanged. Verified by targeted regressions and `fw check`; subsequent UI redesign is in progress.

## Guidance and rendering second pass (2026-10-24)

Guide me now uses the full scene and one compact media player with direct play, seeking, chapter navigation, speed and replay. Map and conversation are opt-in drawers. Room selection preserves camera framing; Focus room and Fit animate explicit changes. Pointer-intent handling prevents pan/rotate gestures from selecting rooms, including drags returning to their origin. Dense plan labels avoid collisions; route/selected connector labels use fixed-size icons. Raised opaque route geometry and tighter camera depth ranges replace overlapping route strips. Interiors retain ceilings. Manual-location and simulated-progress markers are distinct.

Integrated the reviewed Claude asset catalogue: all 96 supplied types have bounded, illustrative procedural silhouettes rendered in instanced batches. Repeated tools are grouped by turn and name with inspectable inputs and computed summaries. The closure stress-test panel now explains its actual reachability computation and assumptions.

Verification: `fw check` passed all offline gates; the eight existing ambiguous-name e2e misses are unchanged. Full desktop/phone UI run: 90 passed, four opt-in capture/contact-sheet cases skipped. TypeScript check passed after the concurrent companion package's typing fix. Screenshot evidence is under `runs/ux2/`; design rationale and incomplete stair/sensor/human checks are documented in `docs/UX_REVIEW_SECOND_PASS.md`. The phone companion and benchmark-resolution packages remain separate work until their READY handoffs are reviewed; this milestone does not claim they are integrated.

## Paired phone integration and ambiguity review (2026-10-24)

The companion is now mounted at `/phone` with confirmed, expiring pairing, synchronized computed instructions, remote chapter/repeat controls, touch/optional gyro camera orientation, recenter, revocation and reconnect. `fw start --lan` exposes the single-process server to the selected same-network phone setup. Added the required WebSocket transport dependency. The default LAN HTTP setup supports touch; motion requires a trusted secure context and an explicit user action. No physical phone, iOS hardware or real LAN trial is claimed. Setup and the short jury beat are in `docs/PHONE_DEMO.md`.

The real two-context integration test exposed a connector-label DOM teardown race. Labels now project into the ordinary React overlay with wall occlusion rather than creating independent DOM roots inside the canvas. First-person orientation looks farther along visible walking sections, ray-tested against walls, while positions remain on the validated route. Phone orientation does not update the declared location. Read-aloud also works when explicitly enabled during playback.

Reviewed the benchmark package: larger bounded sampling and ambiguity diagnostics are integrated; the proposed same-room pruning was rejected to preserve valid zero-length/repeated-room interpretations. The eight insufficiently specified end-to-end misses remain unchanged. Final `fw check`: 108 unit tests and all offline gates passed. Full UI run: 113 passed; 27 duplicate-project/opt-in cases skipped. The final wall-visible camera adjustment passed 11 targeted checks, including real paired navigation, with one duplicate-project skip. Typechecking and production build passed through `fw ui-test`.

The multi-hop capacity/evacuation proposal and landmark/multisensory evidence are saved under `research_notes/scenario-simulation/`; integer scheduling/discretization concerns are recorded in the integration review. The engine is now implemented (`floorwise/reason`, `floorwise/evacuation`, `server/scenario.py`, chat tool `plan_scenario`); it is not yet wired into the web UI. Occupants are a seat-count estimate and capacity is a flow rate with an adjustable band (1.0 to 1.6). No occupancy data, throughput measurement, stair flights, hazard progression or responder tactics have been invented. Continuous surveyed stair traversal, physical voice/sensor rehearsal and unfamiliar-user acceptance remain incomplete.

## Atrium, phone and chat corrections (2026-10-24)

Removed blanket current-room ceilings. Recorded upper-floor unions are triangulated with gaps intact, and actual upper slabs/walls provide context during guidance. All 280 buildings compiled to 85,264 slab triangles in 20.475 seconds; summed triangle areas match every unioned footprint within 1e-5 m². This does not recover unrecorded roof/atrium geometry or measure interactive FPS.

The route display now uses flat strips and round joins instead of swept tubes. Camera turns use damping and a speed bound; the analytical walking polyline is unchanged. Claude owns the pending graph/routing changes and the remaining walking-line zigzag audit. Scene pinch-wheel gestures no longer zoom the whole page; intentional page/keyboard zoom remains available. The media rail is smaller and mobile secondary tools are collapsed.

Fixed the phone's ignored overview input when no route existed. The pad now turns the existing overview or first-person camera without silently changing modes or declared position. The phone can open the current building in its own expanded 3D workspace; motion/disconnect controls are collapsed. Verified in separate browser contexts, not on physical hardware. Assistant room mentions now link unique names/references to the real room inspector/focus; ambiguous names and decimal measurements are not guessed into links. Added footprint clipping for rotated equipment parts after the isolated tests exposed small robot-cell arm overflow.

Release browser validation: 124 passed, 28 duplicate-project/opt-in cases skipped. Integration snapshot: 118 unit tests and all offline gates passed. The shared core's basic e2e result is 2122/2130 versus the prior committed 2124/2130; this belongs to Claude's in-progress core changes and is documented in `docs/parallel/codex-third-pass-handoff.md`. No graph/routing changes are included in the UI commit. Sources and future VR/AR/SLAM/Wi-Fi/BLE requirements are in `research_notes/PHONE_XR_POSITIONING_REVIEW.md`. Physical devices, immersive XR and live positioning remain unverified/unimplemented.


## Kit 1.1.0 route rules (2026-10-24, evening)

Synera patched the expected answers (`patch/fix-answers-ruleset`, kit 1.1.0). The questions are unchanged; **the route model is not**: walking is door to door inside each space, 15 cm off the walls, round corners; a door lands 30 cm inside; stairs cost 2 m per metre climbed; a lift costs 15 m once per ride plus 1 m per metre climbed and joins every pair of its stops; **there is no way round the outside**. Our previous model (centre-to-door straight lines, 12 m per floor stairs, 15 + 6 m lifts, a free outside hop) was the old rule set, so every route number in this file dated before this section refers to it and is superseded.

- Re-implemented from the written rules in `floorwise/core/spacewalk.py` and `graph.py` (not copied from the starter). Verified: `routes` 2130/2130 to the centimetre with 1313/1313 leg space paths and element paths identical to the dataset's; `differential` 7280/7280, including edge-for-edge equality of the whole graph with the kit's own `starter_agent/building_map.py` on all 280 buildings (train, dev and test) with and without step-free; the kit's own `benchmark.evaluate` scores 138/138 on dev; `solver` 655/655; test parser 145/145.
- Route answers are now the ordered list of spaces passed through (what Synera says is scored): `Answer: A -> B -> C` with ids; "no route" when none exists.
- New rules in the model: without stairs, closed or blocked places (rooms, doors, lifts), a forklift (aisles and openings of 3 m or wider, no stairs or lifts), production bays as destinations that are never crossed. **Assumptions to confirm with Synera:** what counts as a "forklift aisle" (we use corridor, hall or outdoor spaces that are not bays and can hold a 3 m circle); which spaces are "production bays" (hall spaces whose room type ends in `_zone`); and that "without stairs" means the step-free rule (lifts, ramps and doors only).
- Drawn routes follow the same geometry: straight lines and corners only (taut string around furniture, 20 cm clear), no raster staircase. Where furniture closes a door off the drawn line is the official walk and the room is flagged. Walkability: 3 of 216 walked pairs withheld (was 26 of 160).
- Known misses are exactly the 11 diagnosed ambiguous-name questions in `eval/known_issues.json`; the gate fails on any other miss.
- Demo facts changed: step-free Lab 2.17 to Lab 4.26 is 60.15 m via Lift 3; close Lift 3 and it is 73.00 m via Lift 2 (closing Lift 2 no longer changes this route).


## Interactive chat recovery (2026-10-24)

The reported `hello` stall was reproduced on the real Claude path: the structured parser returned HTTP 400, "Schema is too complex." The Claude transport now requires top-level fields rather than compiling combinations of optional fields; the original Pydantic model still validates every result. No local greeting response was added. Live verification returned a reply through ChatAgent in 9.67 s, the HTTP/SSE endpoint in 6.93 s, and Chrome in 4.16 s (cache/network conditions differ; these are observations, not latency guarantees).

Interactive model calls have 25 s network timeouts, no SDK retries, and a 60 s budget checked before subsequent calls; deterministic tool CPU work is not forcibly interrupted. The server immediately streams progress, bounds session-lock waits, and always ends error streams. Failed model turns roll back incomplete conversation messages while retaining computed session state, allowing the next prompt to recover. Benchmark/evaluation timeout and retry defaults are unchanged. The UI shows the active request stage; the optional facing selector was removed. Common count commands and unconstrained explicit from/to wording dispatch to deterministic tools; greetings still reach Claude.

Regression coverage includes transport-schema validation, deadline scope, both provider history recovery, SSE timeout/retry, and desktop/phone recovery. Full UI run: 125 passed, 28 skipped, one Lab loading timeout; all 8 Lab tests passed on targeted recheck. `fw check` passed: 142 unit tests and all configured offline gates, with only the explicitly diagnosed benchmark ambiguities. Exact route, solver and parser gates remain 100%.


## Pairing QR and route display repairs (2026-10-24)

Phone setup now generates a local QR from the LAN phone URL, with address/code fallback and confirmation retained. Chrome-generated QR pixels were decoded using OpenCV and matched the active pairing URL; New code regenerated the image. Actual Navigator pairing/remote control regression passed. Physical phone hardware remains unverified.

Current and previous route strips use separate floor offsets and unlit, depth-tested materials without writing coplanar depth, reducing route-overlay interference while preserving wall occlusion. A generic walking repair excludes fully enclosed, separately recorded spaces from a containing hall's free area, including source furniture clearance; it preserves door endpoints and withholds a preview if no valid detour exists. On the reported CIT room-to-toilet route, the initial polyline crossed two stairwell walls; the repaired polyline crossed none. No stair flights or new geometry facts were invented. Two synthetic nested-space regression fixtures and the combined offline/UI checks cover this pass; concurrent route-model changes remain separate.


## Cognitive-load audit and submission release (25 October 2026)

Audited the running UI against the requested Laws of UX article and docs/UX_PLAN.md before editing; findings are in docs/UX_COGNITIVE_LOAD_AUDIT.md. Secondary actions (including scenarios) share a labelled Tools disclosure; examples are grouped; origin assumptions and manual/linked starts are disclosed; room search includes floor names and omitted-match counts. The phone first-use layout keeps all six labelled destination shortcuts above the composer at 390 × 844.

Final validation: 373 unit tests passed; serial desktop/phone UI run 136 passed and 28 intentional skips; fw doctor passed. The complete post-fix fw check passed all configured gates: exact routes 2130/2130, solver 655/655, parser train/dev 655/655 and test 145/145, robust 630/630, transformations 860/860, rules 661/661. Raw e2e remains 653/655, basic 2122/2130 and Sunday 1329/1338, with only the individually diagnosed ambiguities. Wider checks on all 280 buildings passed: 3039/3039 generated routes, 8960/8960 graph/route comparisons and 3275/3275 new-wording round trips.

Live Claude rehearsal initially failed 0/3 because specialized tool loading invalidated preserved-thinking signatures. The provider now uses documented invalid-binding handling while preserving assistant/tool history; the three five-turn browser/SSE rehearsals then passed 3/3. Keyboard Escape/menu races, a phone toolbar overlap and a Windows nested dependency-install lock in the companion test launcher were also repaired and browser-tested.

fw submit now validates complete unique public-test IDs, rejects unresolved or contradictory answers, and creates exactly SUBMISSION/BENCHMARK.md and SUBMISSION/answers.json. Final generation covers 145/145 questions with zero fallbacks; legacy CSV uses those same predictions. The latest organizer announcement supplies filenames but no JSON schema.

Import remains a material limitation: the assisted 40-building/122-floor diagnostic passes 22 strict floor checks, with mean room recall 93.8%, door recall 81.7% and floor-only exit-connected share 30.4%. This diagnostic omits reconstructed vertical connections and is not a predicted jury score. The import evaluator now returns nonzero on failed/empty checks rather than making a poor import look like a passing full-profile phase.

The demo plan is now exactly 120 seconds, and docs/SUBMISSION_TECHNICAL.md provides form copy and the configured repository URL. The edited duration-verified video, repository push and final Hack and More form submission remain outstanding. Physical phone/audio/projector and uncoached human validation remain unverified. Full evidence, failures and snapshot/fingerprint limitations from concurrent checkout changes are in docs/RELEASE_AUDIT_2026-10-25.md; logs and screenshots are in runs/ux-*.


## Product evidence and Claude-first chat (25 October 2026)

Normal chat now always uses the conversational provider and deterministic tools; regex dispatch and the structured parser are retained only as benchmark/helper infrastructure. Text streams over SSE with message IDs, completion reconciliation and partial-answer recovery. Tool schemas stay fixed throughout a conversation: specialized schemas are discovered as data and executed through a locally validated dispatcher, avoiding changes to the prefix bound to provider thinking signatures. Count/location requests use computed room groups, not page samples. Cards retain a View results reference in their originating turn; result pages are immutable snapshots and no longer wait on the chat write lock.

The Lab now opens on four judge-weighted readiness panels, raw evidence, release blockers and a feature inventory. Content fingerprints include dirty source, dataset, frontend, model and effort; unfingerprinted or mismatched runs are historical. `fw test smoke|full|live|demo` adds product profiles, unit/browser report ingestion, a 30-conversation real-browser/SSE pack and bounded demo rehearsals. Grading usage is included, unpriced model cost stays unknown, and budget-exhausted cases remain incomplete. The first exploratory pack is deliberately retained with its failures (17/31 including a separately corrected build-row bookkeeping bug); it is not a current grade or proof of release readiness. The grader was subsequently corrected to receive supplied building context and automatic highlight evidence. One complete five-turn live rehearsal passed after stable-tool discovery; the reduced 180k retry budget exhausted before all three could be reviewed. Three passing rehearsals and uncoached human/physical-device checks are still required.

The remote capacity-flow and typed reasoning implementation has been brought into this shared checkout, with SciPy declared and locked. Its operator/core tests pass. Tools → Scenarios requires explicit occupancy and opening throughput, computes baseline/blocked comparisons, exposes model assumptions, and publishes schematic flow independently of walkable navigation. The scenario UI passed on desktop and phone. No capacity, availability, access or physical tracking data is invented.

Human previews now check rendered walls and recorded furniture. Room-level origins use a doorway-connected free component instead of starting inside furniture. No furniture collision waiver reaches playback; unsafe joins are withheld and counted separately. The latest completed check retained exact route/solver/parser gates, robust 630/630, transformations 860/860, and 130 checked wall-clear previews, 29 unavailable routes and one withheld preview in the 160-pair sample. Further updated-source validation and limitations are in the run ledger; no historical numbers should be presented as proof of this exact build.

Latest product rehearsal (`20261025-003631_demo_87bd6931`): all three five-turn conversations completed with real streamed text, no provider errors, retained origin/accessibility and no applied edits. Raw result is **2/3**, because language review identified an exit/connector conflation in one reply. This supersedes any earlier 3/3 claim for the current source. The 300k process budget included grading; recorded usage was 81,693 input, 4,999 output, 161,464 cache-read and 6,884 cache-write tokens. The latest smoke profile completed both unit and browser phases; its fingerprint changed during the run and is historical evidence. The current unit suite passes 374 tests.

Integration follow-up: the current-branch team merge preserves the verified kit graph and newer chat/session handling while bringing in graph-compatible widening fixes and profile tests. Exact printer types outrank substring matches; assumed map starts retain provenance through API, model context and UI, and room destinations are explicitly distinguished from equipment positions. Filtered room answers include complete floor totals plus clearly marked example rows. Closure summaries include deterministic per-floor room counts, and the grader now receives the closure highlights the UI actually renders.

The expanded 30-conversation browser/SSE pack (`20261025-004659_live_chat_bb773074`) accounts for every case: 25 passed, three language-review failures and two budget-incomplete cases. All three critical repeats passed. Follow-up disambiguation and closure cases passed after repair; the availability answer needed another complete-summary repair. A separate stable-server showcase (`20261025-005412_demo_20715c93`) completed and passed all three five-turn rehearsals within its 300k process cap. This does not retroactively improve the raw 25/30 result. Source fingerprints must still be consulted because concurrent reconstruction/private-test work continued in this checkout.

Fresh UI follow-up: 18 Lab/product browser cases passed, then smoke passed 23 focused unit contracts and 10 browser cases. The combined Python suite reached 380 passing tests before later concurrent import/private-test additions. All-building wall evidence: 908 emitted previews were clear, 151 routes were unavailable and 61 previews withheld among 1,120 samples. The Lab now distinguishes these coverage limits from safety-contract checks, traces requirements to implementation/tests/assumptions, and only verifies features with matching case evidence.

The final targeted availability recheck (`20261025-005720_live_chat_0a11967b`) passed after complete per-floor summaries and explicit sample/data-limit metadata were added. The 25/30 pack remains unchanged. A second configured `fw check` also finished successfully, retaining exact routes/solver/parser, robust 630/630, transformations 860/860 and differential 256/256. Concurrent reconstruction/private-evaluation files are intentionally left outside the integration checkpoint until their owner finishes; no source-changing run is labelled current proof.

Latest collected Python suite: 392 passed. Full live/demo requirements now reject subset runs by explicit scope metadata and expected denominator (30 conversations or three rehearsals); a regression verifies a passing one-case repair cannot replace a failed full pack. This also protects historical focused runs without scope metadata by their case count. Incomplete live rows retain family/building identity. Integration commits 10ff34a and 22bc539 were pushed on the existing codex/verified-building-demo branch; no new branch or force push was used.

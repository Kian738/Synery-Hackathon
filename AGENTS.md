# AGENTS.md: how to work in this repository

This file is the contract for any coding agent (Claude Code, Codex, Cursor) or teammate working here. Read it before changing anything. `CLAUDE.md` points here.

## What this is

**Floorwise** is our entry for Synera Track 01, "Talk to your building", at the Industrial Agents Hackathon 2026. It is an indoor navigation agent: people ask a building where things are, how to get somewhere (step-free, avoiding areas, multi-stop), and report changes (closed lift, new door). The building can be rebuilt from floor-plan images.

Grading: 55 % automated correctness (the hidden "Sunday" building plus the test set), 25 % interaction rubric ("asks only what it needs, shows what it understood, gives directions a person can follow; voice counts"), 10 % creativity, 10 % demo video. The challenge text is in `docs/industrial-agents-hackathon-2026/README.md` and `docs/Hackathon Challenge - Talk to Your Building.pdf`.

## The one rule of the architecture

**Every fact comes from deterministic code. The LLM only parses language and words answers that have already been computed.**

- `floorwise/core` computes everything: geometry, routes, reachability, what-if edits. There is no LLM in it.
- The LLM turns text into a `QuerySpec` (`agent/parse_*`), drives tools (`agent/tools.py`), and phrases results.
- Never let a model estimate a distance, an area, a count or a route. If the model needs a fact, add a tool.

Why: LLMs are unreliable at geometry (FloorplanQA, ICML 2026), and the benchmark checks exact numbers. See `reports/Indoor wayfinding agent UX.md`.

## Map of the code

| Path | What it is | Status |
|---|---|---|
| `floorwise/core/analytics.py` | complete chat counts, item rankings/ties, content filters and grouped stats; benchmark semantics unchanged | unit-tested |
| `floorwise/core/scene.py` | cached schematic walls and opening gaps; display-only wall deduplication | unit-tested |
| `floorwise/agent/local.py` | deterministic benchmark/helper dispatch and validated parser-to-session adapter; normal chat is Claude-first | unit-tested |
| `floorwise/core/model.py` | `Building`: typed, cached view of one `building.json` | verified |
| `floorwise/core/spacewalk.py` | the judges' walking rule (kit 1.1.0): door to door inside each space, 15 cm off the walls, round corners, doors land 30 cm inside; cached per building on disk (`runs/.walk-cache`) | gold to the cm, 280 buildings graph-equal to the kit |
| `floorwise/core/graph.py` | `RouteGraph`: the judges' route model (stairs 2 m per metre climbed, lift 15 m + 1 m per metre, no outside hop) plus `Constraints` (step-free, min width, closed, avoid, soft-avoid, forklift, bays as destinations, extra doors) | verified (L0 100 %, `eval.rules`, `eval.differential`) |
| `floorwise/core/geometry.py` | areas, 3D centroids, shared walls (0.35 m, ≥1 m), stacking, wall midpoint | verified (L1 100 %) |
| `floorwise/core/ops.py` | one operator per question family | verified (L1 100 %) |
| `floorwise/core/routing.py` | `plan_route`, tours, polyline | verified (L0 100 %) |
| `floorwise/core/walk.py` | drawn walking lines per room: taut string (visibility graph) around furniture, 15 cm off walls, straight lines and corners only; doorway-connected origins and strict preview collision gating; blocked previews are withheld | drawn length ≈ official + clearance; few withheld |
| `floorwise/core/instructions.py` | followable directions: decision points, salient landmarks, floor-change steps, spoken overview (research §3) | unit-checked; wording reviewed by hand |
| `floorwise/core/resolve.py` | entity linking: floors, rooms, room types, item types, lifts; fuzzy, with candidates | verified on train/dev/test text |
| `floorwise/agent/spec.py` | `QuerySpec` (mentions) → solver inputs; ambiguity readings | verified |
| `floorwise/agent/parse_rules.py` | free regex parser for known phrasings | verified 655/655 + perturbations |
| `floorwise/agent/parse_llm.py` | LLM parser for unknown phrasings | live on Groq: 36/40 dev; Claude parser 39/40 in recorded prior run |
| `floorwise/agent/solve.py` | kind + inputs → result + reply ending in `Answer:` | verified |
| `floorwise/agent/answer.py` | benchmark entry `answer(dir, text)` | verified (kit evaluator 138/138 dev) |
| `floorwise/agent/session.py` | per-user state: closures, edits, profile, UI events | unit-tested |
| `floorwise/agent/tools.py` | LLM tools wrapping `Session` | live on Groq |
| `floorwise/agent/chat.py` | `ChatAgent` (provider-neutral) | live on Groq and Claude; five route/closure rehearsals verified |
| `floorwise/llm/` | provider layer: `anthropic` (prod), `groq`/`openrouter` (testing) | Groq verified |
| `floorwise/build/` | floor plan images → `building.json` (CV + learned palette + optional vision labels) | procedural 100 %; OSM/Swiss weaker |
| `floorwise/cli.py` | `run_benchmark` (Sunday command) | verified offline |
| `floorwise/submission.py` | validates complete public-test predictions and packages exactly `SUBMISSION/BENCHMARK.md` and `SUBMISSION/answers.json`, plus legacy CSV | unit-tested |
| `floorwise/fw.py` | `fw`: the one command | verified |
| `eval/` | eval suites L0–L7, ledger, report | see `docs/EVALS.md` |
| `server/app.py` | FastAPI: geometry, sessions, route/close/door, SSE chat, build | tested; chat live on Groq |
| `server/companion.py`, `web/src/companion/` | confirmed paired-phone relay and controller; `/phone`, touch/optional secure-context gyro | protocol + two-browser tested; physical hardware pending |
| `web/src/scene-assets/` | bounded illustrative procedural visuals for all supplied asset types | catalogue + footprint tests |
| `server/checks.py` | the Lab's inspection sheet: every check in plain words, target, cost, grading group | |
| `server/lab.py` | Benchmark Lab API: runs, compare, dataset, launch suites with live logs | tested |
| `web/src/navigator/` | Navigator UI (signage design, route sign, steps, step mode, voice) | desktop + phone regression coverage; see docs/STATUS.md |
| `web/src/lab/` | Benchmark Lab UI (overview, launcher, runs, drill-down on plan, compare, dataset) | Playwright |
| `docs/` | our docs plus the kit (`docs/industrial-agents-hackathon-2026`, read-only) | |
| `research_notes/`, `reports/` | sourced research behind the decisions | |

The full status matrix is in `docs/STATUS.md`. Update it whenever you change what works.

## Commands (everything goes through `fw`)

```bash
uv sync                      # once
uv run fw                    # list commands
uv run fw doctor             # check setup (keys, data, web build)
uv run fw start              # app at http://localhost:8000
uv run fw start --lan        # same app reachable by a phone on this network
uv run fw dev                # hot-reload dev (backend :8000, frontend :5173)
uv run fw check              # all offline tests + eval gates; must stay green
uv run fw ui-test            # Playwright UI tests (desktop + phone) against a fresh server
uv run fw test smoke         # product contracts and focused desktop/phone checks
uv run fw test full          # comprehensive offline product evidence
uv run fw test live          # 30 real-browser conversations, three bounded batches
uv run fw test demo          # three continuous live showcase rehearsals
uv run fw submit             # validate SUBMISSION/{BENCHMARK.md,answers.json} + legacy CSV
uv run fw bench B Q OUT      # Sunday run (see BENCHMARK.md)
uv run fw eval <suite> ...   # one suite (docs/EVALS.md)
```

## Rules for changes

1. **Run `uv run fw check` before committing.** L0, L1, L2 and parser-test coverage must stay at 100 %. Any drop in `e2e`, `robust` or `metamorphic` must be explained in the commit message.
2. **No building-specific code.** Never put building IDs, room names or test-set strings in `floorwise/`. Test questions have no answers; never hand-label them (that is against the rules). The Sunday building is unseen.
3. **Semantics are settled against gold, then frozen.** Examples: "rooms" in reach counts means `type == "room"` including the start; shared walls exclude corridors, stairs and lifts but include halls. If you change one, re-run L1 on train+dev.
4. **LLM code must work on both providers.** Use `floorwise.llm` (`Conversation`, `structured.parse`, `tool`). Never import `anthropic` or `openai` outside `floorwise/llm/`, except in the build-vision labeller.
5. **Secrets live only in `.env`** (gitignored). The Groq key is for testing; one live Claude call was verified on AWS Bedrock (plan_scenario, numbers matched the solver); Anthropic API or AWS Bedrock only, never Vertex.
6. **Keep docs true.** After a change, update `docs/STATUS.md`, and also this file if paths or commands change.
7. **UI work follows `docs/UX_PLAN.md`** and the design rules in it, not generic dashboard defaults.
8. **UI work uses the control kit.** `web/src/ui/kit.css` is the only place that defines control height (40 px), corner radius (12 / 16 px / pill), gaps (8 / 16 px) and the button font; use `IconButton`, `Segmented`, `Popover`, `Dock` from `web/src/ui/kit.tsx`. Never add private button CSS, new `!important` patches or literal radii/heights to `styles.css`. Every icon-only control needs a label (tooltip + `aria-label`). Floating chrome on the 3D stage lives in the four docks (top-left view switch, top-right Map / Layers / Tools, bottom-left camera, bottom-centre status). Icons go into `components/Pictogram.tsx`. `web/tests/ui-kit.spec.ts` enforces size, radius, gap, no overlap, names, and a compact floor rail; run it with every UI change (desktop and phone).
9. **3D rules.** Files and owners: `Building3D.tsx` (scene, focus, camera), `Connectors3D.tsx` (stairs; `stairWalkLine` mirrors `stairBoxes`), `LiftShafts.tsx` (animated hollow car, doors), `Ceilings.tsx` (roofs), `SceneAssets.tsx` + `scene-assets/` (models; add a type in `families.ts` and `catalog.ts`, keep part budgets, run `asset-catalog.spec.ts`), `lib/focus.ts`, `lib/cameraPath.ts`, `lib/playback.ts` (speed profile). Item facing is calibrated from data (`uv run python -m eval.orientation`, `FACING_OFFSET_DEG` in `SceneAssets.tsx`): do not change it without re-running the audit. Verify visually: a passing data attribute is not proof that it looks right; screenshot it.
10. **Edits are a first-class feature.** Session edits (`add_door`, `remove_door`, `widen_door`, `move_asset`, `add_asset`, `remove_asset`, `undo`) must keep `Session._refresh` semantics (walking-edge cache refresh) and have a test in `tests/test_edit_capabilities.py` plus the `eval.edits` check against the kit's router.
11. **Shared checkout etiquette.** Other agents edit the same tree: commit small and early, `git diff` a file before editing it, keep your logic in your own files with thin hooks, never revert files you did not change, no force-push, no extra branches without asking. On Windows use script files (Write tool) instead of long heredocs, `taskkill //F //FI "IMAGENAME eq uvicorn.exe"` to stop servers, and start the app with `uv run fw start` (port 8000) after `npm run build` in `web/`.
13. **Building selector and thumbnails.** The building menu is the Atlas (`components/BuildingAtlas.tsx`); thumbnails come from `server/thumb.py` (`/api/buildings/{id}/thumb.svg`, cached in `runs/.thumb-cache`, floor colours must stay in step with `web/src/lib/floorColors.ts`).
14. **Phone/AR.** Pure geometry lives in `web/src/companion/ar.ts` (tested without a headset); the companion protocol field `path` is validated in `server/companion.py` (max 400 finite points). Do not add companion message fields without a server check and a test in `tests/test_companion.py`.
15. **Closing things.** `set_closed` on spaces is chat-only; the UI asks via `closure_preview` before a closure strands rooms. Do not make closing a corridor a one-tap action. Stair floor plates: `compile_stair_plates` is display-only; never change analytical polygons.
16. **Search.** Keep Dijkstra (measured 11 ms worst case); see `docs/BACKLOG.md` before proposing A*: only a landmark (ALT) heuristic is provably safe on this graph.
17. **Models.** No two differently coloured parts of a model may share a face plane (`web/tests/zfight.spec.ts`; `scene-assets/zfight.ts` recesses the larger part 3 mm as a guard). Seating is turned by `lib/facing.ts`, everything else by the measured rotation + 180 (`eval.orientation`). Track work in `docs/TASKLIST.md`.
12. **Tests to run for UI/3D work:** `npx tsc --noEmit`, `npx vite build`, then `npx playwright test tests/ui-kit.spec.ts tests/focus-guide.spec.ts tests/camera-quality.spec.ts tests/navigator.spec.ts tests/ux-regressions.spec.ts tests/product.spec.ts tests/visual-workspace.spec.ts tests/cognitive-load.spec.ts tests/review-third-pass.spec.ts tests/phone-integration.spec.ts tests/playback.spec.ts tests/asset-catalog.spec.ts --project=desktop` (set `FLOORWISE_URL` to the running server), and `uv run python -m pytest -q` plus `uv run python -m eval gates` on a clean (committed) tree for the Python side.

## Data facts agents get wrong

- Coordinates are **metres** in one frame per building (some Swiss floors are centred per floor). Plan images have **no scale**: the builder needs one real dimension (or uses its door-width estimate).
- Route anchors are `representative_point()`, not centroids. Centroids are only for `straight_line_3d`.
- **Route model (kit 1.1.0, README section 3):** walking is door to door inside each space, 15 cm off the walls, round corners, never through walls; a door lands 30 cm inside the space. Stairs cost **2 m per metre climbed**, a lift **15 m once per ride plus 1 m per metre climbed** (lifts join every pair of stops). Furniture is never an obstacle for distances. **There is no way round the outside**: entrances are door nodes of one space, and two parts that only meet outside have no route (`reachable: false`). `Constraints(outside="exits")` exists only for exit-distance analyses (what-if door, weak points).
- LLM spend is capped per process (`FLOORWISE_MAX_TOKENS`, default 400k) with request timeouts. Lab jobs time out after 20 min and can be cancelled.
- OSM buildings repeat names (e.g. 9 × "Büro" on one floor). The benchmark path then solves every reading and votes; chat asks back.

## Independent reconstruction validation

`fw eval build --mode both` separates assisted geometry, actual import floors and complete-building exit/topology assessments. `fw private generate|run|live|retire` manages ignored independent corpora and frozen holdout lifecycle. Protocol: `docs/PRIVATE_VALIDATION.md`; current evidence: `docs/RECONSTRUCTION_VALIDATION_RESULTS.md`. Never tune against an opened holdout and then reuse its success as unseen evidence. Review-required imports and missing-scale clarification are not automatic reconstruction successes.

Consolidation note: `server/exterior.py` resolves only recorded OSM way references; never infer a geographic placement. `web/src/components/ExploreTools.tsx` holds contextual exploration/share controls. `uv run --env-file .env fw eval chat_regressions` is an explicitly paid five-turn provider regression; it is not the full live readiness pack. New browser acceptance remains pending the saved localhost permission gate.

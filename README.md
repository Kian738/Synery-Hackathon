# Floorwise: talk to your building

Synera Track 01, Industrial Agents Hackathon 2026. You give Floorwise a floor plan and it learns the building; after that, anyone can ask it the way, by text or by voice.

## Submission (everything for judging is in this repository)

| What | Where |
|---|---|
| Answers for the public test set (required package) | [`SUBMISSION/answers.json`](SUBMISSION/answers.json) and [`SUBMISSION/BENCHMARK.md`](SUBMISSION/BENCHMARK.md) |
| The kit's CSV (`question_id,answer`, last line `Answer: ...`) | [`submissions/team_floorwise_test.csv`](submissions/team_floorwise_test.csv) |
| Run it on any building (the Sunday command) | `uv run run_benchmark <building_dir> <questions.json> <answers.json or .csv>`; the JSON also carries `route`, `route_elements`, `legs` and `length_m` |
| Rebuild the public-test package | `uv run fw submit` |
| The app | `uv sync`, `cd web && npm install && npm run build`, then `uv run fw start` and open http://localhost:8000 |
| The multi-hop demo in one click | **Run demo** (Welcome panel or top bar), or open `/?demo=fire`: a 35 s narrated fire scenario (exact evacuation flow, minimum-cut doors with the capacity arithmetic, responder route, verified door fix). Chosen by measurement with `uv run python -m eval.demo_pick` |
| Results and their limits | [Results](#results-offline-no-api-calls), [multi-hop section](#multi-hop-scenarios-fire-evacuation-door-fixes), [`docs/JUDGING.md`](docs/JUDGING.md), [`docs/STATUS.md`](docs/STATUS.md) |

Honest limits: the public test set has no gold answers, so the CSV and JSON are predictions; the dev benchmark (138/138 with the organisers' scorer) and the route checks are the evidence. Evacuation uses seat-count occupants, no smoke model, and is a pre-screen, not a compliance check.

**Design: neurosymbolic.** Claude handles language: parsing questions, linking names to rooms, dialogue, asking back and explaining. A deterministic 3D scene graph handles space: geometry, routing, reachability and what-if simulation. Frontier LLMs are unreliable at raw geometry. FloorplanQA (ICML 2026) shows them breaking physical constraints on JSON floor plans. Graph-grounded agents do much better (Floorplan2Guide, SayPlan, SG-Nav, HOV-SG). So every number Floorwise states comes from the core, and Claude never estimates a distance.

```
 voice/text ─► Claude (parse · link · ask back · explain) ─► Session ─► spatial core ─► answer + map events
                                                                      │ scene graph: building → floor → space → item
                                                                      │ door graph (dataset route model v1.1.0)
                                                                      │ wall adjacency · vertical stacking · constraints
                                                                      │ what-if edits with impact diff
 floor plan images ─► CV regions + doors + entrances ─► Claude vision labels ─► stacked building.json
```

## Results (offline, no API calls)

| Gate | What | Score |
|---|---|---|
| L0 `routes` | route model v1.1.0 vs 2,130 warm-up answers (to the cm; recomputed by the organisers, 1,314 changed) | 2130/2130 |
| L1 `solver` | gold inputs → solver → official scorer, train+dev | 655/655 |
| L2 `parser` | question text → resolved ids vs gold, train+dev / test coverage | 655/655 · 145/145 |
| L3 `e2e` | full pipeline via the kit's `benchmark.evaluate` on dev | **138/138** |
| L3 `e2e` | train+dev | 653/655 (2 misses: 9 rooms all named "Büro") |
| L3b `e2e_basic` | locate/count/route/step-free/closure/tour from text | 2124/2130 (remaining misses: duplicate OSM names) |
| L4 `robust` | perturbed wording (case, floor synonyms, ref-only rooms, typos) | 630/630 dev |
| L6 `unseen` | test questions (no gold): rule-parsed, one reading, no errand near-tie, no new kind | 145/145 |
| L5 `metamorphic` | translate/shuffle/rotate invariance + route properties | 898/898 |
| L7 `build` | floors rebuilt from plan images (procedural buildings) | rooms 1.00 · IoU 0.98 · doors 1.00 |

Test submission: `submissions/team_floorwise_test.csv` (145 answers, regenerated under route model v1.1.0, offline, $0 API cost).

**Live-LLM status.** Every gate above runs offline and needs no model. Live Claude checks (`rehearse`, `interaction`, parser comparisons) were last run on an earlier key and before the v1.1.0 change; one live call has since been verified on AWS Bedrock (Claude Sonnet 4.6, EU inference profile, 2 requests, about 3.8k tokens): asked about a fire in a named room, Claude called `plan_scenario` and its answer repeated the solver's numbers exactly (358 people, 345 out through 2 exits in 155 s, 13 stranded in the hazard room, door fix 155 s to 145 s). The check script is not part of the gates; the older `rehearse` and `interaction` runs have not been repeated.

## Run

```bash
uv sync
cp .env.example .env                      # ANTHROPIC_API_KEY=...
cd web && npm install && npm run build && cd ..
uv run --env-file .env uvicorn server.app:app --port 8000     # app at http://localhost:8000
# dev mode with hot reload: (cd web && npm run dev) -> http://localhost:5173
```

- Benchmark: see [BENCHMARK.md](BENCHMARK.md) (`uv run run_benchmark <building_dir> <questions.json> <answers.json>`).
- Terminal chat: `uv run --env-file .env python -m floorwise.agent.chat docs/industrial-agents-hackathon-2026/data/dev/proc-factory-dev-003`
- Every offline gate: `uv run python -m eval gates`. Runs are logged to `runs/`, with a leaderboard at `runs/report.html`.
- Claude suites:
  - `uv run --env-file .env python -m eval parser --parser llm --split dev` (parser model comparison)
  - `... -m eval robust --variants paraphrase`
  - `... -m eval interaction` (tricky-user personas graded by an LLM judge)
- Rebuild from plans: `uv run python -m floorwise.build.builder buildings/new --floor 0=plan0.png --floor 1=plan1.png --width 55.5 [--vision]`

## Models

| Role | Model | Why |
|---|---|---|
| Chat agent | `claude-opus-5-5`, effort `low`, server-side fallbacks | Best at asking back and explaining; the cached building prompt keeps cost down |
| Parser for unfamiliar wording | `claude-haiku-5-5` (structured output) | Extraction only; known wording is parsed by rules for free |
| Room labels from plan images | `claude-opus-5-5` vision, set-of-mark prompting | Reads printed room labels at numbered marks |
| Interaction judge, paraphrases | `claude-opus-5-5`, `claude-sonnet-5-5` | Eval only |

## Layout

```
floorwise/core     model, graph (route model + constraints), geometry, ops, routing (directions), resolve (entity linking)
floorwise/agent    spec (QuerySpec), parse_rules, parse_llm, solve, answer (benchmark entry), session, tools, chat
floorwise/build    from_image (CV), builder (multi-floor stacking), label (Claude vision), palette (learned)
floorwise/reason   verified multi-hop: typed operators, plan DAG, per-step checks, abstention, templates, findings (suggestions re-solved)
floorwise/evacuation  exact evacuation as flows over time, responder routes, door synthesis, N-1 robust doors
floorwise/llm      provider-neutral tool loop, budget, structured output
floorwise/cli.py   run_benchmark
eval/              ledger + suites L0–L7 + report
server/app.py      FastAPI: geometry, sessions, route/close/door, SSE chat, build-from-plans
server/scenario.py POST /api/sessions/{id}/scenario (run a scenario) and /scenario/ask (the one missing input)
web/               React + Vite: 2D plan, 3D floor stack, animated routes, chat with understanding cards, voice
```

## Licences

Data under `docs/` is from the kit. OSM-derived buildings are ODbL 1.0 (© OpenStreetMap contributors). Swiss Dwellings and ResPlan are CC BY 4.0. Procedural buildings are CC0. See the kit's `ATTRIBUTION.md`.


## Verified building demo

The cinematic Navigator includes schematic 3D, first-person route preview, profile-aware closure impact, and verified hypothetical door-width repairs. See [judging evidence](docs/JUDGING.md), [demo script](docs/DEMO.md), [product brief](PRODUCT.md), and [design direction](DESIGN.md). Run `uv run fw eval differential` for the independent official-router comparison and `uv run fw eval rehearse` for bounded live Claude checks. Image-derived buildings require review; voice hardware is not yet verified.

## Multi-hop scenarios (fire, evacuation, door fixes)

Ask "fire in room X: who gets out how fast, how do responders get in without meeting evacuees, which door should we add?" and Floorwise plans a chain of typed steps (hazard, people, exits, evacuation, bottleneck, responders, door candidates, best door), checks each step's postcondition and names the step that fails instead of guessing. Claude plans and words; the numbers come from the solver, and a suggested fix is only shown after the engine re-solved the edited building. The chat tool is `plan_scenario`; the UI endpoint is `/api/sessions/{id}/scenario`.

- Re-solved means the engine re-ran its own model on the edited building. It is self-consistency, not validation against Pathfinder, PyroSim or a real drill.
- Interactive capacity scenarios and the chat tool require explicit occupancy and assumed passage rates. Legacy template diagnostics can use a seat-count estimate; that is not measured occupancy. There is no fire or smoke model, and this is not a compliance check.
- People already inside the hazard room get `escape_s` seconds to leave (default 30 s, an assumption you can set per hazard; 0 means none, and then they are reported as stranded).
- Sensitivity: `uv run python -m eval.sensitivity` re-runs one scenario at specific flow 1.0, 1.316 and 1.6 persons/s/m and occupancy x0.5, x1, x1.5. On campus-dev-000 (Canteen 0.28, 358 people, 30 s escape window) the same door is the top fix in all 6 cases up to the estimated occupancy; at x1.5 occupancy it is a different door at flow 1.0, none at 1.316, and the first door again at 1.6. Absolute seconds move (145 to 175 s at x1), so the fix ranking is only stable up to the estimated headcount.
- How good is the plan: on campus-dev-000 the exact plan takes 155 s (110 s walking plus 45 s queueing). Against the classic CCRP heuristic (165 s) it is about 6% faster; against everyone using their nearest exit (260 s) it is 40% faster. The second figure compares to a naive baseline, so quote the first for state-of-the-art claims.
- Across the dataset (`uv run python -m eval.ccrp_gap 40`, one fire per building, 40 sampled train/dev buildings): the exact plan matches CCRP in 26 of 27 comparable scenarios (best 4.2% faster), so the value is not raw speed. It is that the plan names the doors that limit the evacuation, reserves a responder route, and finds a verified door change in 9 of 40 buildings (median 8% faster evacuation, best 14%) and says so plainly when nothing helps in the other 31. Times are in 5 s steps.
- Stress test across the dataset: `uv run python -m eval scenarios` (determinism, people conserved, exact never slower than the CCRP heuristic, every suggested fix verified and better). It tests robustness on generated and inferred kit data, not real buildings.

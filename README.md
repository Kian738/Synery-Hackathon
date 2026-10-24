# Floorwise: talk to your building

Synera Track 01, Industrial Agents Hackathon 2026. You give Floorwise a floor plan and it learns the building; after that, anyone can ask it the way, by text or by voice.

**Design: neurosymbolic.** Claude handles language: parsing questions, linking names to rooms, dialogue, asking back and explaining. A deterministic 3D scene graph handles space: geometry, routing, reachability and what-if simulation. Frontier LLMs are unreliable at raw geometry. FloorplanQA (ICML 2026) shows them breaking physical constraints on JSON floor plans. Graph-grounded agents do much better (Floorplan2Guide, SayPlan, SG-Nav, HOV-SG). So every number Floorwise states comes from the core, and Claude never estimates a distance.

```
 voice/text ─► Claude (parse · link · ask back · explain) ─► Session ─► spatial core ─► answer + map events
                                                                      │ scene graph: building → floor → space → item
                                                                      │ door graph (exact dataset route model)
                                                                      │ wall adjacency · vertical stacking · constraints
                                                                      │ what-if edits with impact diff
 floor plan images ─► CV regions + doors + entrances ─► Claude vision labels ─► stacked building.json
```

## Results (offline, no API calls)

| Gate | What | Score |
|---|---|---|
| L0 `routes` | route model vs 2,130 warm-up answers (to the cm) | 2130/2130 |
| L1 `solver` | gold inputs → solver → official scorer, train+dev | 655/655 |
| L2 `parser` | question text → resolved ids vs gold, train+dev / test coverage | 655/655 · 145/145 |
| L3 `e2e` | full pipeline via the kit's `benchmark.evaluate` on dev | **138/138** |
| L3 `e2e` | train+dev | 653/655 (2 misses: 9 rooms all named "Büro") |
| L3b `e2e_basic` | locate/count/route/step-free/closure/tour from text | 2124/2130 (remaining misses: duplicate OSM names) |
| L4 `robust` | perturbed wording (case, floor synonyms, ref-only rooms, typos) | 630/630 dev |
| L5 `metamorphic` | translate/shuffle/rotate invariance + route properties | 898/898 |
| L7 `build` | floors rebuilt from plan images (procedural buildings) | rooms 1.00 · IoU 0.98 · doors 1.00 |

Test submission: `submissions/team_floorwise_test.csv` (145 answers, $0 API cost).

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
floorwise/cli.py   run_benchmark
eval/              ledger + suites L0–L7 + report
server/app.py      FastAPI: geometry, sessions, route/close/door, SSE chat, build-from-plans
web/               React + Vite: 2D plan, 3D floor stack, animated routes, chat with understanding cards, voice
```

## Licences

Data under `docs/` is from the kit. OSM-derived buildings are ODbL 1.0 (© OpenStreetMap contributors). Swiss Dwellings and ResPlan are CC BY 4.0. Procedural buildings are CC0. See the kit's `ATTRIBUTION.md`.

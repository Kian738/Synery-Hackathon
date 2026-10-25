# Evaluation engine

Goal: measure everything the jury measures, without overfitting to buildings we can see. Every run writes `runs/<time>_<suite>/` (`results.jsonl` with one row per item, plus `summary.json`). `fw eval report` and the Benchmark Lab read these files.

## Suites

| Layer | Suite | Question it answers | Gold? | Cost | Gate |
|---|---|---|---|---|---|
| L0 | `routes` | Does our route model equal the dataset's? (2,130 warm-up answers) | yes | free | 100 % |
| L1 | `solver` | Given the correct inputs, is every benchmark answer right? | yes | free | 100 % |
| L2 | `parser` | Does text → ids match the gold inputs? (`--parser rules\|llm`) | yes | rules free; llm costs | rules 100 % |
| L3 | `e2e` | Full benchmark path, official scorer | yes | free (rules) | ≥ 99 % |
| L3b | `e2e_basic` | locate / count / route / step-free / closure / tour from text | yes | free | ≥ 99 % |
| L3c | `sunday` | The judges' route scoring, replicated: reply read back as an ordered list of spaces, validated and measured by the kit's own router (best length / ours, 1.0 within 1 %, 0 if invalid or the wrong endpoints, "no route" only when none exists) | yes | free | 100 % |
| L3d | `generated` | New route, step-free, closure and tour questions written for any building (all 280, test included), answered end to end, judged against the kit's router | no (kit code is the oracle) | free | 100 % |
| L3f | `roundtrip` | Benchmark question frames (cut from train/dev questions with the gold inputs) filled with the entities of any building; parser + resolver must return exactly the intended ids. `fw eval roundtrip --split train,dev,test --per-building 8`: 2,185/2,185 | no (ids known by construction) | free | 100 % |
| L3e | `rules` | Every route rule as a property on real buildings: walking off the walls, stair and lift costs, no outside hop, furniture ignored, closed places, step-free, forklift, bays as destinations, validity under the kit's measure | no | free | 100 % |
| L4 | `robust` | Same questions reworded (`--variants perturb\|paraphrase`) | yes | perturb free | 100 % perturb |
| L5 | `metamorphic` | Invariance (translate, shuffle, rotate) and route properties | no | free | 100 % |
| L6 | `interaction` | Scripted tricky users: rule checks plus an LLM judge | no | LLM | trend |
| L7 | `build` | Rebuild floors from images vs the true plan; calibration uses supplied true bounds | yes | free | latest strict check 22/122 floors; room recall 93.8%, door recall 81.7%, exit-connected share 30.4% |

`uv run fw check` runs pytest, then L0–L5 and the report, all offline.

## Protocol (from `reports/Indoor wayfinding agent UX.md`)

- **Split by building.** Develop on train, select on dev. Test has no answers; only parse coverage is measured there. Leave-one-building-out stands in for the Sunday building (planned in the Lab).
- **Report error bars clustered by building** (questions from one building are correlated). Planned in the Lab.
- **Code graders first.** LLM judges only for the rubric, binary per clause, calibrated on 30–60 hand-labelled transcripts. Report the true-positive and true-negative rates.
- **Simulated users must be difficult:** ambiguity, typos, nonexistent rooms, changes of mind, terse users, wheelchair users. Report pass^k over repeated runs, because LLM behaviour varies run to run.
- **Metamorphic checks where no gold exists:** a paraphrase gives the same parse; "avoid stairs" never yields stairs; swapping start and end gives the same length.
- **No test-set tuning.** Test strings never appear in code or prompts.

## Planned additions

1. `interaction`: binary judges per clause, pass^k (k = 3), more personas (terse, off-topic, technician voice), state-based success checks.
2. Leave-one-building-out and clustered CIs in `ledger`.
3. Followability check: parse the generated directions back into moves, execute them on the graph, and confirm they reach the goal.
4. Generated question sets (avoid-X, multi-stop, closures) for all 280 buildings, to stress the LLM parser and agent. These test the parser and agent, not the solver (that would be circular).
5. Playwright UI flows.


## Verified demo checks (2026-10-24)

`fw check` now enforces nonzero suite coverage and thresholds, adds train to the basic end-to-end gate and runs a differential smoke gate. Walkability separately reports withheld routes, requires zero emitted-path failures and at least 80% sampled route availability. It no longer counts collision-crossing fallback paths as valid guidance.

`fw eval differential` compares 7200 deterministic cases across 240 train/dev buildings with the kit's independent graph implementation. `fw eval rehearse` runs bounded live model state checks and saves transcripts for wording review. `fw ui-test` launches a fresh server on a free port; it forwards Playwright filters such as `--project=desktop`.

`fw eval build` exits nonzero when any configured per-floor quality check fails or
no floor was evaluated, so the `fw test full` launcher cannot turn failed import
metrics into a successful phase merely because the benchmark finished. This strict
diagnostic is separate from the normal offline correctness gates; see the release audit.

## UX overhaul verification (2026-10-24)

`tests/test_visual_analytics.py` checks complete aggregates, chair families, ties, AND filters, all 15 visual families, no-key/basic chat, selected-room follow-ups and preservation of constraints. `tests/test_tool_loading.py` exercises dynamic tool schemas on both provider protocols. `tests/test_eval_ledger.py` protects evidence against same-second collisions. Playwright covers the shared playback model at 30/60/120 FPS, explicit floor scopes, real deterministic chat and complete paged results. Visual workspace screenshots go to `runs/ux-overhaul/`.

Per-turn chat usage includes parser and agent models separately, cache creation/read tokens, dispatch path and latency. `estimated_cost_usd` is null unless every used model has configured input/output/cache rates in `FLOORWISE_MODEL_PRICES_JSON`. Configured rates are USD per million tokens, keyed by `provider:model`; estimates are not provider billing receipts. Fully deterministic turns report zero model usage/cost.


## Strict gates and the known-issues list (2026-10-24)

A percentage gate hides regressions: with a 99 % threshold a new bug can pass as long as it costs under one question in a hundred. Every ledger summary now reports `known_failures` and `unexplained_failures`. A miss is *known* only if `eval/known_issues.json` has a diagnosis for that exact question id (today: the 11 ambiguous-name questions in two OSM buildings, see `docs/parallel/benchmark-handoff.md`; the question text names several spaces and nothing in it separates them). `fw eval gates` fails on **any unexplained miss**, in every suite, whatever the score. Do not add an id without evidence: the file is the evidence log, not a mute button.

## Independent oracles

- `eval.differential` compares our route graph edge for edge with the kit's own `starter_agent/building_map.py` (kit 1.1.0) on every building, with and without step-free, plus sampled shortest paths under closures.
- `eval.sunday`, `eval.generated` and `eval.rules` measure our routes with that same implementation (`eval/judge.py`), so a bug in our own graph cannot hide itself.
- The kit's official evaluator also runs on our agent: `PYTHONPATH=docs/industrial-agents-hackathon-2026 uv run python -m benchmark.evaluate docs/industrial-agents-hackathon-2026/data/dev --agent floorwise.agent.answer:answer` (138/138 on dev).
- Full-coverage runs that are too slow for `fw check`: `fw eval generated --split train,dev,test --per-building 6` (1,573 questions) and `fw eval differential --split train,dev,test` (7,280 comparisons).

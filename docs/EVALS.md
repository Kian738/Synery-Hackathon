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
| L4 | `robust` | Same questions reworded (`--variants perturb\|paraphrase`) | yes | perturb free | 100 % perturb |
| L5 | `metamorphic` | Invariance (translate, shuffle, rotate) and route properties | no | free | 100 % |
| L6 | `interaction` | Scripted tricky users: rule checks plus an LLM judge | no | LLM | trend |
| L7 | `build` | Rebuild floors from images vs the true plan | yes | free | procedural 100 % |

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

## UX overhaul verification (2026-10-24)

`tests/test_visual_analytics.py` checks complete aggregates, chair families, ties, AND filters, all 15 visual families, no-key/basic chat, selected-room follow-ups and preservation of constraints. `tests/test_tool_loading.py` exercises dynamic tool schemas on both provider protocols. `tests/test_eval_ledger.py` protects evidence against same-second collisions. Playwright covers the shared playback model at 30/60/120 FPS, explicit floor scopes, real deterministic chat and complete paged results. Visual workspace screenshots go to `runs/ux-overhaul/`.

Per-turn chat usage includes parser and agent models separately, cache creation/read tokens, dispatch path and latency. `estimated_cost_usd` is null unless every used model has configured input/output/cache rates in `FLOORWISE_MODEL_PRICES_JSON`. Configured rates are USD per million tokens, keyed by `provider:model`; estimates are not provider billing receipts. Fully deterministic turns report zero model usage/cost.

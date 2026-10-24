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

# Testing and evaluation

The goal is to measure what the jury measures without tuning to buildings we can see. Official weights: 55 correctness, 25 interaction, 10 creativity, 10 demo. The Lab (`/lab`) shows evidence and coverage. It does not predict a jury grade. The public test questions have no gold answers, so 145 parsed test answers are not 145 correct answers.

## Commands

| Command | What it runs | Cost |
|---|---|---|
| `uv run python -m pytest -q` | 567 Python tests in `tests/` (61 files) | free |
| `uv run fw check` | pytest, then every offline gate (`python -m eval gates`) | free, a few minutes |
| `uv run fw ui-test` | Builds `web/`, starts a server on a free port, runs Playwright (`web/tests/`, 39 spec files, desktop 1440 px and phone 390 px). Forwards filters such as `--project=desktop`. | free |
| `uv run fw test smoke` | Focused contracts, then real desktop and phone UI with mocked model wording | free |
| `uv run fw test full` | Unit tests, gates, the independent area and centroid oracle, wall checks on all buildings, import diagnostics, browser tests. A failed phase keeps a failed exit code while later phases still run. | free |
| `uv run fw test live` | 30 real browser conversations against real Claude over SSE, in three batches of ten, each capped at 300,000 tokens including grading. Incomplete cases stay in the denominator. | paid |
| `uv run fw test demo` | Three complete live showcase conversations on one server process | paid |
| `uv run fw eval <suite> [args]` | One suite (list: `uv run python -m eval`) | per suite |

Run gates on a clean, committed tree: each summary carries a source fingerprint, and the gates abort if the source changes during a run. Evidence from a changed tree is labelled historical.

## Eval suites

Every run writes `runs/<time>_<suite>/` with one row per item in `results.jsonl` and a `summary.json`. The Lab and `fw eval report` read these files.

| Suite | Question it answers | Gold? | Gate |
|---|---|---|---|
| `routes` | Does our route model equal the dataset's 2,130 warm-up route answers, to the centimetre? | yes | 100 % |
| `solver` | Given the correct inputs, is every benchmark answer right? | yes | 100 % |
| `parser` | Does text map to the gold ids? (`--parser rules\|llm`) | yes | rules 100 % |
| `e2e` | The full benchmark path, scored with the official scorer | yes | no unexplained miss |
| `e2e_basic` | Locate, count, route, step-free, closure and tour questions from text | yes | no unexplained miss |
| `sunday` | The judges' route scoring, replicated: the reply is read back as an ordered list of spaces, then validated and measured by the kit's router | yes | no unexplained miss |
| `generated` | New route, step-free, closure and tour questions for any building, judged by the kit's router | kit code is the oracle | 100 % |
| `rules` | Each route rule as a property on real buildings: wall offset, stair and lift costs, no outside hop, furniture ignored, closures, step-free, forklift, bays | no | 100 % |
| `roundtrip` | Benchmark question frames filled with another building's entities. Parser and resolver must return exactly the intended ids. | ids known by construction | 100 % |
| `walls` | No emitted walking preview crosses a rendered wall | no | 98 % |
| `walkability` | Furniture clearance. Withheld and unavailable previews are counted separately from valid ones. | no | 100 % |
| `edits` | Route length after each edit equals the kit's router on the edited data, and undo restores it exactly | kit code | 100 % |
| `robust` | The same questions reworded (`--variants perturb\|paraphrase`) | yes | 100 % perturb |
| `metamorphic` | Translate, shuffle and rotate invariance, plus route properties | no | 100 % |
| `gold` | Every warm-up question said five more ways (voice transcript, polite, filler, German lead-in, typos), with place names unchanged. Has a hash-based 20 % holdout. | yes | 100 % |
| `differential` | Our graph against the kit's `starter_agent/building_map.py`, edge for edge, with and without step-free, plus shortest paths under closures | kit code | 100 % |
| `interaction` | Scripted difficult users: rule checks plus an LLM judge | no | trend only |
| `build` | Plan-image import with one supplied dimension. Assisted floors, pipeline floors and complete buildings are reported separately. | source geometry, used only for scoring | reported, see [PRIVATE_VALIDATION.md](PRIVATE_VALIDATION.md) |

`python -m eval gates` runs, in order: routes, solver, parser (train+dev and test), e2e, e2e_basic, sunday, generated, rules, roundtrip, walls, edits, robust, metamorphic, walkability, differential, gold (twice: normal and holdout), then report. The list is `GATES` in [`eval/__main__.py`](../eval/__main__.py). The latest results are in the [README](../README.md#results).

### Strict gates and the known-issues list

A percentage gate hides regressions: at a 99 % threshold, a new bug passes as long as it costs less than one question in a hundred. So every summary reports `known_failures` and `unexplained_failures`. A miss is *known* only if [`eval/known_issues.json`](../eval/known_issues.json) has a diagnosis for that exact question id. Today these are ambiguous-name questions in OpenStreetMap buildings, where the question names several spaces and nothing in it tells them apart (diagnosis: [parallel/benchmark-handoff.md](parallel/benchmark-handoff.md)). The gates fail on any unexplained miss. That file is an evidence log, not a mute button.

### Independent oracles

- `eval.differential` compares our route graph with the kit's own implementation on every building. `eval.sunday`, `eval.generated`, `eval.rules` and `eval.edits` measure our routes with that same implementation ([`eval/judge.py`](../eval/judge.py)), so a bug in our graph cannot hide itself.
- The differential check was mutation-tested: forcing `RouteGraph._opening_allowed` to return `True` made 116 rows fail ([JUDGING.md](JUDGING.md)).
- The kit's official evaluator on our agent (138/138 on dev):
  `PYTHONPATH=docs/industrial-agents-hackathon-2026 uv run python -m benchmark.evaluate docs/industrial-agents-hackathon-2026/data/dev --agent floorwise.agent.answer:answer`
- Full-coverage runs that are too slow for `fw check`: `fw eval generated --split train,dev,test --per-building 6` and `fw eval differential --split train,dev,test` (8,960/8,960 on all 280 buildings).

### Dataset audits (not gates)

- `uv run python -m eval.connectivity`: rooms with no way to the main part, by reason.
- `uv run python -m eval.overlaps`: rooms that overlap on one floor (drawn as a colour blend in 3D).
- `uv run python -m eval.audit_all [--limit N]`: one ranked table over all buildings, written to `docs/AUDIT_<date>.md`.
- `uv run python -m eval atlas`: closure fragility across the kit (single lifts, interior doors).
- `uv run python -m eval.orientation`: item facing calibration (see AGENTS.md rule 9).
- `uv run python -m eval scenarios`, `eval.sensitivity`, `eval.ccrp_gap 40`, `eval.demo_pick`: evacuation invariants, sensitivity to flow and occupancy, the gap to the CCRP heuristic, and the choice of demo building.

### Independent private corpus

`fw private generate|run|live|retire` adds new generated buildings with independently computed expectations, layout, style and language families kept apart, and a holdout frozen by fingerprint. These campaigns are separate from the fast gates and keep every automatic reconstruction failure visible. Protocol: [PRIVATE_VALIDATION.md](PRIVATE_VALIDATION.md). Results: [RECONSTRUCTION_VALIDATION_RESULTS.md](RECONSTRUCTION_VALIDATION_RESULTS.md).

## Protocol

From [`reports/Indoor wayfinding agent UX.md`](../reports/Indoor%20wayfinding%20agent%20UX.md):

- **Split by building.** Develop on train, select on dev. Test has no answers; only parse coverage is measured there.
- **Code graders first.** LLM judges are used only for the interaction rubric. Model grading does not replace human review.
- **Simulated users must be difficult:** ambiguity, typos, rooms that do not exist, changes of mind, terse users, wheelchair users.
- **Metamorphic checks where no gold exists:** a paraphrase gives the same parse; "avoid stairs" never yields stairs; swapping start and end gives the same length.
- **No test-set tuning.** Test strings never appear in code or prompts (AGENTS.md rule 2).

## Manual challenge pack

Use Hörsaalzentrum 024 and start a fresh conversation for each item unless it is a follow-up.

1. **Count and locate:** "How many 3D printers exist and where are they?" Then "There are five in Makerspace 0.08. Where are the others?" Expected: eight in total, five there, one each in Labs 2.02, 2.08 and 2.17.
2. **Remember accessibility:** "I'm in Lab 2.17 and use a wheelchair. Take me to Lab 4.26." Then "Close the lift that route uses and reroute from the same origin." Check the actual origin, the excluded lift and the step-free route, not just the prose.
3. **Change only the destination:** "Actually take me to Lab 2.02. Keep my requirements." The origin must not jump.
4. **Compound no-match:** "Find labs on floor 2 with at least two chairs and a projector..." No lab matches. The answer must not invent a destination.
5. **Rank and scope:** "Which room has the most chairs? Include ties, the building-wide total and a floor breakdown." Then "Now only the ground floor."
6. **Missing data:** "Find a free room for 50 people with a projector and tell me its opening hours." The data has no bookings, capacity or hours, and furniture counts are not seating capacity.
7. **Closure scenario:** "Simulate one exit being blocked. Show affected rooms, compare an alternative and preview a repair without applying it."
8. **Capacity:** "Assume 20 people are in Makerspace. Route them to exits while keeping a responder entrance available. Ask me for missing capacity assumptions before calculating."

During routes, try all four speeds, seek backwards, pause, change floors and reopen an earlier card. Preview motion never changes the declared location. Check keyboard-only use and reduced motion.

## Not covered by automated tests

- Three people who do not know the app should find equipment, navigate between floors and reroute around a closure without help. This has not been done.
- Physical phone motion, real audio, AR and VR headsets, and projector legibility need real hardware.
- Plan-import diagnostics report room and door precision and recall and exit-connected share separately. The largest connected component is not evidence of exit access.

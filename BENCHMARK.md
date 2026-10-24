# Benchmark run

One command, no manual steps between input and output.

## Required submission package (organizer update, 25 October 2026)

The repository's `SUBMISSION` folder contains **exactly** `BENCHMARK.md` and
`answers.json` (case-sensitive names). Regenerate it from the public test questions:

```bash
uv run fw submit
```

This computes answers from question text and building data, checks complete unique
question IDs, rejects unresolved answers, verifies structured route/answer agreement,
and copies this run guide into the package. It also regenerates the kit's earlier
`submissions/team_floorwise_test.csv` from those same answers. Logs and test reports
stay outside `SUBMISSION`. The answers are predictions: the public test set has no
released gold answers, so coverage does not establish test-set accuracy.

For an unseen Sunday building, use the supplied questions, without manual labels:

```bash
uv run fw bench <building_dir> <questions.json> SUBMISSION/answers.json
```

This replaces the public-test predictions with the supplied building's answers.
The JSON schema below describes our output; confirm any newly supplied organizer
schema before the final run. The announcement specifies filenames, not a JSON schema.

## Setup (once)

```bash
uv sync
cp .env.example .env   # add ANTHROPIC_API_KEY (only needed for wording the rule parser does not know)
```

## Run

```bash
# Sunday format: one building directory + a questions file -> answers
uv run --env-file .env run_benchmark <building_dir> <questions.json> <answers.json>

# Same, CSV output in the kit's submission format (question_id,answer)
uv run --env-file .env run_benchmark <building_dir> <questions.json> <answers.csv>

# A whole split (every building's questions.jsonl), e.g. the public test set
uv run --env-file .env run_benchmark docs/industrial-agents-hackathon-2026/data/test submissions/team_floorwise_test.csv
```

- **Questions file:** a JSON list, `{"questions": [...]}`, JSON lines or CSV.
  - Each entry needs an `id` (or `question_id`) and a text (`question` or `text`).
  - An optional `constraints` object (`{"step_free": true, "closed": ["Lift 1"]}`) is applied on top of what the text says.
- **`.csv` output:** `question_id,answer`. The answer is the full reply, ending in `Answer: ...`.
- **`.json` output:** `{"answers": [...]}`. Each entry has:
  - `id`, `kind`, `answer` (the committed answer line) and `reply`;
  - for routes and tours: `route` (the ordered spaces passed through, corridors crossed door to door included), `route_elements` (each opening, stair and lift used once), `legs` and `length_m`; `reachable: false` and the answer line `no route` when none exists under the rules;
  - for locate: `item_id` / `room_id`;
  - for numeric questions: `value`.

Without an API key, set `FLOORWISE_OFFLINE=1`. Every question in the known families is still answered (rules + exact solver). Only unfamiliar wording falls back to "unknown".

## How answers are computed

1. **Parse.** A rule parser handles the known question shapes for free. Claude (`claude-haiku-5-5`, structured output) parses new wording into the same `QuerySpec`.
2. **Link.** Room names, floors, item types and lifts are resolved to ids deterministically. If a name fits several spaces, each reading is solved, and the answer agreeing with most readings is chosen (ties go to the median value).
3. **Solve.** Exact geometry and graph search in `floorwise/core` compute the answer. The route model is the judges' (kit 1.1.0: door-to-door walking 15 cm off the walls, stairs 2 m per metre climbed, lifts 15 m + 1 m per metre, no way round the outside) and matches every expected answer to the centimetre. A route reply ends in `Answer: <ordered space ids joined by " -> ">`, which is how the judges read a route; rules stated beside the question (step-free / without stairs, closed places, forklift, production bays as destinations) are applied.
4. **Fallback.** Anything outside the known families goes to the tool-using Claude agent (`claude-opus-5-5`), which must finish with an `Answer:` line.

## Self-check

```bash
uv run python -m eval.routes  --split train,dev   # route model vs 2,130 warm-up answers   (100%)
uv run python -m eval.sunday  --split train,dev   # the judges' route scoring, replicated      (known misses only)
uv run python -m eval.generated --split dev       # new questions, kit router as oracle      (100%)
uv run python -m eval.rules   --split dev --limit 16   # every route rule as a property    (100%)
uv run python -m eval.solver  --split train,dev   # gold inputs -> solver -> official scorer (100%)
uv run python -m eval.parser  --split train,dev   # text -> resolved inputs vs gold          (100%)
FLOORWISE_OFFLINE=1 uv run python -m eval.e2e --split train,dev
```

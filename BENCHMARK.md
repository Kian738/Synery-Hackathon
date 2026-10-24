# Benchmark run

One command, no manual steps between input and output.

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
  - for routes: `route` (ordered space ids), `route_elements` (doors and connectors), `legs` and `length_m`;
  - for locate: `item_id` / `room_id`;
  - for numeric questions: `value`.

Without an API key, set `FLOORWISE_OFFLINE=1`. Every question in the known families is still answered (rules + exact solver). Only unfamiliar wording falls back to "unknown".

## How answers are computed

1. **Parse.** A rule parser handles the known question shapes for free. Claude (`claude-haiku-5-5`, structured output) parses new wording into the same `QuerySpec`.
2. **Link.** Room names, floors, item types and lifts are resolved to ids deterministically. If a name fits several spaces, each reading is solved, and the answer agreeing with most readings is chosen (ties go to the median value).
3. **Solve.** Exact geometry and graph search in `floorwise/core` compute the answer. The route model matches the dataset to the centimetre.
4. **Fallback.** Anything outside the known families goes to the tool-using Claude agent (`claude-opus-5-5`), which must finish with an `Answer:` line.

## Self-check

```bash
uv run python -m eval.routes  --split train,dev   # route model vs 2,130 warm-up answers   (100%)
uv run python -m eval.solver  --split train,dev   # gold inputs -> solver -> official scorer (100%)
uv run python -m eval.parser  --split train,dev   # text -> resolved inputs vs gold          (100%)
FLOORWISE_OFFLINE=1 uv run python -m eval.e2e --split train,dev
```

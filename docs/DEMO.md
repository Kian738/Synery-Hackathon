# Demo script (two minutes)

The video must be **120 seconds**, titles and end card included. Check the real media duration before uploading. Show the product in the first minute and how it works in the second. Do not spend the timed pitch waiting for model replies; cut or speed up waits in the edit.

## Before recording

1. `uv run fw doctor` (keys, kit data, web build), then `uv run fw check`.
2. Build the web app (`cd web && npm run build`) and start the server with the keys loaded: `uv run --env-file .env uvicorn server.app:app --port 8000`. Without `--env-file`, chat turns fail with a credentials error.
3. For the phone beat, start with `uv run fw start --lan` and pair before recording ([PHONE_DEMO.md](PHONE_DEMO.md)).
4. Open the building once and send one chat message. This warms the walk cache and the model client.

## Script

| Time | Say | Show |
|---|---|---|
| 0:00–0:10 | "Floor plans are drawings. Floorwise lets a visitor ask the building the way, and a facilities team ask what changes when something closes." | The 3D building turning, then the chat. |
| 0:10–0:35 | "I use a wheelchair. How do I get from Lab 2.17 to Lab 4.26?" | `proc-campus-dev-000`. The understood start, destination and step-free constraint, the route across floors, then **Guide me** with one decision card. |
| 0:35–0:55 | "Lift 3 is closed for maintenance. What changes?" | The closure and the new route via Lift 2. The agent keeps step-free without being told again. Recorded figures: 60.15 m via Lift 3, 73.00 m via Lift 2 ([JUDGING.md](JUDGING.md#demo)). |
| 0:55–1:20 | "Fire in an office, 502 people inside." | Open `/?demo=fire`. It switches to the prepared building and plays five narrated beats: the fire and the headcount, the evacuation flow, the bottleneck door, the responder route, and a door change that is solved again before it is shown. |
| 1:20–1:45 | "The model reads the request and explains. It never estimates a distance. Every number comes from deterministic code that follows the challenge's walking and stair rules." | An architecture slide (the diagram in the [README](../README.md#architecture)), then the gate table and the two files in `SUBMISSION/`. |
| 1:45–2:00 | "Plans can be rebuilt with one real dimension and reviewed. A paired phone shows the next step." | A short plan-import draft and the phone remote, if recorded beforehand. End on the building at 2:00. |

Use only results measured on the current revision. Say "computed", not "certified". Do not claim live positioning, hardware validation or fire modelling.

### The fire beat

- `/?demo=fire` starts the scenario by itself. The scenario lives in [`floorwise/demo_scenario.json`](../floorwise/demo_scenario.json): building `osm-way61408163`, fire in Office 0371 (ground floor), 502 people from seat counts, 3 floors. Everyone is out in 115 s with the exact plan, 245 s if everyone takes the nearest exit, and the checked door change brings it to 75 s. These numbers were chosen and measured by `uv run python -m eval.demo_pick`.
- To run it by hand on any building, open **Building tools → Fire test** and pick a room. **Building tools → Evacuation test** opens the per-person queue simulation with a time scrubber and a crowding heat map.
- Occupancy here comes from seat counts and is labelled as an estimate. The interactive Fire test asks for explicit occupancy and passage rates.

### Other strong shots

- **Closure impact:** `proc-factory-dev-003`, close the Office lift: 29 of 56 rooms lose step-free exit access, while 0 rooms are cut off for everyone (`tests/test_insights.py`).
- **Verified widening:** `proc-campus-dev-000`, Main lobby to Print room 0.16 for a step-free 1.1 m trolley. A hypothetical widening of door O0015 from 0.9 to 1.1 m is previewed without changing the model, and is only applied on request.
- **Counts without guessing:** "Which room has the most chairs?" gives the full ranking with ties. Counts are recorded items, not seat capacity.

## Fallback recording

PowerShell: `$env:FLOORWISE_CAPTURE_DEMO='1'; uv run fw ui-test --project=desktop demo.capture.spec.ts`, then reset the variable.

This writes `runs/demo/fallback.webm` and still images. The chat is scripted at the transport boundary, while the backend operations are real. It is not evidence of live Claude latency or voice. Rehearse live wording separately with `uv run fw test demo`.

## On-site checks

Check the laptop microphone and speakers, the browser permissions, projector contrast at 1080p, the local app and the API credits. Have one teammate who does not know the app follow the directions. Do not describe any of these checks as passed before doing them.

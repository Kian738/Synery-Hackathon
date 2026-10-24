# Three-minute demo and fallback

Before starting: `uv run fw doctor`, `uv run fw check`, `uv run fw ui-test`. Launch with `uv run fw start`. Use a local screen recording if network or model latency interferes. Do not claim live positioning or certification.

1. 0:00-0:15: "Floor plans are drawings. Floorwise makes the building answer questions and predict what a change will do."
2. 0:15-0:45: optional PNG ingest, one known real width, review the inferred draft, confirm activation. Generated plans work best. Keep a preloaded campus building for the main sequence.
3. 0:45-1:25: on proc-campus-dev-000 ask "I use a wheelchair. How do I get from Lab 2.17 to Lab 4.26?" Show the interpreted route, All floors, then Follow route. Start playback explicitly; use Next waypoint for a concise demonstration.
4. 1:25-1:55: "Lift 2 is closed for maintenance. What changes for my route?" Show the closed lift, previous-route ghost and recomputed route. Measured horizontal walking distance: 49.7 to 96.1 m.
5. 1:55-2:25: "Can a 1.1 m trolley reach Print room 0.16 from Main lobby?" The model proposes O0015 widening from 0.9 to 1.1 m and verifies connectivity. Apply to model. Explain that actual building work is still required.
6. 2:25-2:45: "Claude handles language. Deterministic geometry and graph algorithms compute every fact. We checked 7200 route comparisons against the official implementation."
7. 2:45-3:00: "For facilities, logistics and accessibility teams, starting with one building. Reconstructed plans are drafts for review."

Shock shot alternative: factory-dev-003, Office lift closure, 29/56 rooms lose step-free exit access.

## Capture

PowerShell: `$env:FLOORWISE_CAPTURE_DEMO='1'; uv run fw ui-test --project=desktop demo.capture.spec.ts`.

Output: runs/demo/fallback.webm and overview/first-person/closure/fix PNGs. This is a scripted deterministic fallback with real backend operations and no live model audio. Reset the environment variable afterwards. Rehearse live language separately with `uv run fw eval rehearse`.

## On-site checks

Check the laptop microphone and speakers, browser permission, 1080p projector contrast, local app availability, and API credits. Have one unfamiliar teammate follow the directions. Never describe these checks as passed before doing them. Recheck Sunday input schema when released; `fw bench BUILDING QUESTIONS OUT` handles JSON, JSONL and CSV.

## Visual-answer beat after the route demonstration

Ask “Which room has the most chairs?” Show the complete deterministic ranking, click the leading room to link it to the model and inset, and point out “Computed locally · no model tokens.” Counts reflect recorded assets; lecture seating rows are not inferred seat capacities. The updated opt-in recording captures this real deterministic chat answer after the route, closure and verified-fix sequence.

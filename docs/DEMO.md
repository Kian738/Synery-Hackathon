# Strictly two-minute demo and fallback

Before starting: `uv run fw doctor`, `uv run fw check`, `uv run fw ui-test`. Launch with `uv run fw start`; use `uv run fw start --lan` for the paired-phone showcase and follow `docs/PHONE_DEMO.md`. Pair and test before the timed pitch. Use a local screen recording if network or model latency interferes. Do not claim live positioning or certification.

Latest organizer announcement supersedes the earlier three-minute plan: the final
export must be **120 seconds**. Record and edit the product in the first minute and
architecture in the second. Do not spend the timed pitch waiting for model responses.

1. 0:00–0:10: “Floor plans are drawings. Floorwise lets a visitor ask the building where to go, and a facilities team ask what changes when a lift closes.” Show the preloaded campus.
2. 0:10–0:35: “I use a wheelchair. How do I get from Lab 2.17 to Lab 4.26?” Show the understood endpoints and step-free constraint. Open Tools → Route floors; start Guide me and advance one decision. “These are recorded rooms and computed directions. The start is set manually.”
3. 0:35–1:00: “Lift 3 is closed for maintenance. What changes for my route?” Show the closure and reroute via Lift 2. “The agent remembers step-free access and computes another route.” Cut to the verified widening preview: “Changes are reviewed before applying them to the model.”
4. 1:00–1:25: Show a simple architecture graphic or code: image/data → Building → deterministic geometry and route graph → tools → language/UI. “The model parses language and explains tool results. It never estimates distances or invents routes. We use the challenge's door-to-door walking and vertical travel rules.”
5. 1:25–1:45: Show the latest raw benchmark results and two-file SUBMISSION folder. “Tests check exact geometry, route validity, text parsing and interaction recovery. Public test answers are generated from the supplied data. The unseen building remains unseen.” Use only results actually measured for the current revision.
6. 1:45–2:00: Show a brief plan import draft and paired-phone control if already recorded. “Plans can be rebuilt with a real dimension and reviewed. A paired phone controls the view and instructions. This is a model-based guide; live positioning and physical-device validation remain future work.” End on Floorwise at exactly 2:00.

Keep the master export at 120 seconds, including titles and end card. Verify the
actual media duration with a media inspector before uploading; the automated fallback
below is raw footage, not an edited two-minute submission. The form also needs the
GitHub repository link and [technical explanation](SUBMISSION_TECHNICAL.md).

Shock shot alternative: factory-dev-003, Office lift closure, 29/56 rooms lose step-free exit access.

## Capture

PowerShell: `$env:FLOORWISE_CAPTURE_DEMO='1'; uv run fw ui-test --project=desktop demo.capture.spec.ts`.

Output: runs/demo/fallback.webm and overview/first-person/closure/fix PNGs. This is a scripted deterministic fallback with real backend operations and no live model audio. Reset the environment variable afterwards. Rehearse live language separately with `uv run fw eval rehearse`.

## On-site checks

Check the laptop microphone and speakers, browser permission, 1080p projector contrast, local app availability, and API credits. Have one unfamiliar teammate follow the directions. Never describe these checks as passed before doing them. Recheck Sunday input schema when released; `fw bench BUILDING QUESTIONS OUT` handles JSON, JSONL and CSV.

## Visual-answer beat after the route demonstration

Ask “Which room has the most chairs?” Show the complete deterministic ranking, click the leading room to link it to the model and inset, and point out “Computed locally · no model tokens.” Counts reflect recorded assets; lecture seating rows are not inferred seat capacities. The updated opt-in recording captures this real deterministic chat answer after the route, closure and verified-fix sequence.

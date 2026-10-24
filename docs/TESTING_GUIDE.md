# Product testing and judge readiness

The official weights are 55 correctness, 25 interaction, 10 creativity, 10 demo. The Lab reports evidence and coverage, not a promised jury grade. A pass on an old commit or one helper cannot prove live chat or a browser works. Kit 1.1.0 corrects route answers; public test questions have no gold labels. Do not call 145 parsed answers 145 correct answers.

## Commands

- `uv run fw check`: existing offline numerical/parser/property gates.
- `uv run fw test smoke`: focused contracts, then real desktop/phone UI with explicitly mocked model wording.
- `uv run fw test full`: unit tests, gates, independent area/centroid oracle, all-building wall checks, assisted import diagnostics and browser tests. A failed phase keeps a failed exit code while later phases still run.
- `uv run fw test live`: 24 distinct conversations, 3 regression repeats and 3 showcase conversations; real Chrome desktop/mobile viewports, real API/SSE and Claude. Three batches of ten; 300,000 model tokens per batch including grading. Every incomplete case stays in the denominator.
- `uv run fw test demo`: three complete live showcases on one server process. The default batch ceiling is 300,000 tokens; `FLOORWISE_BATCH_TOKENS` can lower it, never raise it.

The first four commands never claim physical-phone hardware coverage. Free product profiles disable actual provider clients. Inspect logs, full tool evidence, assertions, screenshots, language-review issues and budget outcomes in Lab → History. Current source fingerprints include uncommitted code and dataset/build identity. Source changes during a run make its evidence historical.

## Manual challenge pack

Use Hörsaalzentrum 024. Start a fresh conversation per item unless a follow-up is specified.

1. **Count and locate:** “How many 3D printers exist and where are they?” Then “There are five in Makerspace 0.08. Where are the others?” Expected: eight total; five there, one each in Labs 2.02, 2.08 and 2.17. Close the result, reopen it from chat, expand a room and return to room grouping.
2. **Remember accessibility:** “I’m in Lab 2.17 and use a wheelchair. Take me to Lab 4.26.” Then “Close the lift that route uses and reroute from the same origin.” Check actual origin, excluded lift and step-free route, not merely the prose.
3. **Change only the destination:** “Actually take me to Lab 2.02. Keep my requirements.” The origin must not jump to the lobby or the preview avatar.
4. **Compound no-match:** “Find labs on floor 2 with at least two chairs and a projector. Of those choose the largest and give a step-free route from Main lobby. If none match, say so.” No lab matches. No invented destination or unrequested substitution.
5. **Rank and scope:** “Which room has the most chairs? Include ties, the building-wide total and a floor breakdown.” Then “Now only the ground floor.” Pages must not limit totals or highlights.
6. **Missing data:** “Find a free room for 50 people with a projector and tell me its opening hours.” Booking, capacity and hours are unavailable. Recorded furniture counts are not seating capacity.
7. **Closure scenario:** “Simulate one exit being blocked. Show affected rooms, compare an alternative and preview a repair without applying it.” Check assumptions, actual affected IDs, no permanent edit and a visual result.
8. **Capacity stretch:** “Assume 20 people are in Makerspace. Route them to exits while keeping a responder entrance available. Ask me for missing capacity assumptions before calculating.” Supply a passage rate with units and choose a mapped entrance. Keep scenario-flow lines distinct from walking previews; inspect the assumptions and method limitations.

During routes try all four speeds, seek backwards, pause, change floors and reopen a prior card. Preview motion never changes declared physical location. Check keyboard-only operation and reduced motion. Interrupt a response and verify partial text, computed cards and the next question survive.

## Human acceptance

Three unfamiliar people must independently find equipment, navigate between floors and reroute around a closure without coaching. Record completion, wrong turns, hesitation, clarification count and comments. Physical phone motion/audio and projector legibility require actual hardware. Model grading and synthetic sensor events do not replace these checks.

## Known limits

Plan-import diagnostics use assisted calibration from known outline bounds. Report room precision/recall, door recall and entrance-connected share separately. A largest connected component is not evidence of exit access. Human walking validation is separate from official route costs, which ignore furniture. Unavailable/withheld previews must remain visible beside the number of validated previews.

Focused live diagnosis is available with repeated selectors, for example `uv run fw test live --case ambiguous_printer --case closure_impact --case availability`. This creates a separate subset run and never replaces the complete 30-case denominator.

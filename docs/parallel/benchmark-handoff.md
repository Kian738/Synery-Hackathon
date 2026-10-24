# Package B: benchmark failure diagnosis — READY

**Integration review:** the original proposal below pruned same-room readings. Codex rejected that assumption: repeated ambiguous mentions can legitimately denote the same space, and zero-length routes/distances must remain possible. The integrated resolver retains those readings while sampling the complete product evenly with a fixed bound. Regression tests now assert that repeated and unique same-room interpretations survive. Final gates remain 653/655 and 2124/2130 end to end, with all exact gates green. Sections below describe the package's original diagnosis/proposal where they discuss pruning; they do not override this final integration decision.

Status: **READY.** Result in one line: **there are no exact routing, geometry or parser failures in train+dev. Every miss is one of the eight known ambiguous-name misses, and in each the question text provably does not identify the hidden room.** Nothing was made to look solved. Two small generic ambiguity-handling changes were made in the owned files; they change no pass/fail count (details below).

Owned files touched: `floorwise/agent/spec.py`, `floorwise/agent/answer.py`, `tests/test_resolution_regressions.py` (new), this handoff. `floorwise/core/resolve.py` was read and **not changed** (nothing evidence-supported to fix there). `core/walk.py`, `routing.py`, `graph.py`, `scene.py` untouched.

## 1. Reproduction (before any change; `uv run fw eval … --split train,dev`)

| Suite | Result |
|---|---|
| routes (L0) | 2130/2130 |
| solver (L1) | 655/655 |
| parser, rules (L2) | 655/655 |
| e2e (L3) | **653/655** |
| e2e_basic (L3b) | **2124/2130** |

So all failures are the 2 + 6 = **8** known misses. Exact-failure categories, each checked: routing (`routes`, `differential`), geometry (`solver`, `metamorphic`), parsing (`parser`, `robust`): all at their gates with zero misses; the walkability and differential gates are unaffected.

## 2. The eight misses, and whether the language identifies the room

All eight are in OSM buildings that repeat names. Per-reading correctness was measured by solving every reading and scoring each against the dataset's scorer. **Gold was used only to report how many readings would have scored; it feeds no production decision.**

| Question | Kind | Mention (as asked) | Candidates | Readings that would score | Does the text separate them? |
|---|---|---|---|---|---|
| osm-way37850565-H03 | room_stacked | "Büro (Ground floor)" | 3 (refs 0.10, 0.11, 0.12) | 1 of 3 | No: only the shared name and floor appear |
| osm-way37850565-H04 | shared_walls_count | "Büro (Floor 1)" | 9 (refs 1.01-1.10) | 2 of 9 | No |
| osm-way37850565-Q08 | route (step-free) | "Büro (Ground floor)" to "Toilet 0.04" | 3 | 1 of 3 | No (the destination is unique and gives no hint) |
| osm-way37850565-Q09 | route with closure | "Büro (Floor 1)" to "Toilet 0.04" | 9 | 3 of 9 | No |
| osm-way37850565-Q10 | tour | "Büro (Ground floor)", "Büro (Ground floor)", "Büro (Floor 1)" | 3 x 3 x 9 (54 after pruning) | 4 of 54 | No |
| osm-way58216509-Q02 | route | "Generic room N2146" to "N2103" (Floor 2) | 2 x 2 | 1 of 4 | **No: both candidates have the same name and the same room number** |
| osm-way58216509-Q03 | route | "N2149" to "N2197I" | 2 x 2 | 1 of 4 | No (same) |
| osm-way58216509-Q05 | route (step-free) | "N2184" to "N2121" | 2 x 2 | 1 of 4 | No (same) |

Two kinds of ambiguity:

- **Büro (osm-way37850565): distinct room numbers, but not in the question.** The three or nine candidates have distinct `ref` values (0.10, 0.11, 0.12, and so on). The data could separate them; the questions never mention a number. Whoever wrote "Büro (Floor 1)" knew which one was meant; the sentence does not say. A user who wrote "Büro 1.05" would be resolved uniquely (tested).
- **Generic room N2xxx (osm-way58216509): indistinguishable copies.** In all six pairs checked, the two candidates have the same name, the same room number, the same type, the same floor, **centroid distance 0.0 m and intersecting polygons with areas within 0.2 m²**, and the same number of doors (2/2, 4/4, 1/1, 1/1, 2/2, 1/1). They are co-located duplicates in the supplied data that differ only in which neighbouring nodes their doors connect to. Nothing recorded about the rooms, and nothing in any question, can tell them apart. This is why the geometry-only questions about them (errand, shared walls, straight-line) pass in every reading while the routes differ.

This is information insufficiency, not a parser or resolver bug. I did not add a "prefer the reachable one", "prefer the shortest", "prefer the first id" or similar tie-break: such a rule would be a guess about how the questions were generated, tuned by looking at gold, which the rules forbid and which would not generalise to the unseen Sunday building. For comparison, picking one reading uniformly at random would score 8.4 of the 19 ambiguous train/dev questions; the current vote scores 11 of 19.

Exposure across splits (rules parser + resolver, counted without scoring): train has 18 ambiguous questions (7 benchmark-format, 11 warm-up), dev has 1 warm-up question, and the 145 public test questions have **0**. Ambiguity arises only in OSM buildings with repeated names.

## 3. Changes made (generic, evidence-supported, no change to any pass/fail count)

Both are in `resolve_spec_all` (`floorwise/agent/spec.py`):

1. **Two different mentions never denote the same space.** When a name fits several spaces, readings in which two slots collapse onto one room are dropped if any other reading remains: a route from a room to itself, a first-equals-second distance or door question, or two consecutive identical tour stops (a zero-length leg). Evidence: osm-way37850565-Q10 ("Starting at Büro, visit Büro, then Büro") previously included readings that started and "visited" the same room. If a mention is unambiguous and genuinely repeated, nothing is pruned (tested).
2. **No more cutting readings off after the first twelve.** The old code kept `readings[:12]` of the product, which pinned the *first* slot to the first candidate id (Q10 considered 12 of 81 readings, all starting at the same room). Now the readings are the full set up to 64, otherwise sampled evenly across all combinations (including the first and last), deterministically, without materialising huge products (9^9 combinations tested).

And in `floorwise/agent/answer.py`: an ambiguous answer's note now says "the question does not say which space it means … Treat it as a best guess", and `trace["ambiguity"]` lists each tied mention with its candidates, `ref` values, and which recorded properties could tell them apart (`differs_in`). This is diagnostic and display only and is never used to choose.

Effect, measured on identical gates before and after: e2e 653/655 → 653/655; e2e_basic 2124/2130 → 2124/2130; parser 655/655 → 655/655; every other suite unchanged. The only per-question difference is osm-way37850565-Q10: readings 12 → 54, still scored wrong (4 of its 54 readings would score). No result was newly passed or failed; the changes are about no longer discarding candidates arbitrarily, and about saying plainly that the answer is a guess.

## 4. Tests

`tests/test_resolution_regressions.py` (12 tests, none hand-label a test question; one uses a train fixture): unique mentions give one reading; a room number in the text settles a repeated name; every candidate is a reading when the text cannot separate them; two mentions of one name denote two spaces (route, tour, straight-line pairs); a single candidate named twice is left alone; sampling across the product is deterministic, not pinned to the first candidate, and bounded even for 9^9 combinations; an unmatched mention keeps its own error; the ambiguity report distinguishes "differs in room number" from "identical name and number"; the vote still prefers agreeing values; the train-building benchmark path reports the ambiguity and skips the note when a room number is given.

## 5. Verification

- `uv run fw check` (final, with Codex's concurrent changes in the tree): **exit 0**. 108 unit tests passed; routes 2130/2130; solver 655/655; parser 655/655 (train+dev) and 145/145 (test); e2e 653/655; e2e_basic 2124/2130; robust 630/630; metamorphic 898/898; walkability 160/160 (134 walkable, 26 withheld); differential 240/240. The 8 misses are unchanged and are the ones in section 2. (The 108 include this package's 12 tests, the 37 companion tests and Codex's own.)

## 6. Recommendations (not done, because they are outside the owned files or are product decisions)

- In chat, the existing ask-back path should offer the `ref` values when `differs_in` contains `ref` ("Which Büro: 0.10, 0.11 or 0.12?"). For identical-name-and-number duplicates, ask for a neighbour or a landmark instead of an id. `trace["ambiguity"]` has what the UI needs; `Session.place` was not touched (not an owned file).
- The scorer cannot reward honesty: the Sunday run must commit to one answer, and a hedged answer scores zero (kit `score.py`: only the committed `Answer:` line counts). Do not hedge to game it; the vote remains the best information-free policy.
- If duplicate co-located rooms turn out to be a systematic data artefact of the OSM conversion, that is a **dataset** property worth a note to the organisers; it is not something the resolver can repair.

# UX overhaul: audit and implementation record

2026-10-24. This audit concerns Navigator, not the internal Benchmark Lab. Source polygons, exact benchmark operators and graph penalties remain unchanged. Appearance is schematic; it does not claim a surveyed BIM model.

| # | Issue | Implemented behavior |
|---|---|---|
| 1 | Banner-like playback | Dedicated media dock with prominent play/pause and chapter controls |
| 2 | No progress | Seekable simulated-time timeline and instruction markers |
| 3 | Incorrect arrival action | Distinct arrived state, replay and finish; no landing button at arrival |
| 4 | Fixed speed | 0.5, 1, 2 and 4 times preview speed |
| 5 | Distance lost at vertices | Cumulative elapsed-time sampling, duplicate cleanup and preserved overshoot |
| 6 | Heading snaps / step rewinds | Continuous look-ahead, bounded quaternion rotation, independent instruction state |
| 7 | Wrong-floor route lines | Shared walking sections filtered by visible floors in both renderers |
| 8 | Unclear multi-floor toggle | Current / Route / Whole building scopes, assembled or exploded |
| 9 | Repeated 2D/3D switching | Linked expandable plan, focused on the current decision/preview position |
| 10 | Camera resets | Bounded camera-state cache and explicit Fit action |
| 11 | No location feedback | Confirmation, persistent green manual marker and optional facing direction |
| 12 | Real vs simulated position | Independent manual position, exploration floor and preview avatar |
| 13 | Competing directions | One current decision; complete itinerary in an expandable drawer |
| 14 | Overlay collisions | Reserved playback/inset/inspector zones, inspector hidden while guiding |
| 15 | Conversation clutter | Earlier turns collapsed; pending decisions remain accessible |
| 16 | Cramped mobile view | Full-stage guidance with one bottom player; map and questions open on demand |
| 17 | Disconnected selection | Linked room selection and contextual inspector; explicit Focus room animates framing |
| 18 | Unexplained door gaps | Oriented instanced frames and thresholds; passage/entrance distinctions |
| 19 | Connector teleports | Labeled landings and explicit transition curtain; no traversal through unknown interiors |
| 20 | Unenclosed interiors | Full supplied wall heights, interior ceiling, balanced lighting; overview remains open |
| 21 | Unrecognizable assets | Procedural furniture, printer, oscilloscope and supplied internal-stair silhouettes; muted irrelevant context |
| 22 | Coplanar artifacts | Display-wall union removes overlapping segments; deterministic floor depth layers |
| 23 | Truncated visual answers | Typed validated visual events, complete entity sets and session-scoped result pages |
| 24 | Missing analytics | Complete counts, per-room rankings/ties, AND content filters and area/count breakdowns |
| 25 | Expensive basic requests | Deterministic dispatch, small-parser fallback, relevant/deferred agent tools and per-turn usage |

## Question coverage

The planning audit inspected all 2,930 supplied question records across 15 families. Representative train/dev contracts now cover each family. No test-set answer labels were added or used to implement behavior.

- Locate/count: complete highlights and grouped lists.
- Route/step-free/closure/tour/errand: ordered, validated walking sections and explicit connector transitions.
- Largest room/floor totals: polygon areas, rankings and breakdowns.
- Shared walls: qualifying boundaries and adjacent spaces.
- Stacking: compared spaces on aligned separated floor slices.
- Straight-line 3D distance: blue measurement, explicitly distinct from walking.
- Reachability/delivery: reachable/unreachable result rows under deterministic constraints.
- Door what-if: proposed opening and before/after exit-distance rows; never applied implicitly.

## Evidence and limits

`fw check` passed 57 unit tests and all offline gates. `fw ui-test` passed 64 desktop/phone checks covering malformed streams, real deterministic chat, paging, floor scopes, reduced motion, seeking, arrival and replay. The pure playback checks compare equal elapsed time at 30/60/120 FPS, short edges and connector gaps. Live provider smoke tests exercise unfamiliar count wording and a closure with known deterministic impact. Generated screenshots are under `runs/ux-overhaul/`; API usage evidence is under `runs/ux-live-*.json`.

Compilation survey: all 280 buildings succeeded, with 175,456 display-wall segments in 11.11 seconds on this machine. This does not measure interactive FPS.

There is no supplied window geometry, seating capacity, booking/access feed, live positioning or surveyed stair-flight geometry. Existing internal-stair assets receive illustrative appearance only. Connector interiors use disclosed landing transitions; they are not claimed as validated continuous stair walks. Physical microphone quality, projector readability, target-machine FPS and uncoached human completion remain manual checks.

## Human acceptance script

Use three people who have not worked on Navigator. Give each the same three tasks without explaining the controls: find recorded equipment on a floor; reach a destination on another floor; recover after the relevant lift closes. Record completion, wrong turns, help requests and any mistaken belief that preview position is live tracking. Repeat the failed task after correcting the observed issue. These human trials have not been performed by the coding agent.

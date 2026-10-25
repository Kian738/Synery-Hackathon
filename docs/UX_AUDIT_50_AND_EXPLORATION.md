# Fifty interaction repairs and twenty contextual additions

This is a code-level audit of failures and interaction gaps, not a claim of fifty separately reproduced crashes. Every row names its repair. Numeric and provider contracts are checked separately from visual acceptance. Browser inspection is currently blocked by the saved localhost permission rule even after renewed user approval; new visual behavior must not be labelled browser-verified until that gate is cleared. No alternative browser channel was used to bypass it.

## Repair register

| # | Issue | Repair | Source |
|---|---|---|---|
| 1 | Rejected thinking signatures repeatedly poison follow-up questions | One bounded pre-generation recovery removes rejected reasoning only; user words and tool evidence survive | `floorwise/llm/loop.py` |
| 2 | Request schemas can drift when Tool objects are mutated | Snapshot advertised Claude schemas once per conversation | `floorwise/llm/loop.py` |
| 3 | Binding beta was checked at kwargs level, not the wire | Real SDK HTTP transport tests inspect the header for streaming and nonstreaming calls | `tests/test_chat_recovery_and_comparison.py` |
| 4 | A signature retry can duplicate completed tools | Retry only pre-text signature rejection in the request helper, never the tool loop | `floorwise/llm/loop.py` |
| 5 | Removing thinking-only content can leave an invalid empty assistant turn | Remove only newly empty assistant entries during explicit recovery | `floorwise/llm/loop.py` |
| 6 | All 400 responses could otherwise become retry loops | Unrelated schema/provider failures are never automatically retried by recovery | `floorwise/llm/loop.py` |
| 7 | Recovery adds empty answer bubbles | Hide empty assistant messages while retaining their stream identity | `web/src/navigator/Navigator.tsx` |
| 8 | The newest streamed answer can remain outside the scrolled panel | Follow the newest user turn and pin deltas only while the user remains near the bottom | `web/src/navigator/Navigator.tsx` |
| 9 | Thinking time looks like a frozen text stream | Report an explicit reasoning stage without exposing private reasoning | `floorwise/llm/loop.py` |
| 10 | First text latency is not measurable | Record first_text_ms separately from whole-turn time | `floorwise/agent/chat.py` |
| 11 | Reverse proxies can buffer text SSE | Send no-transform and X-Accel-Buffering headers | `server/app.py` |
| 12 | Idle network intermediaries can drop SSE while tools work | Emit comment keepalives without fabricating answer text | `server/app.py` |
| 13 | A truncated stream can look like a completed answer | Require the done event; preserve partial text and surface interruption | `web/src/lib/api.ts` |
| 14 | Parser errors can leave a reader and connection open | Cancel and release the reader on every exit path | `web/src/lib/api.ts` |
| 15 | A stopped older request can clear a newer request busy state | Only the active request owns completion and busy cleanup | `web/src/navigator/useNavigator.ts` |
| 16 | Stopping a turn leaves partial text labelled as still streaming | Mark only that request’s stream IDs interrupted immediately | `web/src/navigator/useNavigator.ts` |
| 17 | Continuous streamed events can bypass the overall deadline | Check the budget/deadline on every provider event | `floorwise/llm/loop.py` |
| 18 | Whitespace requests reach the provider | Validate trimmed nonempty text at the API boundary | `server/app.py` |
| 19 | Unlimited pasted text can overload the chat path | Apply a shared 12,000-character limit in composer and API | `server/app.py; web/src/navigator/Navigator.tsx` |
| 20 | The item type all fails deterministic ranking | Route all/everything to a complete all-type comparison | `floorwise/agent/session.py` |
| 21 | Whole-building versus ground-floor comparisons require repetitive tool calls | Provide both scopes from one indexed deterministic comparison | `floorwise/core/analytics.py` |
| 22 | Which has the most loses the previous item topic | Retain explicit item_context alongside the last visual | `floorwise/agent/chat.py` |
| 23 | Tied leaders can disappear behind ranking limits | Compute and retain every tied place, including in the complete comparison card | `floorwise/core/analytics.py` |
| 24 | A cross-item table can accidentally create a meaningless mixed-count heatmap | Comparison visuals do not assign incompatible item counts to one heatmap value | `floorwise/agent/session.py` |
| 25 | A long all-type answer is hard to scan | Filter the complete comparison table on the client, not just its first page | `web/src/components/ComparisonCard.tsx` |
| 26 | Computed comparison evidence cannot be exported | Export the complete table with spreadsheet-formula escaping | `web/src/lib/share.ts` |
| 27 | The one-line composer is poor for compound requests | Support multiline input with Enter send and Shift Enter newline | `web/src/navigator/Navigator.tsx` |
| 28 | IME Enter can submit unfinished text | Respect native composition state before keyboard submission | `web/src/navigator/Navigator.tsx` |
| 29 | A late building-load failure can overwrite the current building | Ignore errors from cancelled load generations | `web/src/navigator/useNavigator.ts` |
| 30 | A building with no floors crashes during initialization | Validate floor availability and offer retry/building selection | `web/src/navigator/useNavigator.ts` |
| 31 | Old routes, closures and cards survive while a new building loads | Clear per-building state at load start | `web/src/navigator/useNavigator.ts` |
| 32 | Late route failures can display options for the wrong building | Guard route failure responses with the building generation | `web/src/navigator/useNavigator.ts` |
| 33 | A rejected closure action causes an unhandled promise rejection | Surface actionable errors and preserve the current scene | `web/src/navigator/useNavigator.ts` |
| 34 | Double-clicking closure controls can issue duplicate mutations | Deduplicate pending closure requests by element ID | `web/src/navigator/useNavigator.ts` |
| 35 | A proposed door can be accepted twice while a mutation is pending | Deduplicate proposal acceptance by message ID | `web/src/navigator/useNavigator.ts` |
| 36 | Late geometry refreshes can replace a newer building | Apply edited geometry only to the originating session | `web/src/navigator/useNavigator.ts` |
| 37 | A late weak-point result can affect a newer building | Guard weak-point responses, errors and busy cleanup | `web/src/navigator/useNavigator.ts` |
| 38 | An outdated profile response can reapply old settings in the UI | Ignore cancelled profile-effect responses | `web/src/navigator/useNavigator.ts` |
| 39 | Result loading errors have no retry action | Add retry controls while retaining the originating answer reference | `web/src/navigator/Navigator.tsx` |
| 40 | Closing a visual card leaves unexplained answer highlights | Clear the card-owned highlights; reopening restores them | `web/src/navigator/Navigator.tsx` |
| 41 | A room inspector can describe a different selected floor | Dismiss stale room selection when exploration floor changes | `web/src/navigator/Navigator.tsx` |
| 42 | Phone, scenario and tool panels can survive a building change | Reset contextual panels with the building | `web/src/navigator/Navigator.tsx` |
| 43 | A shared route is only initialized once across building changes | Reset deep-link initialization per building and validate shared via stops | `web/src/navigator/Navigator.tsx` |
| 44 | Room areas are rounded to whole metres without need | Show one decimal place in the room inspector | `web/src/navigator/Navigator.tsx` |
| 45 | Only six room contents appear with no indication of omission | Provide a complete expandable contents list | `web/src/navigator/Navigator.tsx` |
| 46 | Static step mode skips the starting instruction | Clamp to valid indices including index zero | `web/src/navigator/Navigator.tsx` |
| 47 | Timeline markers are decorative and cannot seek | Make every chapter a labelled keyboard-accessible seek button | `web/src/components/GuidePlayer.tsx` |
| 48 | The new toolkit would allow keyboard focus to escape its modal | Trap focus, focus search first and restore the opener on close | `web/src/lib/dialog.ts` |
| 49 | Escape leaves room/map/phone inspection overlays open | Close transient inspection layers consistently | `web/src/navigator/Navigator.tsx` |
| 50 | Trackpad pinches over the model zoom the entire interface | Prevent browser Ctrl-wheel zoom inside the scene only; browser zoom elsewhere remains available | `web/src/navigator/Navigator.tsx` |

## Twenty additions

All additions use supplied data or personal device-local state. They stay in contextual drawers/cards rather than permanent scene overlays. Exterior tiles show mapped geography; no landscaping, exterior height or surveyed indoor alignment is fabricated.

| # | Addition | Access |
|---|---|---|
| 1 | Geographic exterior | Outside on OSM-sourced buildings |
| 2 | Neighborhood context | Outside → Surroundings |
| 3 | Exterior-to-interior reveal | Outside → Explore inside |
| 4 | All-item leader board | Tools → Find, save & share → equipment |
| 5 | Two-scope comparison | equipment → Whole building vs my start floor |
| 6 | Complete comparison filtering | Comparison card → Filter item types |
| 7 | CSV evidence export | Comparison card → Export complete comparison |
| 8 | Keyboard place finder | Ctrl/Cmd K |
| 9 | Equipment lens including oscilloscopes | equipment → select a recorded type |
| 10 | Saved places per building | places → Save place |
| 11 | Recently inspected places | places → Recently inspected |
| 12 | Room deep links | places → Copy room link |
| 13 | Shareable constrained itineraries | route → Copy route link |
| 14 | Locally generated room QR | places → Room QR |
| 15 | Ordered multi-stop planner | route → Visit places in order |
| 16 | Return-route preview | route → Preview return route |
| 17 | Landmark cue cards | route → Landmark cue cards |
| 18 | Recall practice using computed instructions | route → Practice this route |
| 19 | High-contrast interface | display → High contrast |
| 20 | Larger interface text | display → Larger interface text |

## Research and limits

- [Claude preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking): immutable prefixes and narrow invalid-binding recovery; text is streamed when the provider emits text, not during private reasoning.
- [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/): visible attribution, normal browser caching, no prefetch, configurable tiles and no assumed service guarantee.
- [OSM licence](https://www.openstreetmap.org/copyright): mapped-data attribution remains visible.
- [MapLibre](https://maplibre.org/maplibre-gl-js/docs/examples/display-a-map/): interactive map lifecycle and controls.
- Existing `reports/Indoor wayfinding agent UX.md` and `docs/UX_PLAN.md` guide landmark cues, reorientation and the restrained signage layout. Recall practice is an optional rehearsal aid, not a clinically validated memory treatment.

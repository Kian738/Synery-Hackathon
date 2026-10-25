# UX audit, October 2026 (control kit era)

Method: re-runnable inventory (`uv run python scripts/ux_inventory.py`), screenshots of the live app at 1440x900 and 390x844, a read of every interactive component, and the interaction rubric of the challenge (asks only what it needs, shows what it understood, gives directions a person can follow; voice counts). Findings are ranked by severity x how often a person meets them. Items marked (shot) were seen on screen; the rest come from reading the code.

## 1. What is on the kit and what is not
Inventory result (legacy utility-class tokens, outside Lab and the phone companion): Navigator.tsx 59, PlanView.tsx 8 (Lab 122, companion has its own CSS). Beyond that count, components styled by their own CSS classes in `styles.css` instead of the kit: room card (`.room-inspector`), "i" button (`.scene-info`), Welcome tiles, start picker, route card rows (`StepRow`), step mode, legend, visual answer cards, tool trace, comparison card, explore tools, scenario panel, build dialog, stress drawer.
On the kit already: stage chrome (view switch, Layers, Tools, camera dock, status pill), floor rail, header (building atlas, three icon toggles), composer, follow-up chips, jump-to-latest, route "Now / Next" card.

## 2. Findings, ranked
| # | Severity | Finding | Where | Fix (plan step) |
|---|---|---|---|---|
| 1 | High | The start picker is the most visible leftover: square input, square outlined chips, a label stack with no hierarchy (shot) | `StartPicker` | rebuild: kit search field, rounded rows with floor dots (4) |
| 2 | High | Welcome is six square tiles plus a heading; people have to read a block of text to know what to do first (shot) | `Welcome` | 3 contextual starter chips, "Things you can say" as popover (3) |
| 3 | High | Clicking a room opens a boxy card with unequal buttons; "Go here" and "I'm here" look like a different product | `RoomCard`, `.room-inspector` | kit popover anchored to the room, bottom sheet on phone (4) |
| 4 | High | Directions are one long paragraph per step; landmark, turn and distance are mixed in one sentence | `instructions.py`, `RouteSign` | leg list: verb + landmark + distance, floor change as its own leg, short/detailed (2) |
| 5 | Medium | The "i" info button is a lone old-style control in the corner | `.scene-info` | kit icon button + popover (4) |
| 6 | Medium | Answers do not show how the question was understood (start, constraints, resolved room), so a wrong reading is invisible until the route looks odd | `Conversation` | "Understood as" chip row under every answer, chips editable (3) |
| 7 | Medium | Result cards (visual answer, comparison, results links, ranking) have four different headers, paddings and paging controls | `VisualAnswer`, `ComparisonCard`, `TurnResultLinks` | one card component (3) |
| 8 | Medium | Tool activity, response time and usage live in two different places (`ToolTrace` and the footer line) | `ToolTrace`, `.turn-usage` | one quiet line per turn that expands (3) |
| 9 | Medium | Plan view controls and hints are old-style and differ from the 3D camera dock | `PlanView` | kit dock (4) |
| 10 | Medium | Options ("Which one do you mean?") and change cards use square buttons and dashed borders | `Conversation` | kit buttons, before/after impact line (3) |
| 11 | Low | Legend is a permanent block, not on demand | `Legend` | key popover under Layers (4) |
| 12 | Low | No loading choreography: a plain text line while the building loads | `Suspense` fallback | `Loader` (6) |
| 13 | Low | Lab and phone companion look like another app | `lab/`, `companion.css` | tokens (5) |

## 3. Interaction rubric check
- Asks only what it needs: good (ask-gate in `Session.place`; start defaults to the main entrance). Gap: when it does ask ("Which one do you mean?") the choices are buttons without context (floor, distance); add both (3).
- Shows what it understood: partial (route card names start and destination). Gap: constraints and resolved names are not shown for non-route answers (6).
- Directions a person can follow: partial; see 4.
- Voice: speak/listen work; reads the long step text. Gap: read the short leg text, not the paragraph (2).
- Accessibility: kit controls are 40 px with names; leftovers are smaller and unnamed in places; axe sweep to run per step.

## 4. Measures to track (before -> after, re-run each step)
Legacy tokens outside Lab/companion (67 now, target 0), clicks from load to first route (toilet: 1 tile click now, keep), words in the first-screen panel (~45 now, target <= 25), axe violations per screen, controls under 40 px (count), steps of an instruction paragraph over 18 words (now: arrive legs up to ~30).

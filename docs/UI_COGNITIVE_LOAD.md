# Cognitive load: how the scenario UI applies the organisers' brief

The organisers judge UI/UX on reduced cognitive load and pointed to
[Design Principles for Reducing Cognitive Load](https://lawsofux.com/articles/2015/design-principles-for-reducing-cognitive-load/)
(Laws of UX, 2015). Its seven principles, each with what it means for the evacuation and findings views. A reviewer can
check every row by looking at the screen.

| Principle (the article's wording) | Rule for the scenario UI | Check |
|---|---|---|
| Avoid unnecessary elements ("less is more") | One headline sentence per result (for example "Everyone is out in 155 s; 13 people start inside the hazard"). Everything else sits behind one disclosure. | At first sight the screen shows the headline, the building, and one next action. |
| Leverage common design patterns | Play, pause and a seekable timeline for the simulation; a legend; click a room to set the hazard. No new gestures. | No control needs an explanation. |
| Eliminate unnecessary tasks | Defaults fill what the dataset cannot give (occupants = seat count, labelled "estimate"; responders = every usable entrance). The person never types a width, rate or time to get a first answer. | A first result needs one click: the hazard room. |
| Minimise choices | `elicit.next_question` asks one question at a time with 2 to 4 options, only for what is missing. Findings show the top three, most serious first. | Never more than one open question; never more than three findings before "show more". |
| Display choices as a group | The audience (occupant, safety officer, builder, regulator) and the capacity meaning (rate or total) are shown as one visible set of options, never hidden in a menu. | All options of a choice are visible together. |
| Strive for readability | Plain words; units always attached; the same word for the same thing ("exit", not exit/egress/door-out). Status is text plus icon, never colour alone. | Contrast at least 4.5:1 on the projector; no jargon on the headline line. |
| Use iconography with caution | Every icon has a text label. Only universally understood icons (play, pause, close) stand alone. | No icon-only button except those. |

## Reasoning chain, shown without load
The nine plan steps (hazard, people, exits, evacuation, bottleneck, responders, door candidates, door fix) are the
evidence, not the interface. Show them as a single collapsed line "9 steps checked" that expands into the step list; each
step is one sentence with its number. If a step abstains, show only that step, named, with its reason.

## Findings
`floorwise.reason.findings.assess(trace, audience)` returns findings ordered blocker, risk, improve, info. Each has a title
(one line), a detail, the trace step it comes from, and, only when a re-solve proved it, a suggestion. Show the suggestion
as a single button ("Apply to model") next to its finding, never as a list of alternatives.

## Not in scope
Phone and voice flows follow Kian's own guidance in `docs/UX_AUDIT.md`.

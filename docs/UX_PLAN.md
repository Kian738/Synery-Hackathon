# UX plan

Sources: `reports/Indoor wayfinding agent UX.md` (research), the official frontend-design skill, and the challenge rubric. Every decision below names its reason.

## Brief

- **Subject:** wayfinding inside industrial buildings: factory halls, labs, campus blocks.
- **Audience:**
  - a first-day visitor who knows no room names;
  - a wheelchair user;
  - a technician with full hands;
  - a facility manager;
  - plus the jury, who run scripted tricky conversations and watch a 3-minute demo.
- **Primary job:** get a person to the right place with directions they can follow, and show them it understood.
- **Second surface:** the Benchmark Lab, for us. It is dense and data-first.

## Visual direction: "the building's own signage"

The UI should look like part of the building's sign system, not a SaaS dashboard. It merges three ideas:

- **Signage** for directions: sign panels, pictograms, arrows, strong type.
- **Architect's drawing** for the plan: a light ground with ink-line rooms and no decorative fills.
- **Transit map** for the route and floors: the route is the hero line, and floors are stops on a vertical line.

### Tokens

| Name | Hex | Use | Why |
|---|---|---|---|
| Concrete | `#E6E8E6` | app ground, plan floor | cool concrete grey of hall floors (deliberately not the warm-cream AI default) |
| Ink | `#1C2226` | text, plan lines, sign panels | drawing ink / sign background |
| Marking yellow | `#F5C400` | the route (with an ink casing), the current step | factory floor-marking tape (RAL 1003-like); 3:1 contrast comes from the ink casing |
| Escape green | `#1E7A4C` | step-free, exits, "done" | ISO 7010 safe-condition green |
| Signal red | `#C8102E` | closed, blocked, destructive | prohibition red |
| Mandatory blue | `#0B5394` | focus rings, links, interactive accents | ISO 7010 mandatory blue |

Neutrals are tints of ink and concrete. Zone fills are limited to 5 (circulation, workshop and hall, office, lab, service), always paired with a text label (NHS signage guidance: colour is secondary to text).

### Type

**Barlow** for everything (Google Fonts). It is a grotesk with DIN-like proportions, modelled on highway signage.

- **Barlow Semi Condensed** at 600/700 for sign-panel text and destinations.
- Regular Barlow at 400/500 for body text.
- Two weights for content, bold for the destination (signage guidance).
- Tabular figures for metres and scores.
- No monospace labels, no all-caps eyebrows, no "→" decorations (generic tells to avoid).

### Layout: Navigator

Desktop (≥ 1024 px):

```
┌──────────────── sign column (ink) ───────────┬──────────── plan (concrete) ─────────────┐
│ Building ▾   ● Step-free  ● Voice            │  floor rail   ┌────────────────────────┐ │
│ ┌──────────────────────────────────────────┐ │   F2 ●        │                        │ │
│ │ ROUTE HEADER (sign panel)                 │ │   F1 ●━━┓     │   ink-line plan,       │ │
│ │ Kitchen 0.28 ▸ Quality lab 0.21           │ │   EG ●━━┛     │   yellow route,        │ │
│ │ step-free · 36 m · 1 floor                │ │               │   pins for mentions    │ │
│ ├──────────────────────────────────────────┤ │               └────────────────────────┘ │
│ │ ① ↰  Leave by the door to the corridor    │ │  [+][−][⌖]  pan/zoom buttons (WCAG 2.5.7) │
│ │ ② ↑  Past the CNC mill to the lifts       │ │                                           │
│ │ ③ ⇅  Lift B up to Floor 1, exit right     │ │                                           │
│ │ ④ ◉  Quality lab 0.21 on your left        │ │                                           │
│ └──────────────────────────────────────────┘ │                                           │
│ conversation (latest turns)                  │                                           │
│ [Toilets][Coffee][Exit][Meeting rooms]…      │                                           │
│ [🎤  Where do you want to go?          ][↵]  │                                           │
└──────────────────────────────────────────────┴───────────────────────────────────────────┘
```

Mobile: the plan is on top (≈45 %), with a bottom sheet holding the header, steps and composer. "Step mode" turns it into one big step at a time with next / repeat / back.

### Layout: Benchmark Lab (`/lab`)

The same tokens, compact density, a concrete ground with ink tables. It has no sign column: a left nav with Overview, Runs, Run detail, Compare, Dataset, Interaction and Build.

### Principles

1. **The route is the one bold thing.** Everything else is quiet ink on concrete.
2. **Text first, colour second.** Every colour-coded thing also has a label or a pictogram.
3. **Show what was understood, every time:** the route header echoes resolved start, destination, floors and constraints, and the map pins every mentioned place.
4. **One step equals one decision.** Steps happen only at turns, doors into new areas and floor changes. Each has one landmark and the room number only on arrival.
5. **Nothing moves unless the user acted.** The exception is one orchestrated moment: the route drawing in.

Review against generic defaults: no warm cream, no single acid accent on near-black (the dark element is the sign column and has three ISO-meaning colours), no identical rounded cards (sign panels are square-cornered, steps form a list, not cards), no mono labels, no gradients. Corner radius: 2 px for sign panels (signs are square), 6 px for inputs and buttons only.

## Interaction protocol (agent plus UI)

Each rule comes from the research report (sources there).

1. **Resolver outcomes:**
   - One match: act.
   - 2–4 matches that lead to different routes: ask one closed question with chips and numbered map pins.
   - Several matches with the same answer (same room): don't ask.
   - No match: show the nearest real candidates and never invent one.
2. **Ask-gate:** at most one clarification round per request. Never ask for something already said or on screen.
3. **Answer-first:** every route opens with the header (resolved names, floors, constraints, length, floor changes).
4. **Directions:** turns and decision points only. Straight runs are merged. Each turn gets one salient landmark (machine or equipment near the decision point). A floor change is its own step: mode, direction, floor, exit turn. The room number confirms arrival. Spoken overview: at most 4 segments.
5. **Needs are remembered:** "wheelchair", "no stairs" or "pallet 1.2 m" become a removable chip. They apply to every later route and are stated in the header. Never silently fall back to stairs; say "no step-free route exists" and offer options.
6. **Changes:**
   - Closures apply immediately with a consequence summary (which rooms lose step-free access).
   - New doors: map diff preview, then Apply or Discard, then a receipt with Undo.
7. **Voice:** push-to-talk, a text echo of every spoken line, step mode (next, repeat, back, stop), and the destination echoed back ("Quality lab 0.21. Starting.").
8. **Start point:** "I'm at" pill set by tapping the map, choosing an entrance, or a QR (`?at=<space>`). The agent asks "what can you see?" only if the start is needed and unknown.

## Build order

1. Design tokens plus the app shell (Vite, React, Tailwind v4, Radix primitives as needed), plan renderer v2 (ink lines, zones, pins, route casing, pan buttons).
2. Navigator: sign column, route header, steps list, conversation, category chips, needs chips, step mode, voice.
3. Backend: deterministic instruction planner v2 (chunking, salience, floor-change steps) and an ask-gate in the resolver and tools; agent prompt aligned with the protocol.
4. Benchmark Lab:
   - P0: runs table with CI and cost; per-item drill-down with trace and route on plan; slicing.
   - P1: compare runs; launch runs from the UI with live progress.
   - P2: interaction transcripts with judge verdicts; build overlay.
5. Playwright flows for both surfaces and screenshot review at 1440 px and 390 px.
6. Stretch: QR-seeded WebXR glance-AR (Android Chrome) with a 2D/compass fallback, isometric stack view.

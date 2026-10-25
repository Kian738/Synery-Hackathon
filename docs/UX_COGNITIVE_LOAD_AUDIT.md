# Cognitive-load audit — 25 October 2026

Scope: Navigator first use, location selection, destination choice, route guidance,
secondary tools, request recovery, and submission readiness. Reviewed current source,
existing desktop/390 px tests, and the running first-use screen at 1280 × 720 before edits.
This is an expert inspection, not an uncoached usability study.

Reference: [Design Principles for Reducing Cognitive Load](https://lawsofux.com/articles/2015/design-principles-for-reducing-cognitive-load/).
The article recommends removing unnecessary elements and tasks, familiar controls,
fewer simultaneous choices, grouped alternatives, readable content, and text beside icons.

| Priority | Finding and evidence | Consequence | Decision / acceptance check |
|---|---|---|---|
| P1 | Default main entrance is selected without a user declaration; green floor marker says YOU and map pin says “You are in”. | A visitor may interpret an assumed route origin as measured location. | Disclose the entrance default beside the origin; use “Start” markers. Preserve one-tap routing and manual/QR starts. |
| P1 | Desktop toolbar simultaneously shows Phone, floor scope, Stress test and Evidence; mobile hides these behind an unlabelled ellipsis. | Optional tasks compete with finding a destination; mobile requires interpreting an icon. | One labelled Building tools disclosure on both sizes; keep map and view switching visible, and keep all secondary choices together. Verify keyboard access and phone pairing. |
| P1 | StartPicker silently returns only eight substring matches, ignores floor names, and treats leading spaces differently from empty input. | Repeated names are hard to distinguish; users cannot tell that the desired result was omitted. | Normalized room/reference/floor search, floor labels, explicit match count and “keep typing” hint. Verify duplicate names and no-match recovery. |
| P2 | Six destination categories and three full-sentence examples appear together; examples scroll beneath the fold at 720 px. | Competing reading tasks before a first action. | Preserve familiar destination grid; put the complete example group behind labelled disclosure. Keep examples derived from actual building data. |
| P1 | Phone screenshot shows the first destination labels below the composer: the stage and welcome heading consume the available height. | Primary navigation needs scrolling before it is discoverable. | Use a 34vh stage only on first use, smaller welcome type and compact labelled destination rows. Assert the last shortcut is above the composer at 390 × 844; guidance retains its existing layout. |
| P2 | Route already shows one decision, optional full itinerary, and one primary guidance action. | Good existing hierarchy. | Preserve; regression-test route echo, floor changes, accessibility and guidance. |
| P2 | Composer has progress and Stop; interrupted replies retain computed results. | Existing recovery reduces waiting uncertainty. | Preserve; run timeout, interruption and subsequent-request regressions. |
| P0 | New organizer requirement is SUBMISSION/BENCHMARK.md and SUBMISSION/answers.json; current fw submit only writes the old CSV. | Correct answers could be ungradable due to packaging. | Generate and validate exact two-file package, complete unique test IDs, nonempty answers and consistency with legacy CSV. Keep evidence outside SUBMISSION. |
| P0 | docs/DEMO.md plans three minutes; latest organizer announcement requires strictly two minutes. | Submission may violate the video requirement. | Replace with a 120-second script and separate technical explanation. A script is not a submitted or duration-verified video. |

Deferred: physical phone/microphone/projector checks and an unfamiliar person's navigation
test require hardware or a participant. 3D illustration accuracy and plan reconstruction
quality are separate from usability and must retain their existing disclosures. Automated
passes do not predict the jury's score, and test-set answers have no public gold labels.

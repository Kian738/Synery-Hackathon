# Navigator second-pass review

2026-10-24. The previous audit's implemented labels did not establish that the interaction was good. The supplied screenshots exposed real layout and navigation regressions. This pass changes those behaviors and captures the reported CIT route on desktop and phone.

## Changes and their purpose

- Guide me occupies the scene. Building selection, itinerary, floor rail and room inspector no longer compete with the current instruction. Ask and Map are explicit optional drawers.
- One player contains the decision, repeat, seek, elapsed/total simulated time, chapter navigation, play/pause/replay and speed. The slider and keyboard operate the same timeline. Arrival has no stair action.
- Selection does not reframe the model. Focus room and Fit explicitly animate framing; dragging cancels the animation. Pan is the default mouse gesture, with an explicit rotate mode and right-drag rotation.
- A pointer gesture remembers whether it ever crossed the drag threshold, even if it returns to its origin. Such gestures cannot select rooms. The SVG uses pointer capture and makes its own pan/selection decision.
- Connector labels are small fixed-size icons, limited to the active route or selection and current floor. Dense plan labels use collision exclusion and a screen-space area threshold.
- The linked plan is absent until opened. On desktop it reserves scene width; on phones it opens above the player. Panning suspends avatar centering until Follow preview is pressed.
- Manual location uses a green marker; simulated progress uses a yellow arrow. Duplicate route-start and instruction pins are suppressed where they obscure these markers.
- The route is opaque raised geometry with ordinary depth testing. The overview uses a larger near plane and a tighter far plane to improve depth precision. It is not drawn through walls.
- Active decision door frames are highlighted. Interiors keep ceilings; they have no distracting ceiling switch.
- All 96 supplied asset types have bounded procedural silhouettes, rendered in instanced shape batches. Equipment appearance and vertical dimensions remain illustrative.
- Repeated tool calls form one expandable evidence group per conversation turn, with inputs, computed output summaries and errors. This exposes the computation trace, not private model reasoning.
- The stress-test panel says exactly what is computed: independent connector-closure impact on step-free exit reachability. It includes the assumptions and does not imply a crowd/fire simulation.

## Research and limits

[W3C supported wayfinding guidance](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o7p06-supported-wayfinding/) supports recognizable cues and opportunities to reorient. That motivates one decision at a time, visible doors, optional plan context and replayable spoken instructions. It does not establish that continuous first-person animation is best for everyone. Reduced-motion users retain manual chapter navigation.

[W3C device orientation](https://www.w3.org/TR/orientation-event/) requires attention to secure contexts and permission. A phone gyro can control viewing direction; it does not establish the user's location. Same-network HTTP touch control and HTTPS sensor control need distinct readiness feedback. Physical device permission, latency and stability must be rehearsed before the jury demo.

[NIST evacuation-model verification and validation guidance](https://nvlpubs.nist.gov/nistpubs/technicalnotes/NIST.TN.1822.pdf) provides the right boundary for the proposed emergency scenarios: a graph exercise is not a validated human evacuation model. Door throughput requires units, occupants require supplied scenario inputs, and responder/evacuee interaction needs explicit assumptions. The outstanding capacity question must be settled before implementing an optimization with that number.

The supplied geometry does not specify surveyed stair flights, risers or travel direction. The app continues to show explicit landing transitions rather than animating an invented traversable flight. The catalogue's stair-shaped objects are illustrative assets, not validated walking surfaces. Continuous stairs remain incomplete.

There is no claimed universal Google-style indoor route-line standard here. Pictograms accompany accessible names; color accompanies shape, text and state. We do not claim ISO certification for the custom icon set.

## Evidence

`runs/ux2/` contains desktop and phone captures of the reported CIT route and its optional map. New regressions cover pointer intent, dense labels, full-stage playback, real CIT route availability and grouping ten repeated calls. The first targeted run passed 70 checks and identified two stale test selectors for the renamed stress-test panel; these were corrected before the full rerun.

Physical microphone/phone sensors, projector readability and the three unfamiliar-user trials still require people and hardware. No result from those trials is claimed.

# Backlog

## Next up: review of 2026-10-24 (everything asked for that is not done yet)

The route-rule change from Synera (kit 1.1.0) took priority, so these are written down instead of half done. Status: **todo** = nobody has started; **codex** = the other agent's working tree already contains a start (RoomText, roomMentions, floor-slab tests); check `git status` before touching the same files.

### Benchmarks and evaluation
- **todo**: independent oracles for the geometry kinds (largest room, area totals, shared walls, stacking, 3D distance) written from the README definitions, compared on all buildings; today they are verified against gold (655/655) and metamorphic invariance only.
- **todo**: wording robustness beyond perturbations: run the paraphrase and LLM-parser suites on Claude again with the new rule fields (forklift, bays, closed places, avoid) and add rule-bearing question variants to `robust`.
- **todo**: confirm the five open interpretations in `docs/REQUIREMENTS.md` with Synera on site (without stairs, forklift aisle, production bay, rules on errands/tours, answer format on Sunday); then promote them from "assumed" to "verified".
- **todo**: run `generated` and `rules` on the whole of train, dev and test nightly (about 15 minutes) and chart the trend in the Lab.
- **todo**: Lab: show known versus unexplained misses and the known-issues evidence next to each run.

### Chat and AI engineering
- **codex**: room, floor and item mentions in chat replies become links that highlight and select them (`RoomText.tsx`, `roomMentions.ts`).
- **todo**: tool calls shown properly again (name, arguments in plain words, result summary, errors) in the chat transcript.
- **todo**: select several components (for example "5 3D printers") and highlight exactly those in the 3D view and the plan, from chat and from the scene, with a list that mirrors the selection.
- **todo**: chat intelligence pass: use the deterministic dispatcher for everything it can answer, ask back only on real ambiguity, say what was understood, keep answers short with links, and add an eval for each of these behaviours.

### Rendering and look
- **todo**: stairs, lifts and connector interiors drawn at their real sizes (footprints and floor heights from the data) instead of illustrative blocks.
- **codex**: roofs and ceilings where there should be none (TUM CIT atrium), z-fighting and flicker between floor slabs, coplanar walls.
- **todo**: colour language for navigation: one colour per room kind (bathrooms, kitchens, labs, offices, stairs and lifts, production bays) used in the plan, the 3D floor tint, chips and chat links, always paired with an icon and a word; accessible in light and dark.
- **todo**: use the extra data we have (room type, area, assets, door widths, step-free) as additional senses: sound cues for floor changes, haptics on the phone, and a legend that explains the colours.
- **todo**: something other projects do not have: a "what changes if" visual (closure ghost routes, door-width what-if heat) as a first-class 3D view, and an evidence atlas as a hero screen.

### UX consistency
- **todo**: guide player controls (the 2x / 4x speed menu): replace the native dropdown (white text on white background in legacy Chrome) with the same segmented control used elsewhere; one component set for all buttons, selects and chips.
- **todo**: audit light and dark mode on every screen with screenshots at 1440 and 390 px, and fix tokens so no control depends on browser defaults.

# Later work: positioning, AR and others

Ordered by value for the jury and by effort. Sources are in `reports/Indoor wayfinding agent UX.md`, section 5.

## Knowing where the user is

| Approach | Accuracy | Works in a browser? | Effort | Verdict |
|---|---|---|---|---|
| **QR code at doors and entrances** (`?at=<space id>`) | exact, at the scan | yes, on every phone | hours; deep links already work | **do first** |
| Tap "I'm here" on the plan / start picker | exact | yes | done | done |
| **BLE beacons** (trilateration on signal strength) | 2–5 m | Chrome on Android only, behind a flag; never on iOS Safari | days, plus hardware | native app only |
| **WiFi RTT / fingerprinting** | RTT 1–2 m; fingerprinting 3–5 m | **no**: browsers expose no WiFi scans; iOS apps can't read WiFi signal strength | survey per building | native Android app only |
| Visual positioning (camera matches a prior scan: MultiSet, Immersal) | under 0.1 m | MultiSet WebXR, Android only | needs the building scanned first | for a pilot site |
| Pedestrian dead reckoning (phone motion sensors) | drifts a few % of distance | yes (DeviceMotion) | medium | only to carry position between QR scans |
| Visual-inertial "SLAM" | very good locally, drifts globally | provided by ARCore/ARKit inside WebXR on Android | comes with AR | use it between QR scans |

**The honest answer to "BLE and WiFi SLAM":** a web app can't see WiFi networks at all, and Bluetooth scanning only works experimentally on Android Chrome. Both need beacons or a site survey per building. In the browser, the realistic stack is:

1. a QR scan at a door, which gives an exact position;
2. ARCore's own motion tracking, which follows the phone between scans;
3. another QR scan when the route passes a door, to correct drift.

BLE and WiFi are for a native-app phase with the site owner, who installs the beacons and does the survey.

## AR route overlay

The base is in place: `web/src/components/Building3D.tsx` renders the building in metres (x east, y up, z = −north). An AR session places that same scene at the scanned door.

1. **Android Chrome:** WebXR `immersive-ar` with `local-floor`, a hit-test and a DOM overlay.
   - When the session starts, align the plan with the QR door's position and the wall direction.
   - Draw floor chevrons every metre along the route, plus a destination pin.
   - Ask for a re-scan when tracking is lost.
2. **iPhone:** iOS Safari has no WebXR `immersive-ar`. Fall back to the 2D plan with a compass arrow (DeviceOrientation), or use an App Clip (e.g. Needle Go) later.
3. **UX:** AR only at decision points ("raise the phone at the junction"), never for walking with the phone held up (research: less spatial memory, battery drain).

## Other items

- **Several buildings:** join `building.json` files with outdoor walkway edges between their entrances (graph change only).
- **Live map updates:** "this machine is now in 0.21" works through `move_item`. Barcode or RFID input could call the same endpoint.
- **Forklift / wide loads:** min door width and step-free are in place. Add aisle blocking per hall zone (close a space or opening) from the UI.
- **Floor plans from real scans:** Raster2Seq (MIT, CubiCasa5K checkpoint) as a fallback for non-generated plans, on a Linux GPU, timeboxed.
- **Voice:** server-side ElevenLabs TTS, or Groq Whisper for speech-to-text, to replace the browser APIs.
- **Lovable:** the code you were given (`COMM-INDUSTRIAL-QHYD`) looks like a credit/promo code, not an API key. Redeem it on lovable.dev. Lovable then works on this repo through GitHub sync: prompt in Lovable, then pull. It uses the same stack (Vite + React + Tailwind).


## Current implementation audit (25 October)

Supersedes earlier todo labels where they conflict: normal chat is Claude-first; token-free dispatch is not the product policy. Streaming and result reopening are implemented and covered by offline transport/UI contracts. Speed choices are visible segmented buttons (0.5×/1×/2×/4×). Tools groups secondary controls, including explicit-input scenarios. The Lab tracks raw scores and historical evidence rather than a guessed overall grade.

Still open: refresh every critical live case after the final integration, complete three graded uninterrupted rehearsals, independent general-polygon wall/stacking oracles beyond gold/hand cases, general plan import quality, physical phone/audio/projector validation, and three unfamiliar teammate trials. These must not be marked done from a backend-only test or a different source fingerprint. See TESTING_GUIDE.md for the exact profiles and challenge prompts.

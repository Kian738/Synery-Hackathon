# Backlog: positioning, AR and later work

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

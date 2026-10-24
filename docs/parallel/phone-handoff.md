# Package C: paired phone companion — READY (touch-first; motion look is opt-in)

Status: **READY** for Codex to integrate. Nothing is mounted: `Navigator`, `server/app.py` and the React router were not edited.

What exists: a laptop-side pairing panel plus hook, a phone controller screen, a validated relay on the server, and a stand-alone two-screen demo. The touch-only paired flow works end to end in two real browser contexts (laptop and phone-sized touch context) against a real server. Motion look is implemented and unit-tested with a fake sensor environment, and exercised in the browser with synthetic `deviceorientation` events. **It has not been run on a physical phone**, and iOS Safari is untested on hardware.

## Files

| Path | Role |
|---|---|
| `server/companion.py` | `Hub` (all protocol logic, transport-free), `create_companion_router(settings=None, hub=None, prefix="/companion")`, `create_demo_app()`, `python -m server.companion` |
| `web/src/companion/protocol.ts` | message types, strict frame parser, `routeStateFromGuide`, `splitDelta` |
| `web/src/companion/client.ts` | `CompanionClient`: REST pairing, WebSocket, numbering, coalesced heading, reconnect with resume |
| `web/src/companion/sensors.ts` | `GyroLook` (explicit start, permission, secure-context and rotation handling), look maths, `pulse()` haptics |
| `web/src/companion/PhoneCompanion.tsx` | phone screen (pair, confirm number, controller) |
| `web/src/companion/LaptopPairing.tsx`, `useCompanionHost.ts` | laptop panel and hook |
| `web/src/companion/Glyph.tsx`, `companion.css`, `index.ts` | pictograms, DESIGN.md tokens, public exports |
| `web/src/companion/demo/` | `index.html` + `demo.tsx` stand-alone demo; `phone-controller.png`, `laptop-paired.png` (390x844 and 1280x800 captures from the passing browser test) |
| `tests/test_companion.py` | 37 protocol and FastAPI tests |
| `web/tests/companion.spec.ts` | 22 Playwright tests (19 pure, 3 two-browser); runs in the `desktop` project only |

## Event contract, protocol v1

Transport: one WebSocket at `/companion/ws`, JSON text frames, plus four small REST calls. Every frame has `"v": 1` and `"t"`. After `hello`, frames from a client also carry `"seq"`, a positive integer, per role, strictly increasing. The server forwards only whitelisted, re-serialised fields.

### Pairing (REST)

1. **Laptop** `POST /companion/sessions` -> `{session, laptop_token, code, code_expires_in, session_ttl}`. The code is 6 digits, single use, valid 120 s.
2. **Phone** `POST /companion/pair {"code": "123456"}` -> `{session, request_id, phone_secret, verify, expires_in}`. The code is consumed. `verify` is a 2-digit number.
3. **Laptop** receives `pair_request {request_id, verify, expires_in}` and shows an Allow / Deny dialog with the same number the phone shows. Only `approve` attaches the phone.
4. `POST /companion/sessions/{id}/code` (Bearer laptop token): new code, old code dies. `DELETE /companion/sessions/{id}` (Bearer): revoke now. `GET /companion/info`: `{v, websocket, lan_addresses, secure_context, sensor_note}`.

### Frames

First frame on every socket: `{"v":1,"t":"hello","role":"laptop"|"phone","session":"…","token":"…"}` (laptop token, or the phone secret). Reply: `hello_ok {role, session, last_seq, peer_online, approved, pending?, phone_paired?}`. **A client continues numbering after `last_seq`** (`approved` also carries `last_seq` for a phone that was waiting).

| Direction | `t` | Fields | Notes |
|---|---|---|---|
| laptop -> server | `route_state` | `status: idle\|guiding\|arrived`, `route_id?`, `step_index`, `step_count`, `instruction{text, short, icon, metres?}`, `next?`, `heading_deg?` | relayed to the phone; the last snapshot is cached and replayed (`replay: true`, with the laptop's own `seq`) when a phone connects or reconnects |
| laptop -> server | `approve` / `deny` | `request_id` | |
| laptop -> server | `new_code`, `revoke`, `ping` | | `revoke` ends the session for both sides |
| phone -> laptop | `heading` | `dyaw`, `dpitch` (degrees, right/up positive, each at most 90), `mode: touch\|gyro` | camera heading only |
| phone -> laptop | `step` | `action: next\|back\|repeat` | a request; the laptop decides |
| phone -> laptop | `recenter` | | camera to route direction |
| server -> client | `pending {verify}`, `approved {last_seq}`, `peer {role, online}`, `code {code, code_expires_in}`, `pong`, `bye {reason}`, `error {code, message}` | | `bye` is followed by a close frame |

Close codes: 1008 policy (also denied / request expired), 4401 auth failed, 4403 bad origin, 4409 replaced, 4410 revoked/expired/idle, 4426 unsupported version, 4429 too fast. The client reconnects on any other close and treats those as final.

Deliberately **not** in the contract: any position, any "confirmed progress", any phone-originated route change. The phone cannot tell the laptop where the person is.

### Safety properties (all covered by tests)

- Pairing is session-scoped, 2-minute, single use; the laptop must confirm a number shown on both screens; one confirmed phone per session; a second phone must be confirmed before the first is replaced, and merely connecting never disconnects the working phone.
- Session ids alone grant nothing. Laptop token and phone secret are 24 random bytes, stored only as SHA-256, compared in constant time, and can never act for the other role or another session.
- Secrets travel in POST bodies and the first WebSocket frame, never in URLs. The phone page link carries the code after `#`, which browsers do not send; the page removes it from the address bar on load. Logs use a 4-character session prefix only (test greps the whole log for every token, code and id).
- Rejected: non-JSON, NaN/Infinity, non-object, wrong version, unknown or role-forbidden types, bad field types and ranges, booleans as numbers, oversize frames (4 KB), stale or repeated `seq` (not consumed by rejected frames). Malformed floods disconnect after 12 per minute; error notices are throttled to one per second.
- Heading is a token bucket (30 per second sustained, burst 20). Excess frames are dropped with one notice; a flood (300 drops in 10 s) closes that phone's socket only. The client already sends at most 20 per second and splits turns larger than 90 degrees.
- Brute force: 8 wrong codes per minute per client key lock that key for 30 s; session creation is capped (10 per minute per client, 200 sessions); failed hellos are limited per client.
- Revocation, 2-hour session lifetime and 30-minute idle timeout end every socket; the old tokens fail afterwards.
- WebSocket handshakes with an `Origin` different from the page's `Host` are refused (4403), so another website cannot drive a socket from a visitor's browser.
- A closed or crashed phone leaves the laptop session intact (`peer offline` is the only effect); the laptop UI never depends on the socket.

## Integration (Codex)

### 1. Server (one line, plus one dependency)

```python
# server/app.py
from server.companion import create_companion_router
app.include_router(create_companion_router())
```

**Required dependency: `websockets`.** The repo's `uvicorn` has no WebSocket implementation (`uv run python -c "import websockets"` fails here), and plain uvicorn then rejects every handshake. I did not touch `pyproject.toml` (not my file). Add it with `uv add websockets` (or switch to `uvicorn[standard]`). `GET /companion/info` reports `websocket: false` when it is missing, and `useCompanionHost().start()` then shows an instruction in the panel instead of a mysterious connection failure. Until then, the stand-alone demo and the browser tests run with `uv run --with websockets …`.

The hub keeps state in process memory: run one worker (the default for `fw start`). `create_companion_router(hub=…)` lets the host share or inspect it.

### 2. Phone route

```tsx
import { PhoneCompanion } from "./companion";
<Route path="/phone" element={<PhoneCompanion />} />      // props documented in PhoneCompanion.tsx
```

`PhoneCompanion` props: `baseUrl`, `prefix`, `initialCode` (otherwise `#code=` is read and removed), `storage` (default sessionStorage so a reload reconnects; `null` disables), `haptics`, `dragSensitivity`, `onStateChange`. Test seams: `socketFactory`, `fetchImpl`, `scheduler`, `sensorEnv`.

### 3. Laptop panel in the Navigator

```tsx
import { LaptopPairing, useCompanionHost, routeStateFromGuide } from "./companion";
const host = useCompanionHost({
  onHeading: (dyaw, dpitch) => { /* add dyaw (and dpitch) to the camera heading; nothing else */ },
  onStep: action => { /* "next" | "back" | "repeat": call the same handlers as the on-screen step buttons */ },
  onRecenter: () => { /* camera back to the route direction */ },
});
useEffect(() => host.publish(routeStateFromGuide(route.guide.steps, stepIndex, { routeId, headingDeg })), [route, stepIndex]);
<LaptopPairing host={host} phonePath="/phone" />
```

- `publish` is cheap and safe to call every step change; it is ignored when no session exists, and the last snapshot is re-sent on (re)connect.
- `routeStateFromGuide` takes the existing `GuideStep[]` (`icon`, `text`, `short`, `metres`; `kind: "arrive"` becomes `status: "arrived"`).
- The panel renders nothing active until the user presses **Pair a phone**. If the socket drops, nothing else in the Navigator changes.
- The phone link shown to the user is built from `location.origin`; on `localhost` it substitutes the machine's LAN address from `/companion/info`. Override with `phoneOrigin` (for example an HTTPS address you set up yourself).
- The phone's heading is a delta applied to **camera heading only**. Per the brief and `docs/UX_PLAN.md`: do not move the declared location, do not mark steps as reached.

### 4. Try it now

```bash
cd web && npx vite build src/companion/demo --outDir ../.tmp-companion --emptyOutDir --base ./     # builds the demo pages
cd .. && uv run --with websockets python -m server.companion --static .tmp-companion --port 8100
# laptop: http://127.0.0.1:8100/?role=laptop     phone: the address the pairing panel prints (add --host 0.0.0.0 for a real phone)
```

(`.tmp-companion` is a throwaway folder; delete it afterwards. The same two commands were verified to build and serve.)

Fastest check: `cd web && npx playwright test tests/companion.spec.ts --project=desktop` builds the demo with Vite into a temp directory, starts the demo server on a free port and drives both browsers (about 11 s). `COMPANION_SKIP_BROWSER=1` skips the three browser tests (they need `uv` and, on first run, network access for `--with websockets`). `COMPANION_SHOTS=<dir>` writes the two screenshots.

## How the phone reaches the server, and what a phone browser will and will not do

Reachability (no tunnel or external service is published or required): run the server on a LAN-visible address (`python -m server.companion --host 0.0.0.0`, or `uvicorn … --host 0.0.0.0` for the real app; both laptop and phone on the same Wi-Fi). The panel shows `http://<lan-ip>:<port>/phone`. Guest or "client isolation" Wi-Fi blocks phone-to-laptop traffic; a phone hotspot with the laptop joined to it is the usual workaround. A firewall prompt on the laptop must allow the port.

**Motion sensors need a secure context.** Researched, with sources:

- MDN, DeviceOrientationEvent: "available only in secure contexts (HTTPS), in some or all supporting browsers" (page last modified 2026-08-04): https://developer.mozilla.org/en-US/docs/Web/API/DeviceOrientationEvent
- W3C Device Orientation and Motion, Candidate Recommendation Draft, 12 Feb 2025: events fire only in a secure context; permission requires user consent; `requestPermission()` rejects with `NotAllowedError` without transient user activation; accelerometer and gyroscope are policy-controlled features: https://www.w3.org/TR/orientation-event/
- MDN, Secure contexts: `https`, `wss`, `file`, and loopback hosts (`127.0.0.0/8`, `::1`, `localhost`, `*.localhost`) are potentially trustworthy; `http://192.168.x.x` is not: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
- MDN, `DeviceOrientationEvent.requestPermission()`: needs transient activation (a click), resolves `"granted"`/`"denied"`; Safari's own heuristics for what counts as a gesture are stricter than the spec (WebKit bug 269706), and `touchstart` does not count, so the button uses `click`: https://developer.mozilla.org/en-US/docs/Web/API/DeviceOrientationEvent/requestPermission_static

Consequences, stated exactly:

| Situation | Sensors | Touch controls |
|---|---|---|
| Phone opens `http://<lan-ip>:8000/phone` (the default same-Wi-Fi setup) | **Not available**: not a secure context. The panel says so in words; the code never calls the API. | Work |
| Phone opens an `https://` address with a certificate the phone trusts | Available after the user taps "Turn on motion look"; iOS shows its permission prompt, Chrome Android needs no prompt | Work |
| Android phone with the laptop's port forwarded over USB (`adb reverse tcp:8000 tcp:8000`, then `http://localhost:8000/phone` on the phone) | Available: loopback is secure | Work |
| iOS Safari | Needs HTTPS and the tap; permission may be remembered or re-asked at the browser's discretion | Work |
| Desktop browser or a phone without a gyroscope | `no-data` after 2 s with an explanation | Work |

HTTPS options that respect the brief (no insecure browser flags such as "treat insecure origin as secure", no tunnel): serve the app with a locally generated certificate (for example `mkcert`, installing its root certificate on the phone, then `uvicorn --ssl-keyfile … --ssl-certfile …` and `phoneOrigin="https://<lan-ip>:8000"`), or the USB `adb reverse` route above for Android. HTTPS pages must use `wss:`; the client derives that from the page origin automatically. Mixed content is therefore not an issue.

Motion look specifics: it controls heading only. Nothing is requested at load or at pairing; the tap on "Turn on motion look" is the only trigger (`GyroLook.start()` runs inside the click handler, test-verified: zero permission calls before the tap). Denial, a failing prompt, no API, an insecure page and no data all end in a worded status while the touch look pad, nudge buttons and Next/Back/Repeat keep working. Upright, the phone's look is the back camera's direction ("window" metaphor); flat, it is the direction of the top of the screen, corrected for `screen.orientation.angle`; a screen rotation re-baselines instead of reading as a turn; samples inside a 0.15 degree dead zone are ignored; turns across north do not jump 358 degrees. Haptics (`navigator.vibrate`) are capability-detected and never the only cue (the instruction is also text, an icon and an `aria-live` region); iOS Safari has no vibration API.

## Checks run

- `uv run pytest tests/test_companion.py`: 37 passed (full-flow pairing; single-use, expiry and lockout; token separation and role enforcement; 16 malformed payloads; stale and replayed `seq`; oversize and wrong version; flood disconnects; heading rate limit; revoke, TTL and idle expiry; phone drop and resume; laptop reconnect; second phone and deny; secrets-in-logs; creation caps; two FastAPI WebSocket flows including the Origin check).
- `npx playwright test tests/companion.spec.ts --project=desktop`: 22 passed. Covered: strict frame parser; delta splitting; look maths including portrait/landscape roll and screen rotation while flat; permission denied, throwing prompt, insecure context, missing API, Android-style no-prompt path, timeout when a device has no gyroscope; client numbering, 20 Hz coalescing, backoff (800 ms then 1600 ms) and resume of numbering from the server, no reconnect after revoked/replaced/denied/auth failure, giving up after the configured attempts, stale snapshot rejection; two browser contexts: pairing with the verify number, Next/Back/Repeat, drag and nudge look, recenter, reload and resume, phone closing while the laptop keeps working, new code, revoke, wrong code, deny, single-use, denial of motion permission leaving touch intact, granted motion turning the laptop heading by -25 degrees while step progress stays put, and no secrets in any request or WebSocket URL.
- Typecheck: `npx tsc --noEmit -p web` clean.
- A real bug was found by the browser run and fixed: an unset React prop (`prefix={undefined}`) erased the client's default route prefix. Another: replayed route state lacked `seq`, so the phone's strict parser dropped it; `Session.state_seq` now carries it.

## Limitations, plainly

- **Not tested on a physical phone**, on iOS at all, or on a real LAN. Emulated touch (Playwright mobile context) and synthetic orientation events were used. The motion maths follow the W3C Euler order but sign conventions on real devices (and the compass-versus-relative `alpha` difference between Chrome and Safari) are unverified; the delta approach avoids absolute-heading reliance, but expect a sensitivity or sign tweak on first hardware test.
- The `websockets` dependency is not in `pyproject.toml` (see above). Without it the feature cannot work, and the panel says so.
- No QR code (would need a library or a hand-written encoder). The address and code are shown as text; `#code=` links can be turned into a QR later without protocol changes.
- No screen wake lock on the phone: the screen may dim while idle. Reconnect handles the dropped socket when the browser is backgrounded; iOS suspends sockets aggressively.
- In-memory hub: restarting the server ends all pairings; multiple workers would not share sessions.
- The 6-digit code plus on-screen confirmation protects against casual or accidental pairing on the same network. It is not a defence against someone who both guesses the code in two minutes within the rate limit and persuades the user to confirm; it also assumes the LAN is not hostile (plain HTTP is readable by others on it, which is one more reason to prefer HTTPS beyond a demo).
- Phone-originated `step` requests are accepted from a confirmed phone at any time. If the Navigator should only honour them in step mode, gate that in `onStep`.
- Accessibility was checked structurally (labels, `aria-live`, 56 px touch targets, keyboard-reachable buttons), not with a screen reader on a phone.

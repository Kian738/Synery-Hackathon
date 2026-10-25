# Phone + laptop jury setup

The real Navigator integrates the reviewed companion package. Run one server process:

```powershell
uv sync
uv run fw start --lan
```

On the laptop, open **Phone**, then **Pair a phone**. Scan the QR with the phone camera on the same network. The address and six-digit code are also available under **Or enter the code manually**. Compare the two-digit confirmation number on both screens and press **Allow** on the laptop. Close setup; pairing remains active. The QR is generated locally, contains the one-use code in the URL fragment, and changes when **New code** is pressed. Codes expire after two minutes.

Choose a route on the laptop. The phone shows the current computed instruction, Next, Back, Repeat, a touch look pad and Recenter. Next/Back use the laptop's chapter controls and pause preview playback. Turning changes camera orientation only. It does not change the declared location, route, or confirm that someone physically reached a waypoint. Closing or disconnecting the phone leaves desktop navigation available. End pairing from laptop setup when finished.

No route is needed to use the remote pad: in the overview it turns the model around the current camera target. It does not silently switch into guidance. **Open 3D on this phone** opens the selected building in a separate full-scene phone workspace. Motion and disconnect controls are under **Motion & connection**. On smaller screens the laptop-style secondary controls are under the three-dot **Building tools** menu; Map and the current view remain directly accessible.

## Motion look readiness

The default `http://<LAN-IP>:8000/phone` address supports touch control. Phone motion sensors require a secure context; enable them only after the phone opens an HTTPS address with a certificate it trusts and the user taps **Turn on motion look**. iOS may ask permission. Denial or missing sensors preserves touch controls. No insecure-browser flags or public tunnel are configured.

**Fast path to https (2026-10-25):** `powershell -File scripts/phone_https.ps1` starts a Cloudflare quick tunnel (`winget install --id Cloudflare.cloudflared` once) and prints a temporary `https://….trycloudflare.com` address; open it on the phone, pair as usual and tap **Turn on motion look**. The address is public while the tunnel runs, so use it for the demo only. There is no bypass on iPhone; on Android Chrome alone, `chrome://flags/#unsafely-treat-insecure-origin-as-secure` with the LAN address also works. Not tried on a physical phone from here.

The package's detailed [HTTPS and device notes](parallel/phone-handoff.md) describe local certificate and Android USB-loopback options. They require on-site setup; this implementation has not installed a root certificate or tested a physical device. Guest-network client isolation and the laptop firewall can prevent LAN connections; rehearse this on the actual network. Keep the laptop alone as the fallback.

## Twenty-second showcase

Pair before the timed pitch. Ask the building for a multi-floor route on the laptop; press Next on the phone to show the decision changing on both screens; turn the view with the touch pad, then recenter. Use gyro only after a successful hardware rehearsal. Repeat reads the computed landmark instruction through the laptop's browser speech output. Do not spend the jury's time pairing or debugging network permissions.

## Verified and still manual

Automated integration exercises the actual FastAPI app and Navigator in separate laptop and phone browser contexts: confirmed pairing, synchronized instructions, remote chapter changes, camera turning without position movement, recentering, unchanged manual location, disconnect and independent desktop playback. Protocol/sensor tests cover stale messages, rate limits, revocation, reconnect, permission denial and synthetic orientation. These are browser tests, not physical-phone results.

The integration regression exposed a connector-label DOM-root teardown race when view and floor changed together. Scene labels now project into one ordinary React overlay with wall occlusion; they do not create independent DOM roots inside the canvas.

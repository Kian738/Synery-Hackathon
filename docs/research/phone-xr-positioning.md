# Phone exploration, VR, AR and indoor positioning

Reviewed 24 October 2026. This separates fixes that ship in Navigator from future systems requiring hardware, mapped anchors and measured performance. Sources below are platform specifications, platform documentation or the implementing project's own API reference. No physical-phone or XR-headset trial has been performed by the coding agent.

## Immediate findings

The phone's overview drag was discarded by Navigator whenever no route existed. The relay could be perfectly connected while the building did nothing. The revised implementation applies remote input to overview orbit or first-person heading according to the actual laptop view. It does not silently enter guidance. The phone also offers a link to the same building in its own expanded 3D workspace. Motion/connection configuration is collapsed, while the current instruction and touch controls remain prominent.

The old ceiling was an extrusion over every current-floor room. That creates false ceilings across atria. The replacement compiles the union of recorded footprints on each actual floor, triangulates the union with its holes intact, and renders the higher floor slabs and walls at supplied elevations. Slab undersides provide coverage only where upper footprints exist. There is no invented top roof. This reconstructs the recorded geometry; an unrecorded atrium or inaccurate upper polygon cannot be recovered from these polygons alone.

## Smooth routes and cameras

[Detour's navigation query](https://recastnav.com/classdtNavMeshQuery.html) distinguishes a polygon corridor from the straight path pulled through it. The useful architecture is a validated walkable corridor, exact doorway crossings, then visibility-constrained simplification or a funnel. Decorative splines over raw waypoints are unsuitable: they can cut corners through walls. An eventual rounded corner must validate its whole swept clearance, preserve door anchors, and fall back when it cannot fit. This is a proposed walking-layer follow-up; Claude currently owns the graph/routing work.

Rendering also matters independently of pathfinding. A tube swept along a hard polyline can develop visible frame changes at corners. The current display uses flat constant-width strips and round joins on the existing validated line. It does not claim to remove geometric zigzags. Camera turns now use damped, rate-bounded rotation while positions stay on the route. [Unity's camera documentation](https://docs.unity3d.com/Packages/com.unity.cinemachine@3.1/manual/CinemachinePositionComposer.html) treats damping and look-ahead as separate controls; adding look-ahead is not a substitute for clean motion input. Acceptance should measure lateral oscillation, turn-angle changes and completion time in addition to frame-independent position sampling.

## VR is a distinct presentation mode

The [WebXR Device API](https://www.w3.org/TR/webxr/) distinguishes inline, immersive VR and immersive AR sessions. An ordinary phone page, gyro controller or duplicated side-by-side image does not establish headset support. A real mode must check `isSessionSupported`, request a session from an intentional user action, handle refusal/end, and use the platform's tracked views. [Three.js WebXRManager](https://threejs.org/docs/pages/WebXRManager) provides session and reference-space integration; the existing desktop camera must stop overwriting the tracked camera during immersion.

Recommended first VR slice: stationary inspection at validated room/decision anchors, room selection with a controller ray, explicit teleport/snap-turn options and a persistent exit. Optional continuous movement needs its own comfort settings and collision validation. Do not force route playback onto a user's headset pose. The [W3C XR accessibility requirements](https://www.w3.org/TR/xaur/) support alternatives to bodily movement, recentering, adjustable speed, clear start/stop and alternatives to sickness-triggering interactions. They do not establish one universally comfortable locomotion method. This is research/proposed scope, not a shipped VR mode.

## AR needs a transformation into the actual building

[ARCore's fundamental concepts](https://developers.google.com/ar/develop/fundamentals) describe tracking device motion and detecting the surrounding environment. That local tracking frame does not identify a room in Floorwise's JSON. The system still needs the building, floor and a measured transform between the AR frame and building coordinates.

Start with a known marker or reference image at a measured position, orientation and size. [ARCore Augmented Images](https://developers.google.com/ar/develop/augmented-images) uses a reference image database and estimates image pose. Reference images need distinctive visual content; a generic chair or similar corridor is insufficient to establish unique room identity. QR room IDs and image-pose tracking are separate jobs: decoding an ID does not by itself provide a calibrated 6D building pose. Existing plan PNGs are not photographs of the user's camera view.

After initial alignment, visual-inertial tracking can carry the pose locally, but tracking status must remain visible. [Apple's relocalization documentation](https://developer.apple.com/documentation/arkit/artrackingstatereason/artrackingstatereasonrelocalizing) explicitly warns that coordinate alignment after an interruption is uncertain while relocalizing, with variable success. Hide or soften world-locked route arrows when alignment is uncertain, retain a manual plan and offer a deliberate re-anchor. Evaluate wrong-floor and confidently-wrong-room cases, not only successful recognition.

## Wi-Fi and BLE are infrastructure-dependent inputs

[Android Wi-Fi RTT](https://developer.android.com/develop/connectivity/wifi/wifi-rtt) measures distances to compatible access points. Its documentation describes multilateration with at least three access points and typically 1–2 m accuracy. That is a platform statement under suitable conditions, not a guarantee for this building. The design needs compatible phone/AP hardware, known AP locations, native API access and permissions. A normal web page must not pretend to have a Wi-Fi RTT position feed just because it has network access.

[Bluetooth Direction Finding](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/direction-finding/) uses AoA/AoD signals and antenna-array infrastructure. Those capabilities differ from reading ordinary beacon RSSI. The [Web Bluetooth specification](https://bluetooth.spec.whatwg.org/) requires secure contexts and user-approved device access; advertisement RSSI, when available, is received signal strength rather than a room coordinate. Browser/device support and the venue deployment need inspection before choosing a web or native implementation. No BLE or Wi-Fi positioning is integrated in Floorwise.

Proposed fusion: camera/IMU relative motion, explicit mapped anchors, floor/door topology, and calibrated RF likelihoods. Each observation carries a timestamp, uncertainty, source and consent scope. Reject stale/impossible floor jumps, test recovery after lost tracking, and require a confidence threshold before converting the manual location into a tracked location. The LLM may explain a state; it must not estimate the position or uncertainty.

## Gestures and readable interfaces

[Pointer Events](https://www.w3.org/TR/pointerevents3/) provides scoped gesture handling. Scene gestures should zoom or move the model, while the surrounding page retains deliberate browser/keyboard zoom and readable controls. [WCAG resize-text guidance](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) requires usable text enlargement. The implementation consumes pinch-wheel zoom in the model surface and gives the canvas its own touch behavior; it does not globally disable page scaling with `user-scalable=no`.

## Work order and concrete evaluation

1. **Now:** overview remote input, compact phone controls, local phone 3D entry, footprint-based upper context, flat route display, camera damping and clickable room mentions. Verify real browser interaction and no declared-location changes.
2. **Walking layer, with its owner:** inspect reported zigzags on actual routes; compare bend count and lateral deviation in straight corridors, verify obstacle clearance and exact doors, then run existing exact benchmark gates. Freeze source semantics separately from presentation.
3. **Hardware rehearsal:** record actual phone OS/browser, LAN reachability, touch latency, gyro permission/sign conventions and background/reconnect behavior. Test with an unfamiliar person. An emulated phone is insufficient evidence of physical gyro quality.
4. **Optional VR prototype:** one supported headset/browser, secure origin, stationary room inspection, tracked camera ownership and clear exit; measure frame time and user discomfort. Keep ordinary 3D available.
5. **AR pilot:** two measured rooms, explicit mapped anchors, tracking-loss UI and a ground-truth trajectory. Measure position/yaw error, wrong-room/floor rate, relocalization time and calibration failures. Add RF only if its measured contribution justifies infrastructure and native integration.

This scope makes the next demo reviewable and leaves SLAM/RF research measurable rather than presenting planned sensors as working capabilities.

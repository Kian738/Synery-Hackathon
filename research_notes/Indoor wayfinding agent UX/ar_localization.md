# Indoor AR Navigation and Phone Localization for a Web App (status as of Oct 2026)

## 1. WebXR immersive-ar support in 2026 (Chrome Android, iOS Safari, Vision Pro) and iOS alternatives

### Takeaway
WebXR `immersive-ar` works reliably only in Chrome on ARCore Android phones. In the sources I checked, iPhone Safari still does not support it, and WebXR is **not** an Interop 2026 focus area. The most practical cross-platform options are: (a) WebXR on Android plus a non-AR or camera-only fallback on iOS, or (b) a wrapper such as Needle Engine's "Needle Go" App Clip, which runs the same WebXR scene on iPhone through ARKit. 8th Wall's hosted platform has shut down.

### Cited Findings
- Chrome and Edge "carry full WebXR on desktop and Android". Safari now exposes WebXR on visionOS with gaze-and-pinch input — [vr.org, Jun 2026](https://vr.org/articles/webxr-interop-2026-cross-browser-standard)
- That same vr.org article says WebXR "has been put forward as a focus area for Interop 2026". **This is contradicted by the official announcements.** The 20 Interop 2026 focus areas, launched Feb 12, 2026, are Anchor Positioning, attr(), Container Style Queries, contrast-color(), CSS Zoom, Custom Highlights, Dialog/popover, Fetch uploads/ranges, IndexedDB getAllRecords(), JSPI for Wasm, Media pseudo-classes, Navigation API, Scoped Custom Element Registries, Scroll-driven Animations, Scroll Snap, shape(), View Transitions, Web Compat, WebRTC and WebTransport. WebXR is not on the list — [WebKit: Announcing Interop 2026](https://webkit.org/blog/17818/announcing-interop-2026/); [web.dev](https://web.dev/blog/interop-2026); [Mozilla Hacks](https://hacks.mozilla.org/2026/02/launching-interop-2026/). The vr.org claim may refer to a proposal that was not selected (or to an investigation area); I could not verify which.
- iOS Safari: the MultiSet docs (2026) say "WebXR immersive-ar is supported on Android (Chrome 81+, ARCore). Safari on iOS does not implement the camera-access feature required for VPS." — [MultiSet WebXR SDK docs](https://docs.multiset.ai/webxr-sdk)
- iOS 15.4 had experimental WebXR flags, but they did not enable AR on iPhone — [Babylon.js forum](https://forum.babylonjs.com/t/webxr-ar-with-safari-on-ios/34570); [Road to VR](https://roadtovr.com/?p=170884)
- Vision Pro: Apple shipped WebXR `immersive-vr` (plus hand tracking) in visionOS Safari — [Road to VR](https://roadtovr.com/apple-vision-pro-webxr-support-safari-model/). On visionOS, `isSessionSupported("immersive-ar")` returned false in an earlier version — [Apple Dev Forums](https://developer.apple.com/forums/thread/743655). A visionOS 26.5 Safari has a "WebXR Augmented Reality Module" feature flag, but a developer reported that an immersive-ar test still did not launch — [Apple Dev Forums](https://developer.apple.com/forums/thread/826845)
- Needle Engine "Needle Go" is a shared iOS App Clip that runs Needle WebXR scenes on iPhone/iPad using ARKit. Its docs claim no Apple Developer account is needed and that it supports hit-test, plane detection, DOM overlay and image tracking, with anchors and lighting estimation still WIP. Users open it via QR code or link. One older docs page still says "coming soon" — [Needle docs: iOS WebXR App Clip](https://engine.needle.tools/docs/how-to-guides/xr/ios-webxr-app-clip); [appclip.needle.tools](https://appclip.needle.tools/about)
- 8th Wall: Niantic shut down the hosted services (logins, cloud editor, XR Studio). The engine framework is MIT open source but excludes SLAM. Core tracking ships as a free closed-source binary, and VPS, Maps and Hand Tracking are not included. The project now lives at 8thwall.org — [Road to VR](https://www.roadtovr.com/niantic-webar-platform-8th-wall-open-source/); [8thwall.org migration](https://8thwall.org/docs/migration). **The shutdown date conflicts between sources:** Feb 28, 2026 in a Jan 2026 Niantic Spatial blog post, versus hosting ending Feb 2027 in a Dec 2025 post — [Niantic Spatial blog](https://info.nianticspatial.com/blog/8th-wall-update-engine-distribution-and-open-source-plans)
- Zappar Mattercraft supports web AR world tracking and has an Immersal VPS integration ("anchor 3D content to real-world locations on the web, no apps needed") — [Zappar docs: Immersal VPS](https://docs.zap.works/mattercraft/vps/immersal/)
- Camera-only marker libraries (AR.js, MindAR) are the fallback when native WebXR tracking is unavailable. They need a camera permission and are less accurate than native tracking — [Needle docs: image tracking](https://engine.needle.tools/docs/how-to-guides/xr/image-tracking)

### Inferences
- For a 1–2 day hackathon, demo on an ARCore Android phone running Chrome. Give iPhone users a 2D map / compass-arrow fallback, or try Needle Go if the team uses Needle Engine.
- AR Quick Look (USDZ) shows static 3D models, not a live route tied to a pose, so it is a poor fit for turn-by-turn wayfinding. This is my knowledge, not sourced here.
- Always feature-detect `navigator.xr?.isSessionSupported('immersive-ar')` at runtime.

### Gaps
- I found no official WebKit 2026 release note stating the iOS WebXR status. "Not supported on iPhone" rests on third-party docs (MultiSet) and the lack of any announcement.
- I could not confirm the exact 8th Wall shutdown date (Feb 2026 vs Feb 2027).
- I did not verify current Zappar pricing or licensing.

## 2. Indoor localization options

### Takeaway
For a hackathon, **QR/marker anchors at known positions** are by far the most practical: scanning one gives a known pose, and WebXR/ARCore tracking carries it from there. Cloud VPS (MultiSet, Immersal) can work on Android WebXR but needs a pre-scanned map. BLE, WiFi RTT and PDR are mostly unavailable or unreliable in the browser and give 2–5 m accuracy, which is too coarse for AR arrows.

### Cited Findings
- MultiSet VPS WebXR SDK (`@multisetai/vps`): sends camera frames from a WebXR session to the cloud and returns a 6-DoF pose. Packages exist for three.js and Needle. It requires HTTPS, an ARCore Android device and a whitelisted domain. It claims "sub-6 cm" accuracy (vendor claim) and is optimized for indoors. The free dev tier offers 10 MapSets and 10,000 localizations per month — [MultiSet docs](https://docs.multiset.ai/webxr-sdk); [MultiSet v1.8 release](https://multiset.ai/post/multiset-ai-v1-8-markerless-object-tracking-sdk)
- Immersal VPS: maps are made with the Immersal Mapper app (iOS/Android), 360 cameras, Polycam or Leica. It supports on-device and on-server localization. On the web it is reached through Zappar Mattercraft. I found no standalone Immersal WebXR JS SDK — [Zappar docs](https://docs.zap.works/mattercraft/vps/immersal/)
- Niantic VPS is **not** included in the open-sourced 8th Wall — [Road to VR](https://www.roadtovr.com/niantic-webar-platform-8th-wall-open-source/)
- WebXR image/marker tracking in Chrome Android is behind `chrome://flags/#webxr-incubations` and is a draft spec — [Needle docs](https://engine.needle.tools/docs/how-to-guides/xr/image-tracking). The practical alternative is to scan a QR code with a normal camera/QR library **before** entering AR, then set the AR origin from that.
- BLE beacons: about 2–5 m with inertial fusion (vendor guide, 2021). One fingerprinting study reported under 2.6 m at the 95th percentile at 1 beacon per 30 m², and under 4.8 m at 1 per 100 m². BLE beat WiFi fingerprinting, which was under 8.5 m at the 95th percentile — [VDE proceedings](https://www.vde-verlag.de/proceedings-en/563621040.html); [ISPRS 2020](https://isprs-archives.copernicus.org/articles/XLIII-B1-2020/193/2020/isprs-archives-XLIII-B1-2020-193-2020.pdf)
- iOS does not expose WiFi signal strengths to apps, and as of 2021 iOS did not support WiFi RTT — [Microsoft/vendor guide PDF](https://query.prod.cms.rt.microsoft.com/cms/api/am/binary/RWEMFM)
- Web Bluetooth `requestLEScan` (needed for beacon scanning in the browser) is experimental. Reports describe it as hanging on desktop Chrome and "seems to work" on Chrome Android — [flutter_web_bluetooth docs](https://pub.dev/documentation/flutter_web_bluetooth/0.2.4/js_web_bluetooth/Bluetooth/requestLEScan.html); [W3C bug, Oct 2025](https://lists.w3.org/Archives/Public/public-web-bluetooth-log/2025Oct/0004.html)
- Situm (commercial IPS) claims 1–5 m using existing signals plus inertial sensors (vendor brochure). It provides native, Flutter, React Native and Capacitor/Cordova SDKs, not a browser SDK — [Situm brochure](https://query.prod.cms.rt.microsoft.com/cms/api/am/binary/RW1hBSM); [Situm GitHub](https://github.com/situmtech/situm-android-getting-started)
- PDR is rated "medium" accuracy and is mainly used to complement BLE against drift and jumps — [encyclopedia.pub](https://encyclopedia.pub/entry/history/show/111447)
- Google ARCore Geospatial / Live View relies on Street View coverage, so it is outdoor-only — [TechCrunch](https://techcrunch.com/2019/08/08/google-launches-live-view-ar-walking-directions-for-google-maps/)

### Inferences
- Within an AR session, WebXR/ARCore VIO tracking is itself a high-quality relative positioning system (it drifts over long distances). Re-anchoring at each QR code or door corrects that drift.
- If the team is not in AR mode, a "scan QR → show position on 2D map, then step counting / DeviceOrientation compass" approach works on both iOS and Android. Note that iOS requires a permission prompt for DeviceMotion/DeviceOrientation (my knowledge, unsourced).

### Gaps
- I found no measured WiFi RTT accuracy figures, and no source confirming that WiFi RTT is reachable from a browser (my understanding: Android native API only).
- I did not fetch the Immersal pricing or free tier.
- I found no peer-reviewed browser-PDR accuracy number.

## 3. AR wayfinding UX best practices; AR vs 2D map studies

### Takeaway
AR helps with orientation, decision points and anxious first-time visitors: it is faster, causes fewer errors and lowers workload. It hurts spatial learning and safety when the phone is held up continuously. Best practice is short "glance" AR at decision points plus a 2D map, not continuous camera-up walking.

### Cited Findings
- Hospital study (N=32, AR vs paper map): AR users were faster, made fewer errors, and had lower anxiety (STAI) and workload (NASA-TLX). Paper-map users had **better spatial memory** (sketch recall). The authors frame this as efficiency vs spatial learning — [Liu et al., arXiv 2601.00001](https://arxiv.org/abs/2601.00001v1)
- Other comparisons are small or pilot studies, such as an Albertina museum AR guide vs map plus signage, and a 10-person Taiwan AR vs 2D map field study. I did not see their results — [Univie thesis](https://utheses.univie.ac.at/detail/58669); [arXiv PDF](https://arxiv.org/pdf/2601.00001)
- Google Live View design: AR is intended for quick orientation (arrows and markers placed in the world for tricky turns and start direction). The app warns users not to hold the phone up while walking. Battery drain and overheating complaints were noted — [Business Insider](https://www.businessinsider.nl/google-maps-live-view-ar-ios-android-2019-8); [Smart Cities Dive](https://www.smartcitiesdive.com/news/google-maps-releases-ar-feature-for-walking-directions/560550/); [Pulse2](https://pulse2.com/google-maps-live-view/)

### Inferences
- UX recipe: floor-level arrows or chevrons every 1–2 m along the polyline, a large arrival marker, an off-screen direction indicator, a "lower your phone" prompt with automatic switch to the 2D map when the device is pitched down, and a re-scan prompt when tracking is lost.
- For a hackathon pitch, cite the hospital study for the stress and anxiety reduction, and acknowledge the spatial-memory tradeoff.

### Gaps
- I found no 2025–2026 CHI/ISMAR meta-analysis. The evidence is mostly small studies.
- I found no current Google Live View design guidance (sources are from 2019).

## 4. Concrete hackathon architecture

### Takeaway
Use a QR code at each door or junction that encodes a node ID and pose. Scanning it sets the AR origin, and three.js + WebXR (`hit-test`, `local-floor`) draws arrows along an A* route on a hand-authored floor graph. Fall back to a 2D map plus compass on iOS or when AR is unavailable.

### Cited Findings
- WebXR immersive-ar with hit-test is available on Chrome 81+ on ARCore Android — [MultiSet docs](https://docs.multiset.ai/webxr-sdk)
- Published AR indoor nav prototypes use exactly "QR code initialization + spatial anchors" on ARCore/ARKit — [IJACSA 2025 paper](https://thesai.org/Downloads/Volume16No4/Paper_6-Evaluating_User_Acceptance_and_Usability_of_AR.pdf)
- Upgrade path: swap the QR origin for MultiSet VPS (three.js package) once a building map has been scanned — [MultiSet docs](https://docs.multiset.ai/webxr-sdk)
- iOS path: Needle Go App Clip, which runs the same scene on iPhone — [Needle docs](https://engine.needle.tools/docs/how-to-guides/xr/ios-webxr-app-clip)

### Inferences (proposed design, not sourced)
1. **Data:** floor plan image → nodes (doors, junctions, POIs) in metres with a floor-local frame → edges. Each QR code encodes `{nodeId, x, y, floor, headingDeg}`, or a URL like `https://app/?n=door12`.
2. **Localize:** the user scans the QR code with the phone camera (the URL opens the web app), or uses an in-app scanner (e.g. jsQR) before AR. Ask the user to stand at the sign facing it. That gives the position, and the sign's facing direction gives the heading.
3. **Enter AR:** request `immersive-ar` with `local-floor` + `hit-test` (+ `dom-overlay`). Map the floor-plan frame to the XR frame using the device pose at session start and the QR heading. Optionally confirm the heading by asking the user to tap the floor at the sign base with hit-test.
4. **Route:** run A* on the graph to get a polyline, then place chevron meshes every ~1 m at floor height and a destination pin. Show distance and next-turn text in a DOM overlay.
5. **Drift control:** re-scan QR codes at intermediate doors to reset the origin. Show "lost tracking — scan nearest sign" when tracking state degrades.
6. **Fallbacks:** (a) no WebXR (iOS): 2D map with a "you are here" marker from the QR code plus a DeviceOrientation compass arrow pointing to the next node; (b) an optional camera-passthrough mode with a compass-oriented arrow overlay (getUserMedia + DeviceOrientation, no SLAM).
7. **Safety:** AR only at decision points, a "lower phone" hint, and an auto-switch to the map while walking.

### Gaps
- Heading accuracy from QR alone (user stance error) is untested. Estimate a ±10–20° error and use the floor-tap or second-QR alignment to reduce it. This is my estimate, not sourced.

## 5. "Scia" — likely candidates

### Takeaway
I found no AR/mobile wayfinding product named "Scia". The most likely intended candidate is **Situm** (an indoor positioning and wayfinding SDK with an AR plugin in progress). Other possibilities: SCIA Engineer (Nemetschek structural engineering software, not AR wayfinding), or a similar-sounding Niantic product.

### Cited Findings
- Situm: an indoor positioning SDK with wayfinding (floors, POIs, routes, turn instructions). It offers native, Flutter, React Native and Capacitor/Cordova SDKs, plus a "Situm Flutter AR" plugin marked work in progress, with native AR binaries available on request — [Situm Flutter AR](https://pub.dev/documentation/situm_flutter_ar/latest/); [Situm Wayfinding app](https://apps.apple.com/mx/app/situm-wayfinding/id6450784110); [SitumWayfinding pod](https://cocoapods.org/pods/SitumWayfinding)
- Situm technologies (secondary source): WiFi fingerprinting, BLE beacons, geomagnetic positioning — [FitGap](https://us.fitgap.com/products/situm)
- Searches for "Scia AR" returned no product. Nemetschek SCIA is structural/steel engineering software — [Architosh](https://architosh.com/tag/BIM/page/13)

### Inferences
- Other similar-sounding names worth asking the user about (from my knowledge, unverified here): Niantic "Scaniverse" (3D scanning app), Sygic (navigation), NavVis (indoor mapping), and Scandit (barcode/AR scanning SDK).

### Gaps
- I could not confirm what the user meant. Ask for the full name or a URL.

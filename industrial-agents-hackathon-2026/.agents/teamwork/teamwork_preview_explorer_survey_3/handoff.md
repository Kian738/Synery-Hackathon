# Handoff Report: Survey of R3 Interactive Visualizer & Real-Time Operational Dispatcher

**Specialist**: Survey Specialist 3 (`teamwork_preview_explorer_survey_3`)  
**Mission**: Technical architecture and feasibility survey for R3 (Interactive Visualizer, 2D/3D Stacked Floor Plans, Real-Time Dispatcher, and Voice-Assisted Navigation).  
**Parent Conversation ID**: `99a36772-9103-445c-a001-17463bb30980`  
**Timestamp**: 2026-10-24T14:04:00Z  

---

## 1. Observation

### 1.1 Existing Repository Assets and Code
- **Repository Search**:
  - Command: `find . -maxdepth 4 -name "*.html" -o -name "*.js" -o -name "*.css"`
  - Result: Empty (0 web files). There are currently **no HTML, JavaScript, CSS, or web server files** anywhere in the repository.
- **Existing Visualization (`starter_agent/viewer.py`)**:
  - Lines 1–85:
    ```python
    """Flat 2D route view: one PNG per floor the latest route passes through."""
    import matplotlib
    matplotlib.use("Agg")
    ...
    def draw_route(building_map: BuildingMap, output_directory: Path) -> list[Path]:
        ...
        axes.add_patch(PolygonPatch(space["polygon"], facecolor=colour, edgecolor=OUTLINE_COLOUR, linewidth=0.5))
        ...
        figure.savefig(path, bbox_inches="tight")
    ```
    Observations: `viewer.py` only outputs static 2D Matplotlib PNG files (`route_{level}.png`). It does not provide any web interface, interactivity, multi-floor 3D stacking, live editing, route animations, or voice support.
- **Pre-generated Assets in `data/dev/` and `data/test/`**:
  - Each building folder contains:
    - `floor_<level>.png`, `floor_<level>.svg`, and `floor_<level>_plain.png`.
    - Inspection of `data/dev/osm-way22744230/floor_0.svg` (lines 1–50) reveals static Matplotlib export artifacts (`<path d="..." clip-path="...">`) without semantic room IDs, interactivity, or coordinate binding.
- **Semantic Geometry in `building.json`**:
  - Inspection of `data/dev/proc-factory-dev-003/building.json`:
    - `floors` (lines 16–31): contains `id`, `level` (int: 0, 1, -1), `elevation_m` (float, e.g. 0.0, 3.5), `height_m`.
    - `spaces` (lines 32–60): contains `id`, `floor_id`, `type`, `room_type`, `name`, `ref`, and `polygon`: array of `[x, y]` coordinates in metres.
    - `openings` (lines 3520–3528): contains `id`, `floor_id`, `space_ids` (pair of spaces or `"outside"`), `kind` (`door`, `opening`, `entrance`), `position`: `[x, y]`, `width_m`, `step_free`.
    - `vertical_connectors` (lines 3529–3560): contains `id`, `kind` (`stairs`, `lift`), `name`, `floor_ids`, `space_ids`, `step_free`.
    - `assets` (lines 3561–3595): contains `id`, `name`, `category`, `type`, `position`: `[x, y]`, and `footprint`: `{"width_m": float, "depth_m": float, "rotation_deg": float}`.
- **Underlying Routing and Dispatch Capabilities (`starter_agent/building_map.py`)**:
  - Lines 48–51: Tracks `self.closed: set[str] = set()`, `self.last_route: RouteResult | None`.
  - Lines 179–213: `graph(step_free: bool) -> nx.MultiGraph`: builds the multi-floor graph where stairs cost 12m/floor and lifts cost 15m wait + 6m/floor.
  - Lines 214–247: `route(start, destination, step_free, via) -> RouteResult`.
  - Lines 291–298: `set_closed(reference: str, closed: bool) -> str`: dynamically adds/removes elements to/from `self.closed`.
  - Lines 299–321: `add_door(first: str, second: str, step_free: bool = True) -> dict`: verifies adjacency via `Polygon.distance <= 0.6`, calculates midpoint using `nearest_points(p1, p2)`, creates new opening, and updates graph.
- **Python Runtime Environment (`uv pip list`)**:
  - Python 3.12 is active.
  - Installed packages: `networkx` (3.7), `shapely` (2.2.0), `pydantic` (2.14.1), `matplotlib` (3.11.2), `anthropic` (2.3.0).
  - Python standard library includes `http.server.ThreadingHTTPServer` (verified via command `python3 -c "import http.server; print(http.server.ThreadingHTTPServer)"`) and `webbrowser`.

---

## 2. Logic Chain

1. **Need for a Native Web Application**:
   - *From Observation 1.1 & 1.2*: The starter code has zero web infrastructure and only generates static PNGs. However, Acceptance Criteria (lines 48–49 of `ORIGINAL_REQUEST.md`) mandate:
     - An interactive web application that runs locally, visualizes 2D/3D stacked floor plans, and animates computed routes.
     - Live map modification (adding a door, reporting a closed lift) that dynamically alters subsequent route calculations and visual feedback.
   - Therefore, a dedicated interactive web visualizer and real-time operational dispatcher module must be built.

2. **Optimal Backend Architecture: Zero-Configuration Python Standard Library Server**:
   - *From Observation 1.4 & 1.5*: The competition evaluation expects immediate single-command execution without requiring users to install unpinned heavy dependencies or run separate Node.js build processes.
   - A backend built with Python 3.12's `http.server.ThreadingHTTPServer` requires **zero new dependencies**, starts in under 100 milliseconds, and exposes standard JSON REST endpoints (`/api/building`, `/api/route`, `/api/closure`, `/api/add_door`, `/api/chat`).
   - The backend directly loads `BuildingMap` and `BuildingAgent`, keeping in-memory state synchronized between route queries, live dispatch closures, and LLM chat.
   - It can be launched with a single standard command:
     `uv run python -m visualizer data/dev/proc-factory-dev-003` (or simply `python -m visualizer`).
   - Using `webbrowser.open(f"http://localhost:{port}")`, the browser window automatically pops up upon startup.

3. **2D / 3D Stacked Rendering Architecture via Three.js**:
   - *From Observation 1.3*: `building.json` contains exact polygon vertices in metres, floor elevations (`elevation_m`), and vertical connector mappings.
   - Three.js (WebGL) offers the highest fidelity and flexibility for multi-floor visualization:
     - **3D Stacked View**: Extrudes room polygons into floor slabs and walls at vertical height `elevation_m * vertical_scale`.
     - **Exploded View Slider**: An interactive slider multiplies the vertical spacing between floors (1.0x to 4.0x) so lower floors can be inspected without occlusion from upper floors.
     - **2D Top-Down Mode**: Instantly transitions the camera to an orthogonal top-down view centered on the active floor.
     - **Semantic Categorization**: Spaces are colored by `room_type` (Production: Amber `#f59e0b`; Offices: Slate `#3b82f6`; Labs: Purple `#8b5cf6`; Corridors: Off-white `#e2e8f0`; Lifts/Stairs: Emerald `#10b981`; Restrooms: Cyan `#0ea5e9`; Closed/Hazard: Red `#ef4444`).
     - **Vertical Shafts**: Glass/wireframe vertical elevator tubes and zigzag stair connectors visually bridge the stacked floor slabs.
     - **Assets & Equipment**: Rendered as 3D bounding boxes matching `footprint.width_m`, `footprint.depth_m`, and `rotation_deg`, with icon tags.
     - **Animated Navigation Routes**: A 3D glowing tube with a traveling light particle/beacon traverses through rooms, doors, stairs, and lifts at constant walking velocity, giving operators an intuitive visual simulation of the journey.
   - Self-containment: Vendor scripts (`three.min.js`, `OrbitControls.js`) can be placed locally in `visualizer/static/vendor/` to ensure 100% offline functionality.

4. **Real-Time Operational Dispatcher Workflow**:
   - *From Observation 1.4*: `BuildingMap` already provides `add_door(s1, s2)` and `set_closed(elem, bool)`.
   - The dispatcher GUI exposes:
     - **Connector & Zone Toggles**: One-click toggling of stairs, lifts, and rooms between Active and Closed. Closed elements are highlighted with 3D warning markers.
     - **Interactive Door Tool**: Click two adjacent spaces -> backend calls `add_door` -> verifies adjacency -> computes opening position -> immediately renders new door in neon green.
     - **Reactive Route Re-planning & Diff Visualization**: When any dispatch change occurs while a route is active:
       1. The system immediately recalculates the optimal path.
       2. Renders the previous path (dimmed dashed gray) alongside the new rerouted path (vibrant red/emerald).
       3. Displays an operational impact banner (e.g., *"Route updated: +14.2 m via Office Staircase"*).
       4. Audio alert triggers: *"Lift 1 closed. Rerouting via stairs."*

5. **Voice Navigation via Browser Web Speech API**:
   - *From Observation 1.1 & Hackathon README*: Voice-in and voice-out are explicitly rewarded under "Interaction (25 pts)" and "Presentation (Level 5)".
   - Implementation uses standard browser-native APIs:
     - **Speech-to-Text (`webkitSpeechRecognition` / `SpeechRecognition`)**:
       - Push-to-talk microphone button with animated audio-wave indicator.
       - Dual-mode intent parsing:
         - **Fast Local Parser**: Regex/pattern-matching for instant navigation and dispatch commands (<50ms):
           - *"Navigate to [destination]"*, *"Take me to the 3D printer"*, *"Close East Lift"*, *"Show Floor 2"*, *"Explode floors"*.
         - **Agent LLM Fallback**: Natural, ambiguous, or multi-step questions (e.g., *"Grab a stove and take it to the kitchen on floor 1"*) are forwarded to `/api/chat` running Claude with tools.
     - **Text-to-Speech (`window.speechSynthesis`)**:
       - Spoken turn-by-turn instructions: *"Start in Lobby. Walk 15 metres through the double doors into Corridor 0.01, then take Office Lift to Floor 1."*
       - Audio dispatch alerts when routes change dynamically.
     - **Graceful Fallback**: Text input prompt, keyboard shortcuts (`/` to focus, `Enter` to send), and visual transcript feed if microphone permissions are denied or unsupported.

---

## 3. Caveats

1. **Web Speech API Browser Compatibility**:
   - `webkitSpeechRecognition` is natively supported in Chromium-based browsers (Chrome, Edge, Brave) and Safari. In Firefox or headless environments, speech recognition may require microphone permissions or be disabled.
   - *Mitigation*: The UI includes a full-featured text search/chat bar and click-based interaction so all features work 100% seamlessly even without microphone hardware or browser support.
2. **Three.js Dependency Packaging**:
   - Relying on external CDNs (like unpkg or cdnjs) could fail if the evaluator runs offline.
   - *Mitigation*: Bundle standalone minified `three.min.js` and `OrbitControls.js` directly within the repository under `visualizer/static/vendor/` (~600 KB total), ensuring guaranteed zero-network offline functionality.
3. **Multi-Floor XY Frame Alignment**:
   - Note in `README.md` (lines 165–167): While procedural and OSM buildings share a unified XY frame across floors, some Swiss Dwellings buildings are centered per floor rather than aligned.
   - *Mitigation*: The 3D renderer centers each floor's bounding box when needed, or aligns floors using connector positions.

---

## 4. Conclusion & Proposed Architecture

We recommend packaging the interactive visualizer and operational dispatcher as a clean, modular Python package `visualizer/` with the following structure:

```
visualizer/
├── __init__.py
├── __main__.py          # Entry point: `uv run python -m visualizer [building_dir]`
├── server.py            # Zero-dependency ThreadingHTTPServer + REST API
├── dispatcher.py        # Dispatcher state manager (connectors, doors, hazards, diffs)
├── voice_nlp.py         # Fast deterministic intent parser for voice/text commands
└── static/              # Modern responsive Single-Page Application (SPA)
    ├── index.html       # Clean industrial dashboard UI
    ├── style.css        # Sleek dark/light theme with HUD telemetry
    ├── app.js           # Frontend controller, API integration, voice recognition
    ├── renderer.js      # Three.js 3D stacked multi-floor & 2D plan renderer
    ├── speech.js        # Web Speech API wrapper (STT & TTS with fallbacks)
    └── vendor/
        ├── three.min.js
        └── OrbitControls.js
```

### Key API Contracts

| Method | Endpoint | Description | Payload / Response |
|---|---|---|---|
| `GET` | `/api/buildings` | List available buildings in `data/dev` and `data/test` | Response: `[{"id": "...", "name": "...", "floors": 3, "spaces": 42}]` |
| `GET` | `/api/building` | Retrieve building metadata & layout | Param: `?id=...` -> Complete `building.json` + current closures |
| `POST` | `/api/route` | Compute multi-floor path | Request: `{"start": "...", "destination": "...", "step_free": bool, "via": [...]}`<br>Response: `{"length_m": 42.5, "space_path": [...], "points_3d": [[x,y,z], ...], "steps": [...]}` |
| `POST` | `/api/closure` | Toggle closure of lift/stair/room | Request: `{"element": "proc-factory-dev-003-V01", "closed": true}`<br>Response: `{"closed": [...], "rerouted": bool, "new_route": {...}}` |
| `POST` | `/api/add_door` | Create dynamic opening | Request: `{"first_space": "...", "second_space": "...", "step_free": true}`<br>Response: `{"opening": {...}, "rerouted": bool, "new_route": {...}}` |
| `POST` | `/api/chat` | Conversational voice/text agent | Request: `{"message": "..."}`<br>Response: `{"reply": "...", "speak_text": "...", "action": {...}}` |

---

## 5. Verification Method

To independently verify the requirements and feasibility:

1. **Verify Python Standard Library HTTP Server**:
   ```bash
   python3 -c "import http.server, webbrowser, json; print('Stdlib web server ready')"
   ```
2. **Verify Building Geometry & Routing Data Availability**:
   ```bash
   python3 -c "from starter_agent.building_map import BuildingMap; m = BuildingMap.load('data/dev/proc-factory-dev-003'); print(f'Floors: {len(m.floors)}, Spaces: {len(m.spaces)}, Connectors: {len(m.connectors)}')"
   ```
3. **Verify Dynamic Map Modification Capabilities**:
   ```bash
   python3 -c "from starter_agent.building_map import BuildingMap; m = BuildingMap.load('data/dev/proc-factory-dev-003'); m.set_closed('Office staircase', True); print('Closed elements:', m.closed)"
   ```
4. **Invalidation Conditions**:
   - The proposed architecture would be invalidated if:
     - Heavy third-party runtime frameworks (e.g. Node.js build steps, Docker containers) were required to run the visualizer.
     - The multi-floor route points did not reflect the benchmark's exact graph coordinate anchors and elevation levels.
     - Live dispatch modifications did not immediately propagate to subsequent route computations.

/**
 * Talk to Your Building — Interactive 2D/3D Multi-Floor Visualizer (app.js)
 * Implements Three.js WebGL multi-floor stacked/exploded rendering, route animation,
 * live dispatch controls, synthetic door insertion, and 2D Canvas fallback.
 */

class VisualizerApp {
  constructor() {
    this.currentBuildingId = null;
    this.building = null;
    this.floors = [];
    this.spaces = [];
    this.openings = [];
    this.connectors = [];
    this.assets = [];
    this.closedSet = new Set();
    this.currentRoute = null;

    this.activeFloorId = "all";
    this.viewMode = "3d";
    this.explodedScale = 1.0;

    // Three.js State
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.clock = null;
    this.raycaster = null;
    this.mouse = null;
    this.floorGroups = {};
    this.roomMeshes = [];
    this.connectorMeshes = [];
    this.routeTubeMesh = null;
    this.beaconMesh = null;
    this.routeCurve = null;
    this.isThreeAvailable = typeof THREE !== "undefined";

    // DOM Elements
    this.viewport = document.getElementById("viewport");
    this.fallbackCanvas = document.getElementById("fallbackCanvas");
    this.tooltip = document.getElementById("tooltip");
    this.buildingSelect = document.getElementById("buildingSelect");
    this.floorButtons = document.getElementById("floorButtons");
    this.explodeSlider = document.getElementById("explodeSlider");
    this.explodeValue = document.getElementById("explodeValue");
    this.btnMode3D = document.getElementById("btnMode3D");
    this.btnMode2D = document.getElementById("btnMode2D");
    this.btnResetView = document.getElementById("btnResetView");
    this.telemetryBadge = document.getElementById("telemetryBadge");
    this.viewModeTag = document.getElementById("viewModeTag");

    // Route inputs
    this.routeStartSelect = document.getElementById("routeStart");
    this.routeDestSelect = document.getElementById("routeDest");
    this.stepFreeCheck = document.getElementById("stepFreeCheck");
    this.minWidthInput = document.getElementById("minWidthInput");
    this.btnCalculateRoute = document.getElementById("btnCalculateRoute");
    this.btnClearRoute = document.getElementById("btnClearRoute");
    this.routeStatsCard = document.getElementById("routeStatsCard");
    this.statDistance = document.getElementById("statDistance");
    this.statTime = document.getElementById("statTime");
    this.statNodes = document.getElementById("statNodes");
    this.statStepFree = document.getElementById("statStepFree");
    this.directionsList = document.getElementById("directionsList");

    // Dispatch inputs
    this.connectorsList = document.getElementById("connectorsList");
    this.btnResetClosures = document.getElementById("btnResetClosures");
    this.doorRoomA = document.getElementById("doorRoomA");
    this.doorRoomB = document.getElementById("doorRoomB");
    this.btnAddDoor = document.getElementById("btnAddDoor");
    this.doorStatusMsg = document.getElementById("doorStatusMsg");

    // Assets
    this.assetsList = document.getElementById("assetsList");
    this.assetSearchInput = document.getElementById("assetSearchInput");

    // Initialize Voice Controller
    this.voice = new VoiceController(this);

    this._initUI();
    this._initScene();
    this.loadBuildingList();
  }

  _initUI() {
    // Sidebar Tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        const targetId = btn.getAttribute("data-tab");
        const targetContent = document.getElementById(targetId);
        if (targetContent) targetContent.classList.add("active");
      });
    });

    // Building Selector
    this.buildingSelect.addEventListener("change", (e) => {
      this.loadBuilding(e.target.value);
    });

    // View Mode Buttons
    this.btnMode3D.addEventListener("click", () => this.setViewMode("3d"));
    this.btnMode2D.addEventListener("click", () => this.setViewMode("2d"));

    // Exploded Spacing Slider
    this.explodeSlider.addEventListener("input", (e) => {
      this.explodedScale = parseFloat(e.target.value);
      this.explodeValue.textContent = `${this.explodedScale.toFixed(1)}x`;
      this.updateFloorVerticalPositions();
    });

    // Reset Camera View
    this.btnResetView.addEventListener("click", () => this.resetCamera());

    // Route Actions
    this.btnCalculateRoute.addEventListener("click", () => this.calculateRoute());
    this.btnClearRoute.addEventListener("click", () => this.clearRoute());

    // Dispatch Actions
    this.btnResetClosures.addEventListener("click", () => this.resetClosures());
    this.btnAddDoor.addEventListener("click", () => this.addSyntheticDoor());

    // Asset filter
    this.assetSearchInput.addEventListener("input", (e) => {
      this.renderAssetsList(e.target.value.trim().toLowerCase());
    });

    // Window Resize
    window.addEventListener("resize", () => this.onWindowResize());
  }

  _initScene() {
    if (!this.isThreeAvailable) {
      console.warn("Three.js not loaded. Falling back to 2D Canvas.");
      this.fallbackCanvas.classList.remove("hidden");
      this.draw2DFallback();
      return;
    }

    try {
      this.clock = new THREE.Clock();
      this.raycaster = new THREE.Raycaster();
      this.mouse = new THREE.Vector2(-999, -999);

      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0x0a0e17);

      const width = this.viewport.clientWidth;
      const height = this.viewport.clientHeight;

      this.camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 2000);
      this.camera.position.set(0, 50, 70);

      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.shadowMap.enabled = true;
      this.viewport.appendChild(this.renderer.domElement);

      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.maxPolarAngle = Math.PI / 2 - 0.05;

      // Lights
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
      this.scene.add(ambientLight);

      const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
      dirLight.position.set(40, 80, 50);
      this.scene.add(dirLight);

      const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.3);
      fillLight.position.set(-40, 20, -30);
      this.scene.add(fillLight);

      // Raycast hover & click
      this.renderer.domElement.addEventListener("mousemove", (e) => this.onMouseMove(e));
      this.renderer.domElement.addEventListener("click", (e) => this.onMouseClick(e));

      this.animate();
    } catch (err) {
      console.error("Failed to initialize Three.js WebGL scene:", err);
      this.isThreeAvailable = false;
      this.fallbackCanvas.classList.remove("hidden");
      this.draw2DFallback();
    }
  }

  animate() {
    if (!this.isThreeAvailable || !this.renderer) return;
    requestAnimationFrame(() => this.animate());

    if (this.controls) this.controls.update();

    // Animate beacon along route
    if (this.beaconMesh && this.routeCurve && this.clock) {
      const elapsed = this.clock.getElapsedTime();
      const loopTime = 6.0; // 6 seconds per route loop
      const t = (elapsed % loopTime) / loopTime;
      const pt = this.routeCurve.getPointAt(t);
      if (pt) {
        this.beaconMesh.position.copy(pt);
      }
    }

    this.renderer.render(this.scene, this.camera);
  }

  async loadBuildingList() {
    try {
      const res = await fetch("/api/buildings");
      const data = await res.json();
      if (data.status === "ok" && data.buildings.length > 0) {
        this.buildingSelect.innerHTML = "";
        let activeId = data.buildings[0].id;
        data.buildings.forEach((b) => {
          const opt = document.createElement("option");
          opt.value = b.id;
          opt.textContent = `${b.name} (${b.id}) [${b.floors} fl, ${b.spaces} rms]`;
          if (b.is_active) {
            opt.selected = true;
            activeId = b.id;
          }
          this.buildingSelect.appendChild(opt);
        });
        await this.loadBuilding(activeId);
      }
    } catch (err) {
      console.error("Failed to load building list:", err);
    }
  }

  async loadBuilding(buildingId) {
    try {
      this.telemetryBadge.textContent = "LOADING BUILDING DATA...";
      const res = await fetch(`/api/building?id=${encodeURIComponent(buildingId)}`);
      const data = await res.json();

      if (data.status === "ok" && data.building) {
        this.currentBuildingId = buildingId;
        this.building = data.building;
        this.floors = data.building.floors || [];
        this.spaces = data.building.spaces || [];
        this.openings = data.building.openings || [];
        this.connectors = data.building.connectors || [];
        this.assets = data.building.assets || [];
        this.closedSet = new Set(data.building.closed || []);

        this.telemetryBadge.textContent = `${this.building.name.toUpperCase()} // ${this.floors.length} FLOORS`;

        this.renderFloorButtons();
        this.populateDropdowns();
        this.renderConnectorsList();
        this.renderAssetsList();
        this.build3DScene();
        this.clearRoute();
      }
    } catch (err) {
      console.error("Failed to load building:", err);
      this.telemetryBadge.textContent = "ERROR LOADING BUILDING";
    }
  }

  renderFloorButtons() {
    this.floorButtons.innerHTML = "";

    const allBtn = document.createElement("button");
    allBtn.className = `hud-btn ${this.activeFloorId === "all" ? "active" : ""}`;
    allBtn.textContent = "ALL STACKED";
    allBtn.addEventListener("click", () => this.setActiveFloor("all"));
    this.floorButtons.appendChild(allBtn);

    this.floors.forEach((f) => {
      const btn = document.createElement("button");
      btn.className = `hud-btn ${this.activeFloorId === f.id ? "active" : ""}`;
      btn.textContent = `${f.name || "FL " + f.level} (${f.elevation_m}m)`;
      btn.addEventListener("click", () => this.setActiveFloor(f.id));
      this.floorButtons.appendChild(btn);
    });
  }

  setActiveFloor(floorId) {
    this.activeFloorId = floorId;
    this.renderFloorButtons();

    // Toggle 3D mesh visibility
    Object.keys(this.floorGroups).forEach((fId) => {
      const group = this.floorGroups[fId];
      if (group) {
        group.visible = (floorId === "all" || floorId === fId);
      }
    });

    if (floorId !== "all") {
      const fl = this.floors.find((f) => f.id === floorId);
      if (fl && this.controls) {
        // Focus camera on that floor
        this.controls.target.set(0, fl.elevation_m * this.explodedScale, 0);
      }
    } else {
      if (this.controls) this.controls.target.set(0, 5, 0);
    }

    if (!this.isThreeAvailable) {
      this.draw2DFallback();
    }
  }

  setViewMode(mode) {
    this.viewMode = mode;
    this.btnMode3D.classList.toggle("active", mode === "3d");
    this.btnMode2D.classList.toggle("active", mode === "2d");
    this.viewModeTag.textContent = `MODE: ${mode === "3d" ? "3D PERSPECTIVE" : "2D ORTHOGRAPHIC"}`;

    if (this.camera && this.controls) {
      if (mode === "2d") {
        this.camera.position.set(0, 100, 0);
        this.controls.target.set(0, 0, 0);
        this.controls.maxPolarAngle = 0; // Lock top-down
      } else {
        this.camera.position.set(0, 50, 70);
        this.controls.target.set(0, 5, 0);
        this.controls.maxPolarAngle = Math.PI / 2 - 0.05;
      }
      this.controls.update();
    }

    if (!this.isThreeAvailable) {
      this.draw2DFallback();
    }
  }

  resetCamera() {
    this.setViewMode("3d");
    this.explodedScale = 1.0;
    this.explodeSlider.value = "1.0";
    this.explodeValue.textContent = "1.0x";
    this.updateFloorVerticalPositions();
    if (this.controls) {
      this.controls.reset();
      this.camera.position.set(0, 50, 70);
      this.controls.target.set(0, 5, 0);
      this.controls.update();
    }
  }

  populateDropdowns() {
    const sortedSpaces = [...this.spaces].sort((a, b) =>
      (a.name || a.ref || a.id).localeCompare(b.name || b.ref || b.id)
    );

    const populate = (selectElem) => {
      selectElem.innerHTML = "";
      sortedSpaces.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.id;
        const fl = this.floors.find((f) => f.id === s.floor_id);
        const flLabel = fl ? `[${fl.name || "FL " + fl.level}]` : "";
        opt.textContent = `${flLabel} ${s.name || s.ref || s.id} (${s.room_type}, ${s.area}m²)`;
        selectElem.appendChild(opt);
      });
    };

    populate(this.routeStartSelect);
    populate(this.routeDestSelect);
    populate(this.doorRoomA);
    populate(this.doorRoomB);

    if (sortedSpaces.length >= 2) {
      this.routeStartSelect.selectedIndex = 0;
      this.routeDestSelect.selectedIndex = 1;
      this.doorRoomA.selectedIndex = 0;
      this.doorRoomB.selectedIndex = 1;
    }
  }

  renderConnectorsList() {
    this.connectorsList.innerHTML = "";
    if (this.connectors.length === 0) {
      this.connectorsList.innerHTML = "<p class='panel-hint'>No vertical connectors defined.</p>";
      return;
    }

    this.connectors.forEach((c) => {
      const isClosed = this.closedSet.has(c.id);
      const item = document.createElement("div");
      item.className = `connector-item ${isClosed ? "closed" : ""}`;

      const icon = c.kind === "lift" ? "🛗" : "🪜";
      const info = document.createElement("div");
      info.className = "connector-info";
      info.innerHTML = `
        <span class="connector-name">${icon} ${c.name || c.id}</span>
        <span class="connector-sub">${c.kind.toUpperCase()} // ${c.step_free ? "STEP-FREE" : "STAIRS"} (${c.floor_ids.length} floors)</span>
      `;

      const switchLabel = document.createElement("label");
      switchLabel.className = "toggle-switch";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !isClosed; // Checked = Open/Active

      input.addEventListener("change", () => {
        this.toggleClosure(c.id, !input.checked);
      });

      const slider = document.createElement("span");
      slider.className = "slider-switch";

      switchLabel.appendChild(input);
      switchLabel.appendChild(slider);

      item.appendChild(info);
      item.appendChild(switchLabel);
      this.connectorsList.appendChild(item);
    });
  }

  renderAssetsList(filterQuery = "") {
    this.assetsList.innerHTML = "";
    const filtered = this.assets.filter((a) => {
      if (!filterQuery) return true;
      return (
        a.name.toLowerCase().includes(filterQuery) ||
        a.type.toLowerCase().includes(filterQuery) ||
        a.category.toLowerCase().includes(filterQuery)
      );
    });

    if (filtered.length === 0) {
      this.assetsList.innerHTML = "<p class='panel-hint'>No matching assets found.</p>";
      return;
    }

    filtered.slice(0, 30).forEach((a) => {
      const item = document.createElement("div");
      item.className = "asset-item";
      const sp = this.spaces.find((s) => s.id === a.space_id);
      const spName = sp ? (sp.name || sp.ref || sp.id) : a.space_id;

      item.innerHTML = `
        <div class="asset-info">
          <span class="asset-name">⚙️ ${a.name || a.type}</span>
          <span class="asset-sub">In ${spName} // [${a.position[0]}, ${a.position[1]}]</span>
        </div>
      `;

      const routeBtn = document.createElement("button");
      routeBtn.className = "hud-btn mini";
      routeBtn.textContent = "NAVIGATE";
      routeBtn.addEventListener("click", () => {
        this.routeDestSelect.value = a.space_id;
        this.calculateRoute();
      });

      item.appendChild(routeBtn);
      this.assetsList.appendChild(item);
    });
  }

  build3DScene() {
    if (!this.isThreeAvailable || !this.scene) return;

    // Clear old objects
    Object.values(this.floorGroups).forEach((g) => this.scene.remove(g));
    this.floorGroups = {};
    this.roomMeshes = [];
    this.connectorMeshes = [];
    if (this.routeTubeMesh) {
      this.scene.remove(this.routeTubeMesh);
      this.routeTubeMesh = null;
    }
    if (this.beaconMesh) {
      this.scene.remove(this.beaconMesh);
      this.beaconMesh = null;
    }

    // Color definitions
    const getColor = (space) => {
      if (this.closedSet.has(space.id)) return 0xef4444; // Red
      const rt = (space.room_type || "").toLowerCase();
      if (rt.includes("production") || rt.includes("warehouse")) return 0xf59e0b; // Amber
      if (rt.includes("office") || rt.includes("meeting")) return 0x3b82f6; // Blue
      if (rt.includes("lab") || rt.includes("cleanroom")) return 0x8b5cf6; // Purple
      if (rt.includes("corridor") || rt.includes("hallway")) return 0x94a3b8; // Slate
      if (rt.includes("stair") || rt.includes("lift")) return 0x10b981; // Green
      return 0x64748b;
    };

    // Build floor slabs and room polygons
    this.floors.forEach((floor) => {
      const floorGroup = new THREE.Group();
      floorGroup.position.y = floor.elevation_m * this.explodedScale;
      this.floorGroups[floor.id] = floorGroup;
      this.scene.add(floorGroup);

      const floorSpaces = this.spaces.filter((s) => s.floor_id === floor.id);

      floorSpaces.forEach((space) => {
        if (!space.polygon || space.polygon.length < 3) return;

        const shape = new THREE.Shape();
        space.polygon.forEach((pt, idx) => {
          if (idx === 0) shape.moveTo(pt[0], pt[1]);
          else shape.lineTo(pt[0], pt[1]);
        });
        shape.closePath();

        const extrudeSettings = {
          depth: 0.3,
          bevelEnabled: false,
        };

        const geom = new THREE.ExtrudeGeometry(shape, extrudeSettings);
        geom.rotateX(-Math.PI / 2); // Horizontal in XZ plane

        const color = getColor(space);
        const mat = new THREE.MeshStandardMaterial({
          color: color,
          roughness: 0.4,
          metalness: 0.1,
          transparent: true,
          opacity: 0.85,
        });

        const mesh = new THREE.Mesh(geom, mat);
        mesh.userData = { space, floor };
        floorGroup.add(mesh);
        this.roomMeshes.push(mesh);

        // Room wireframe edge
        const edges = new THREE.EdgesGeometry(geom);
        const lineMat = new THREE.LineBasicMaterial({
          color: 0x1e293b,
          linewidth: 1,
        });
        const wireframe = new THREE.LineSegments(edges, lineMat);
        mesh.add(wireframe);
      });

      // Render assets on floor
      const floorAssets = this.assets.filter((a) => a.floor_id === floor.id);
      floorAssets.forEach((a) => {
        const boxGeom = new THREE.BoxGeometry(0.8, 0.8, 0.8);
        const boxMat = new THREE.MeshStandardMaterial({
          color: 0x38bdf8,
          emissive: 0x0284c7,
          roughness: 0.3,
        });
        const boxMesh = new THREE.Mesh(boxGeom, boxMat);
        boxMesh.position.set(a.position[0], 0.6, -a.position[1]);
        boxMesh.userData = { asset: a, floor };
        floorGroup.add(boxMesh);
      });
    });

    // Render vertical connector shafts (stairs and lifts)
    this.connectors.forEach((c) => {
      if (!c.space_ids || c.space_ids.length < 2) return;
      const spA = this.spaces.find((s) => s.id === c.space_ids[0]);
      const spB = this.spaces.find((s) => s.id === c.space_ids[1]);
      if (!spA || !spB) return;

      const flA = this.floors.find((f) => f.id === spA.floor_id);
      const flB = this.floors.find((f) => f.id === spB.floor_id);
      if (!flA || !flB) return;

      const yA = flA.elevation_m * this.explodedScale;
      const yB = flB.elevation_m * this.explodedScale;
      const minY = Math.min(yA, yB);
      const maxY = Math.max(yA, yB) + 3.0;
      const shaftHeight = Math.max(1.0, maxY - minY);

      const shaftGeom = new THREE.CylinderGeometry(1.2, 1.2, shaftHeight, 16);
      const isClosed = this.closedSet.has(c.id);
      const shaftMat = new THREE.MeshStandardMaterial({
        color: isClosed ? 0xef4444 : (c.kind === "lift" ? 0x10b981 : 0x06b6d4),
        transparent: true,
        opacity: 0.4,
        wireframe: true,
      });

      const shaftMesh = new THREE.Mesh(shaftGeom, shaftMat);
      shaftMesh.position.set(spA.representative_point[0], minY + shaftHeight / 2, -spA.representative_point[1]);
      shaftMesh.userData = { connector: c };
      this.scene.add(shaftMesh);
      this.connectorMeshes.push(shaftMesh);
    });
  }

  updateFloorVerticalPositions() {
    this.floors.forEach((f) => {
      const group = this.floorGroups[f.id];
      if (group) {
        group.position.y = f.elevation_m * this.explodedScale;
      }
    });

    // Rebuild route tube if active
    if (this.currentRoute && this.currentRoute.points_3d) {
      this.renderRoute3D(this.currentRoute.points_3d);
    }
  }

  async calculateRoute() {
    const start = this.routeStartSelect.value;
    const dest = this.routeDestSelect.value;
    if (!start || !dest) return;

    const stepFree = this.stepFreeCheck.checked;
    const minWidth = this.minWidthInput.value ? parseFloat(this.minWidthInput.value) : null;

    try {
      this.btnCalculateRoute.textContent = "CALCULATING...";
      const res = await fetch("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start,
          destination: dest,
          step_free: stepFree,
          min_width: minWidth,
          closed: Array.from(this.closedSet),
        }),
      });

      const data = await res.json();
      this.btnCalculateRoute.textContent = "CALCULATE OPTIMAL ROUTE";

      if (data.status === "ok") {
        this.currentRoute = data;
        this.displayRouteStats(data);
        this.renderRoute3D(data.points_3d);

        // Voice summary
        const spCount = data.space_path.length;
        const dist = data.distance.toFixed(1);
        this.voice.speak(`Optimal route calculated: ${dist} metres across ${spCount} rooms.`);
      } else {
        alert(data.error || "No reachable path found under current constraints.");
        this.clearRoute();
      }
    } catch (err) {
      console.error("Route calculation error:", err);
      this.btnCalculateRoute.textContent = "CALCULATE OPTIMAL ROUTE";
    }
  }

  displayRouteStats(data) {
    this.routeStatsCard.classList.remove("hidden");
    this.statDistance.textContent = `${data.distance.toFixed(1)} m`;
    const walkTimeSec = Math.round(data.distance / 1.3); // ~1.3 m/s walking speed
    this.statTime.textContent = `${walkTimeSec}s`;
    this.statNodes.textContent = `${data.path.length}`;
    this.statStepFree.textContent = data.step_free ? "YES" : "NO";

    this.directionsList.innerHTML = "";
    (data.steps || []).forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      this.directionsList.appendChild(li);
    });
  }

  clearRoute() {
    this.currentRoute = null;
    this.routeStatsCard.classList.add("hidden");
    if (this.routeTubeMesh && this.scene) {
      this.scene.remove(this.routeTubeMesh);
      this.routeTubeMesh = null;
    }
    if (this.beaconMesh && this.scene) {
      this.scene.remove(this.beaconMesh);
      this.beaconMesh = null;
    }
    this.routeCurve = null;
  }

  renderRoute3D(points3d) {
    if (!this.isThreeAvailable || !this.scene || !points3d || points3d.length < 2) return;

    if (this.routeTubeMesh) this.scene.remove(this.routeTubeMesh);
    if (this.beaconMesh) this.scene.remove(this.beaconMesh);

    // Convert raw 3D coords [x, y, z] to Three.js world [x, z * explodedScale, -y]
    const vectors = points3d.map(
      (p) => new THREE.Vector3(p[0], p[2] * this.explodedScale, -p[1])
    );

    this.routeCurve = new THREE.CatmullRomCurve3(vectors);
    const tubeGeom = new THREE.TubeGeometry(this.routeCurve, 128, 0.22, 8, false);

    const tubeMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0284c7,
      roughness: 0.2,
      metalness: 0.8,
    });

    this.routeTubeMesh = new THREE.Mesh(tubeGeom, tubeMat);
    this.scene.add(this.routeTubeMesh);

    // Traveling glowing beacon sphere
    const beaconGeom = new THREE.SphereGeometry(0.5, 16, 16);
    const beaconMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      emissive: 0x10b981,
      roughness: 0.1,
    });
    this.beaconMesh = new THREE.Mesh(beaconGeom, beaconMat);

    const beaconLight = new THREE.PointLight(0x10b981, 1.5, 8);
    this.beaconMesh.add(beaconLight);

    this.scene.add(this.beaconMesh);
  }

  async toggleClosure(elementId, isClosed) {
    try {
      const res = await fetch("/api/closures", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ element: elementId, closed: isClosed }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.closedSet = new Set(data.closed);
        this.renderConnectorsList();
        this.build3DScene();

        // Reroute dynamically if route is active
        if (this.currentRoute) {
          this.calculateRoute();
        }
      }
    } catch (err) {
      console.error("Closure toggle error:", err);
    }
  }

  async resetClosures() {
    try {
      const res = await fetch("/api/closures", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset: true }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.closedSet.clear();
        this.renderConnectorsList();
        this.build3DScene();
        if (this.currentRoute) this.calculateRoute();
        this.voice.speak("All closures reset. Facility open.");
      }
    } catch (err) {
      console.error("Reset closures error:", err);
    }
  }

  async addSyntheticDoor() {
    const spaceA = this.doorRoomA.value;
    const spaceB = this.doorRoomB.value;
    if (!spaceA || !spaceB) return;

    this.doorStatusMsg.className = "status-msg";
    this.doorStatusMsg.textContent = "Validating adjacency...";
    this.doorStatusMsg.classList.remove("hidden");

    try {
      const res = await fetch("/api/door", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ space_a: spaceA, space_b: spaceB }),
      });
      const data = await res.json();

      if (data.status === "ok") {
        this.doorStatusMsg.className = "status-msg success";
        this.doorStatusMsg.textContent = `Synthetic Door added at [${data.position[0]}, ${data.position[1]}]!`;
        this.voice.speak("Synthetic door added successfully. Re-evaluating spatial connectivity.");

        // Reload building data to reflect new door
        await this.loadBuilding(this.currentBuildingId);
        if (this.currentRoute) this.calculateRoute();
      } else {
        this.doorStatusMsg.className = "status-msg error";
        this.doorStatusMsg.textContent = data.error || "Cannot add door.";
      }
    } catch (err) {
      this.doorStatusMsg.className = "status-msg error";
      this.doorStatusMsg.textContent = `Error: ${err.message}`;
    }
  }

  executeAction(action, fullData) {
    if (!action) return;
    switch (action.type) {
      case "route":
        if (action.destination) {
          this.routeDestSelect.value = action.destination;
          if (action.start) this.routeStartSelect.value = action.start;
          this.calculateRoute();
        }
        break;
      case "close":
        if (action.element) {
          this.closedSet.add(action.element);
          this.toggleClosure(action.element, true);
        }
        break;
      case "open":
        if (action.element) {
          this.closedSet.delete(action.element);
          this.toggleClosure(action.element, false);
        }
        break;
      case "set_floor":
        const targetFloor = this.floors.find((f) => f.level === action.level);
        if (targetFloor) {
          this.setActiveFloor(targetFloor.id);
        }
        break;
      case "set_exploded":
        this.explodedScale = action.value;
        this.explodeSlider.value = String(action.value);
        this.explodeValue.textContent = `${action.value.toFixed(1)}x`;
        this.updateFloorVerticalPositions();
        break;
      case "set_view":
        this.setViewMode(action.mode);
        break;
      case "add_door":
        if (action.space_a && action.space_b) {
          this.doorRoomA.value = action.space_a;
          this.doorRoomB.value = action.space_b;
          this.addSyntheticDoor();
        }
        break;
      default:
        break;
    }
  }

  onMouseMove(event) {
    if (!this.raycaster || !this.camera || !this.roomMeshes.length) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.roomMeshes);

    if (intersects.length > 0) {
      const mesh = intersects[0].object;
      const sp = mesh.userData.space;
      const fl = mesh.userData.floor;
      if (sp) {
        this.tooltip.classList.remove("hidden");
        this.tooltip.style.left = `${event.clientX + 14}px`;
        this.tooltip.style.top = `${event.clientY + 14}px`;
        this.tooltip.innerHTML = `
          <strong>${sp.name || sp.ref || sp.id}</strong><br>
          Floor: ${fl ? fl.name || fl.level : sp.floor_id}<br>
          Type: ${sp.room_type}<br>
          Area: ${sp.area} m²<br>
          Status: ${this.closedSet.has(sp.id) ? "<span style='color:#ef4444'>CLOSED</span>" : "<span style='color:#10b981'>ACTIVE</span>"}
        `;
        return;
      }
    }
    this.tooltip.classList.add("hidden");
  }

  onMouseClick(event) {
    if (!this.raycaster || !this.camera || !this.roomMeshes.length) return;
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.roomMeshes);

    if (intersects.length > 0) {
      const sp = intersects[0].object.userData.space;
      if (sp) {
        if (event.shiftKey || !this.routeStartSelect.value) {
          this.routeStartSelect.value = sp.id;
        } else {
          this.routeDestSelect.value = sp.id;
          this.calculateRoute();
        }
      }
    }
  }

  onWindowResize() {
    if (!this.camera || !this.renderer || !this.viewport) return;
    const width = this.viewport.clientWidth;
    const height = this.viewport.clientHeight;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  draw2DFallback() {
    const canvas = this.fallbackCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = this.viewport.clientWidth || 800;
    const height = this.viewport.clientHeight || 600;
    canvas.width = width;
    canvas.height = height;

    ctx.fillStyle = "#0a0e17";
    ctx.fillRect(0, 0, width, height);

    if (!this.spaces || this.spaces.length === 0) return;

    // Filter spaces for active floor
    const displayedSpaces = this.spaces.filter(
      (s) => this.activeFloorId === "all" || s.floor_id === this.activeFloorId
    );

    // Find bounding box
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    displayedSpaces.forEach((s) => {
      (s.polygon || []).forEach(([x, y]) => {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      });
    });

    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const padding = 60;
    const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);

    const toCanvasX = (x) => padding + (x - minX) * scale;
    const toCanvasY = (y) => height - padding - (y - minY) * scale;

    // Draw rooms
    displayedSpaces.forEach((s) => {
      if (!s.polygon || s.polygon.length < 3) return;
      ctx.beginPath();
      s.polygon.forEach(([x, y], idx) => {
        const cx = toCanvasX(x);
        const cy = toCanvasY(y);
        if (idx === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      });
      ctx.closePath();

      ctx.fillStyle = this.closedSet.has(s.id) ? "rgba(239, 68, 68, 0.4)" : "rgba(56, 189, 248, 0.2)";
      ctx.fill();
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Label room
      const repX = toCanvasX(s.representative_point[0]);
      const repY = toCanvasY(s.representative_point[1]);
      ctx.fillStyle = "#f3f4f6";
      ctx.font = "10px monospace";
      ctx.fillText(s.name || s.ref || s.id, repX - 15, repY);
    });

    // Draw Route line
    if (this.currentRoute && this.currentRoute.points_3d) {
      ctx.beginPath();
      this.currentRoute.points_3d.forEach(([x, y, z], idx) => {
        const cx = toCanvasX(x);
        const cy = toCanvasY(y);
        if (idx === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      });
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 3;
      ctx.stroke();
    }
  }
}

// Instantiate on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.app = new VisualizerApp();
});

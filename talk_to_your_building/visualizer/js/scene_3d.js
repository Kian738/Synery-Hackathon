/**
 * 3D Isometric Multi-Floor Digital Twin Scene (Three.js WebGL)
 * Talk to Your Building — Track 01
 */

class Scene3D {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.floorsData = [];
    this.spacesData = [];
    this.assetsData = [];
    this.connectorsData = [];
    
    this.explodedFactor = 0.0;
    this.targetExplodedFactor = 0.0;
    this.spacingMultiplier = 5.0; // base vertical gap per level in meters

    this.activeRouteWaypoints = [];
    this.routeTubeMesh = null;
    this.guidanceAvatarMesh = null;
    this.routeProgress = 0.0;

    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2(-999, -999);
    this.hoveredObject = null;
    this.onSpaceClicked = null;

    this.initScene();
    this.initControls();
    this.animate();
  }

  initScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x070a12);
    this.scene.fog = new THREE.FogExp2(0x070a12, 0.005);

    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 2000);
    this.camera.position.set(60, 80, 100);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance"
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xf1f5f9, 0.7);
    this.scene.add(ambientLight);

    const hemiLight = new THREE.HemisphereLight(0x38bdf8, 0x0f172a, 0.6);
    this.scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xfffbeb, 1.2);
    dirLight.position.set(80, 140, 60);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.camera.near = 10;
    dirLight.shadow.camera.far = 400;
    const d = 120;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    this.scene.add(dirLight);

    // Ground Grid Helper
    this.grid = new THREE.GridHelper(300, 60, 0x0ea5e9, 0x1e293b);
    this.grid.position.y = -0.5;
    this.scene.add(this.grid);

    // Root Building Group
    this.buildingGroup = new THREE.Group();
    this.scene.add(this.buildingGroup);

    // Route Group
    this.routeGroup = new THREE.Group();
    this.scene.add(this.routeGroup);

    window.addEventListener('resize', () => this.onWindowResize());
    this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    this.canvas.addEventListener('click', (e) => this.onMouseClick(e));
  }

  initControls() {
    // Custom Orbit/Pan/Zoom navigation
    this.isDragging = false;
    this.isPanning = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.target = new THREE.Vector3(0, 0, 0);

    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = e.button === 0;
      this.isPanning = e.button === 2 || e.button === 1;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
      this.isPanning = false;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging && !this.isPanning) return;

      const deltaX = e.clientX - this.previousMousePosition.x;
      const deltaY = e.clientY - this.previousMousePosition.y;

      if (this.isDragging) {
        // Orbit rotation
        const offset = this.camera.position.clone().sub(this.target);
        const radius = offset.length();
        let theta = Math.atan2(offset.x, offset.z);
        let phi = Math.acos(Math.max(-1, Math.min(1, offset.y / radius)));

        theta -= deltaX * 0.006;
        phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.02, phi - deltaY * 0.006));

        this.camera.position.x = this.target.x + radius * Math.sin(phi) * Math.sin(theta);
        this.camera.position.y = this.target.y + radius * Math.cos(phi);
        this.camera.position.z = this.target.z + radius * Math.sin(phi) * Math.cos(theta);
        this.camera.lookAt(this.target);
      } else if (this.isPanning) {
        // Pan
        const panSpeed = 0.12;
        const forward = new THREE.Vector3();
        this.camera.getWorldDirection(forward);
        forward.y = 0;
        forward.normalize();
        const right = new THREE.Vector3().crossVectors(this.camera.up, forward).negate();

        const move = right.clone().multiplyScalar(deltaX * panSpeed)
          .add(forward.clone().multiplyScalar(deltaY * panSpeed));

        this.camera.position.add(move);
        this.target.add(move);
      }

      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY * 0.08;
      const offset = this.camera.position.clone().sub(this.target);
      const dist = offset.length();
      const newDist = Math.max(10, Math.min(800, dist + zoomFactor));
      offset.normalize().multiplyScalar(newDist);
      this.camera.position.copy(this.target).add(offset);
    }, { passive: false });
  }

  onWindowResize() {
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  setExplodedFactor(factor) {
    this.targetExplodedFactor = Math.max(0.0, Math.min(3.0, factor));
  }

  loadBuildingData(state) {
    // Clear previous models
    while (this.buildingGroup.children.length > 0) {
      const obj = this.buildingGroup.children[0];
      this.buildingGroup.remove(obj);
    }
    this.clearRoute();

    this.floorsData = state.floors || [];
    this.spacesData = state.spaces || [];
    this.assetsData = state.assets || [];
    this.connectorsData = state.vertical_connectors || [];

    // Calculate center offset of building
    let totalMinX = Infinity, totalMaxX = -Infinity;
    let totalMinY = Infinity, totalMaxY = -Infinity;

    this.floorsData.forEach(fl => {
      if (fl.bbox) {
        totalMinX = Math.min(totalMinX, fl.bbox[0]);
        totalMaxX = Math.max(totalMaxX, fl.bbox[2]);
        totalMinY = Math.min(totalMinY, fl.bbox[1]);
        totalMaxY = Math.max(totalMaxY, fl.bbox[3]);
      }
    });

    this.centerOffsetX = (totalMinX + totalMaxX) / 2 || 0;
    this.centerOffsetZ = (totalMinY + totalMaxY) / 2 || 0;

    // Build Floor Groups
    const floorGroupsMap = {};
    this.floorsData.forEach(fl => {
      const floorGroup = new THREE.Group();
      floorGroup.name = `floor_${fl.id}`;
      floorGroup.userData = { floorId: fl.id, elevation: fl.elevation_m, level: fl.level };
      this.buildingGroup.add(floorGroup);
      floorGroupsMap[fl.id] = floorGroup;
    });

    // 1. Build Spaces
    this.spacesData.forEach(space => {
      const floorGroup = floorGroupsMap[space.floor_id];
      if (!floorGroup || !space.polygon || space.polygon.length < 3) return;

      const shape = new THREE.Shape();
      const p0 = space.polygon[0];
      shape.moveTo(p0[0] - this.centerOffsetX, p0[1] - this.centerOffsetZ);

      for (let i = 1; i < space.polygon.length; i++) {
        const pt = space.polygon[i];
        shape.lineTo(pt[0] - this.centerOffsetX, pt[1] - this.centerOffsetZ);
      }
      shape.closePath();

      const geom = new THREE.ExtrudeGeometry(shape, {
        depth: 0.35,
        bevelEnabled: true,
        bevelSegments: 1,
        bevelSize: 0.05,
        bevelThickness: 0.05
      });
      geom.rotateX(Math.PI / 2);

      const color = this.getZoneColor(space.room_type, space.type);
      const mat = new THREE.MeshStandardMaterial({
        color: color,
        roughness: 0.45,
        metalness: 0.15,
        transparent: true,
        opacity: 0.92
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.name = `space_${space.id}`;
      mesh.receiveShadow = true;
      mesh.userData = { type: 'space', data: space };

      // Perimeter wireframe
      const edgesGeom = new THREE.EdgesGeometry(geom, 25);
      const edgesMat = new THREE.LineBasicMaterial({
        color: 0x64748b,
        linewidth: 1,
        transparent: true,
        opacity: 0.4
      });
      const edges = new THREE.LineSegments(edgesGeom, edgesMat);
      mesh.add(edges);

      floorGroup.add(mesh);
    });

    // 2. Build 3D Parametric Machinery and Assets
    this.assetsData.forEach(asset => {
      const floorGroup = floorGroupsMap[asset.floor_id];
      if (!floorGroup || !asset.position) return;

      const posX = asset.position[0] - this.centerOffsetX;
      const posZ = asset.position[1] - this.centerOffsetZ;
      const fp = asset.footprint || { width_m: 1.5, depth_m: 1.2, rotation_deg: 0 };

      const assetMesh = this.createParametricAssetMesh(asset, fp);
      assetMesh.position.set(posX, 0.35, posZ);
      if (fp.rotation_deg) {
        assetMesh.rotation.y = (fp.rotation_deg * Math.PI) / 180;
      }
      assetMesh.userData = { type: 'asset', data: asset };
      floorGroup.add(assetMesh);
    });

    // 3. Build Vertical Connectors (Elevator columns and stairs)
    this.connectorsData.forEach(conn => {
      this.createConnectorVisual(conn);
    });

    // Position camera to view entire building
    const spanX = Math.max(30, totalMaxX - totalMinX);
    const spanZ = Math.max(30, totalMaxY - totalMinY);
    const maxDim = Math.max(spanX, spanZ);

    this.target.set(0, 5, 0);
    this.camera.position.set(maxDim * 0.9, maxDim * 1.1, maxDim * 1.2);
    this.camera.lookAt(this.target);
  }

  getZoneColor(roomType, type) {
    const rt = (roomType || "").toLowerCase();
    const t = (type || "").toLowerCase();

    if (rt.includes("production") || rt.includes("manufacturing") || rt.includes("machine")) {
      return 0xf59e0b; // Amber
    }
    if (rt.includes("warehouse") || rt.includes("storage") || rt.includes("logistics")) {
      return 0x8b5cf6; // Purple
    }
    if (rt.includes("assembly") || rt.includes("workshop")) {
      return 0x3b82f6; // Indigo/Blue
    }
    if (rt.includes("cleanroom") || rt.includes("lab") || rt.includes("additive") || rt.includes("server")) {
      return 0x06b6d4; // Cyan
    }
    if (t.includes("corridor") || t.includes("hall") || t.includes("aisle")) {
      return 0x334155; // Slate
    }
    if (rt.includes("office") || rt.includes("meeting")) {
      return 0x10b981; // Emerald
    }
    return 0x475569;
  }

  createParametricAssetMesh(asset, footprint) {
    const w = Math.max(0.6, footprint.width_m || 1.2);
    const d = Math.max(0.6, footprint.depth_m || 1.0);
    const cat = (asset.category || "").toLowerCase();
    const type = (asset.type || "").toLowerCase();

    const group = new THREE.Group();

    if (cat.includes("machine") || type.includes("cnc") || type.includes("mill") || type.includes("lathe")) {
      // Machine Base
      const baseGeom = new THREE.BoxGeometry(w, 1.4, d);
      const baseMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        metalness: 0.8,
        roughness: 0.2
      });
      const base = new THREE.Mesh(baseGeom, baseMat);
      base.position.y = 0.7;
      base.castShadow = true;
      group.add(base);

      // CNC Tooling Console with Glowing Indicator
      const consoleGeom = new THREE.BoxGeometry(w * 0.4, 0.5, d * 0.3);
      const consoleMat = new THREE.MeshStandardMaterial({
        color: 0x0284c7,
        emissive: 0x06b6d4,
        emissiveIntensity: 0.4
      });
      const topConsole = new THREE.Mesh(consoleGeom, consoleMat);
      topConsole.position.set(0, 1.6, 0);
      group.add(topConsole);
    } else {
      // Standard Equipment Rack / Cabinet
      const geom = new THREE.BoxGeometry(w, 1.0, d);
      const mat = new THREE.MeshStandardMaterial({
        color: 0x475569,
        roughness: 0.6
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.y = 0.5;
      mesh.castShadow = true;
      group.add(mesh);
    }

    return group;
  }

  createConnectorVisual(conn) {
    // Elevators and Stairs rendered as multi-floor vertical columns
    const isLift = conn.kind.toLowerCase() === "lift";
    const color = isLift ? 0x06b6d4 : 0x10b981;

    // Find linked spaces to get representative positions
    const linkedSpaces = this.spacesData.filter(s => conn.space_ids.includes(s.id));
    if (linkedSpaces.length < 2) return;

    const s0 = linkedSpaces[0];
    const posX = s0.representative_point[0] - this.centerOffsetX;
    const posZ = s0.representative_point[1] - this.centerOffsetZ;

    const f0 = this.floorsData.find(f => f.id === s0.floor_id);
    const fTop = this.floorsData.find(f => f.id === linkedSpaces[linkedSpaces.length - 1].floor_id);
    const elevBottom = f0 ? f0.elevation_m : 0;
    const elevTop = fTop ? fTop.elevation_m + 3.0 : 8.0;
    const height = Math.max(4.0, elevTop - elevBottom);

    const geom = new THREE.BoxGeometry(2.5, height, 2.5);
    const mat = new THREE.MeshStandardMaterial({
      color: color,
      transparent: true,
      opacity: 0.35,
      roughness: 0.2,
      metalness: 0.6,
      wireframe: !isLift
    });

    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set(posX, elevBottom + height / 2, posZ);
    mesh.name = `connector_${conn.id}`;
    mesh.userData = { type: 'connector', data: conn };
    this.buildingGroup.add(mesh);
  }

  renderRoute(waypoints3D) {
    this.clearRoute();
    if (!waypoints3D || waypoints3D.length < 2) return;

    this.activeRouteWaypoints = waypoints3D;
    this.updateRouteGeometry();
  }

  updateRouteGeometry() {
    // Recompute 3D tube with exploded vertical offsets applied
    if (this.routeTubeMesh) {
      this.routeGroup.remove(this.routeTubeMesh);
      this.routeTubeMesh = null;
    }

    const points = this.activeRouteWaypoints.map(wp => {
      // Find floor level for this elevation to apply exploded view offset
      const elev = wp[2];
      let level = 0;
      const matchedFloor = this.floorsData.find(f => Math.abs(f.elevation_m - elev) < 0.8);
      if (matchedFloor) level = matchedFloor.level;

      const posX = wp[0] - this.centerOffsetX;
      const posZ = wp[1] - this.centerOffsetZ;
      const posY = elev + (level * this.spacingMultiplier * this.explodedFactor) + 0.6;

      return new THREE.Vector3(posX, posY, posZ);
    });

    if (points.length < 2) return;

    this.routeCurve = new THREE.CatmullRomCurve3(points, false, 'centripetal');
    const tubeGeom = new THREE.TubeGeometry(this.routeCurve, points.length * 12, 0.22, 8, false);

    const tubeMat = new THREE.MeshStandardMaterial({
      color: 0x00f5ff,
      emissive: 0x00f5ff,
      emissiveIntensity: 0.8,
      roughness: 0.1,
      metalness: 0.5
    });

    this.routeTubeMesh = new THREE.Mesh(tubeGeom, tubeMat);
    this.routeGroup.add(this.routeTubeMesh);

    // Traveling Guidance Avatar (Glowing Sphere)
    if (!this.guidanceAvatarMesh) {
      const avatarGeom = new THREE.SphereGeometry(0.5, 16, 16);
      const avatarMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0x22d3ee,
        emissiveIntensity: 1.5
      });
      this.guidanceAvatarMesh = new THREE.Mesh(avatarGeom, avatarMat);
      this.routeGroup.add(this.guidanceAvatarMesh);
    }
  }

  clearRoute() {
    while (this.routeGroup.children.length > 0) {
      this.routeGroup.remove(this.routeGroup.children[0]);
    }
    this.routeTubeMesh = null;
    this.guidanceAvatarMesh = null;
    this.activeRouteWaypoints = [];
  }

  onMouseMove(e) {
    const rect = this.canvas.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.buildingGroup.children, true);

    const tooltip = document.getElementById('hover-tooltip');

    if (intersects.length > 0) {
      const topObj = intersects[0].object;
      const uData = topObj.userData;

      if (uData && (uData.type === 'space' || uData.type === 'asset' || uData.type === 'connector')) {
        this.hoveredObject = uData;
        if (tooltip) {
          tooltip.style.display = 'block';
          tooltip.style.left = `${e.clientX + 14}px`;
          tooltip.style.top = `${e.clientY + 14}px`;

          if (uData.type === 'space') {
            tooltip.innerHTML = `<strong>${uData.data.name}</strong><br>Type: ${uData.data.room_type}<br>Area: ${uData.data.area} m²`;
          } else if (uData.type === 'asset') {
            tooltip.innerHTML = `<strong>${uData.data.name}</strong><br>Category: ${uData.data.category}<br>Type: ${uData.data.type}`;
          } else if (uData.type === 'connector') {
            tooltip.innerHTML = `<strong>${uData.data.name || uData.data.kind}</strong><br>Status: ${uData.data.isOperational ? 'Operational' : 'CLOSED'}`;
          }
        }
        return;
      }
    }

    this.hoveredObject = null;
    if (tooltip) tooltip.style.display = 'none';
  }

  onMouseClick(e) {
    if (this.hoveredObject && this.onSpaceClicked) {
      this.onSpaceClicked(this.hoveredObject);
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    // Smooth Exploded View Interpolation
    if (Math.abs(this.targetExplodedFactor - this.explodedFactor) > 0.002) {
      this.explodedFactor += (this.targetExplodedFactor - this.explodedFactor) * 0.12;
      
      // Update floor elevations
      this.floorsData.forEach(fl => {
        const grp = this.buildingGroup.getObjectByName(`floor_${fl.id}`);
        if (grp) {
          const baseY = fl.elevation_m;
          const explodeY = fl.level * this.spacingMultiplier * this.explodedFactor;
          grp.position.y = baseY + explodeY;
        }
      });

      // Recalibrate route ribbon points
      if (this.activeRouteWaypoints.length > 0) {
        this.updateRouteGeometry();
      }
    }

    // Animate Guidance Avatar along path
    if (this.routeCurve && this.guidanceAvatarMesh) {
      this.routeProgress = (this.routeProgress + 0.003) % 1.0;
      const pt = this.routeCurve.getPointAt(this.routeProgress);
      this.guidanceAvatarMesh.position.copy(pt);
    }

    this.renderer.render(this.scene, this.camera);
  }
}

/**
 * Application State Manager & Controller
 * Talk to Your Building — Track 01
 */

class App {
  constructor() {
    this.currentState = null;
    this.activeRoute = null;
    this.currentMode = '3d'; // '3d' or 'ar'
    this.vehicleProfile = 'pedestrian';

    // Components
    this.scene3d = new Scene3D(document.getElementById('scene3d-canvas'));
    this.arView = new ARView(
      document.getElementById('ar-video'),
      document.getElementById('ar-overlay-canvas')
    );
    this.voiceAgent = new VoiceAgent(
      (result) => this.onVoiceResult(result),
      (clarification) => this.showClarificationModal(clarification)
    );

    this.initEventListeners();
    this.loadBuildingList();
  }

  initEventListeners() {
    // 1. Building Selector
    const selectBuilding = document.getElementById('select-building');
    selectBuilding.addEventListener('change', (e) => {
      if (e.target.value) {
        this.loadBuildingState(e.target.value);
      }
    });

    // 2. Exploded View Slider
    const slider = document.getElementById('slider-explode');
    const sliderVal = document.getElementById('val-explode');
    slider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      sliderVal.textContent = `${val.toFixed(1)}x`;
      this.scene3d.setExplodedFactor(val);
    });

    // 3. Vehicle Profile Selector
    const selectVehicle = document.getElementById('select-vehicle');
    selectVehicle.addEventListener('change', (e) => {
      this.vehicleProfile = e.target.value;
      const checkStepFree = document.getElementById('check-step-free');
      if (this.vehicleProfile === 'step_free' || this.vehicleProfile === 'pallet_jack' || this.vehicleProfile === 'forklift') {
        checkStepFree.checked = true;
      }
      // Re-route if active
      if (this.activeRoute) {
        this.calculateRoute();
      }
    });

    // 4. Mode Toggle (3D vs AR)
    const btnToggleMode = document.getElementById('btn-toggle-mode');
    btnToggleMode.addEventListener('click', () => this.toggleMode());

    // 5. Voice Agent Mic Button
    const btnVoice = document.getElementById('btn-voice');
    btnVoice.addEventListener('click', () => this.voiceAgent.toggleListening());

    // 6. Calculate Route Button
    const btnCalc = document.getElementById('btn-calculate-route');
    btnCalc.addEventListener('click', () => this.calculateRoute());

    // 7. Demo Route Button
    const btnDemo = document.getElementById('btn-quick-errand');
    btnDemo.addEventListener('click', () => this.runDemoRoute());

    // 8. Add Dynamic Door Button
    const btnAddDoor = document.getElementById('btn-add-door');
    btnAddDoor.addEventListener('click', () => this.addDynamicDoor());

    // 9. Modal Cancel Button
    const btnCancelModal = document.getElementById('btn-modal-cancel');
    btnCancelModal.addEventListener('click', () => {
      document.getElementById('modal-backdrop').style.display = 'none';
    });

    // 10. 3D Scene Space Selection Callback
    this.scene3d.onSpaceClicked = (objData) => {
      if (objData.type === 'space') {
        const startSelect = document.getElementById('nav-start');
        const destSelect = document.getElementById('nav-dest');
        if (!startSelect.value) {
          startSelect.value = objData.data.id;
        } else {
          destSelect.value = objData.data.id;
          this.calculateRoute();
        }
      }
    };
  }

  async loadBuildingList() {
    try {
      const res = await fetch('/api/buildings');
      const data = await res.json();
      const select = document.getElementById('select-building');
      select.innerHTML = '';

      let defaultId = 'proc-factory-dev-003';
      data.buildings.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = `${b.id} (${b.name || b.split})`;
        if (b.id === defaultId || (!defaultId && select.children.length === 0)) {
          opt.selected = true;
          defaultId = b.id;
        }
        select.appendChild(opt);
      });

      this.loadBuildingState(defaultId);
    } catch (err) {
      console.error("Failed to load buildings list:", err);
    }
  }

  async loadBuildingState(buildingId) {
    try {
      const res = await fetch(`/api/building/state?building=${encodeURIComponent(buildingId)}`);
      const state = await res.json();
      this.currentState = state;

      this.scene3d.loadBuildingData(state);
      this.populateSpaceSelectors(state);
      this.populateIncidentControls(state);
    } catch (err) {
      console.error("Failed to load building state:", err);
    }
  }

  populateSpaceSelectors(state) {
    const startSelect = document.getElementById('nav-start');
    const destSelect = document.getElementById('nav-dest');
    const doorA = document.getElementById('door-space-a');
    const doorB = document.getElementById('door-space-b');

    [startSelect, destSelect, doorA, doorB].forEach(sel => sel.innerHTML = '');

    // Add spaces sorted by floor and name
    const sortedSpaces = [...state.spaces].sort((a, b) => a.name.localeCompare(b.name));

    sortedSpaces.forEach(sp => {
      const opt = document.createElement('option');
      opt.value = sp.id;
      opt.textContent = `${sp.name} [${sp.floor_id}]`;
      startSelect.appendChild(opt.cloneNode(true));
      destSelect.appendChild(opt.cloneNode(true));
      doorA.appendChild(opt.cloneNode(true));
      doorB.appendChild(opt.cloneNode(true));
    });

    if (destSelect.children.length > 5) {
      destSelect.selectedIndex = 5;
    }
    if (doorB.children.length > 1) {
      doorB.selectedIndex = 1;
    }
  }

  populateIncidentControls(state) {
    const list = document.getElementById('connectors-list');
    list.innerHTML = '';

    const closedSet = new Set(state.closed_elements || []);

    state.vertical_connectors.forEach(conn => {
      const isClosed = closedSet.has(conn.id);

      const row = document.createElement('div');
      row.className = 'connector-toggle-row';

      const label = document.createElement('span');
      label.className = 'connector-name';
      label.textContent = `${conn.name || conn.kind} (${conn.kind.toUpperCase()})`;

      const btn = document.createElement('button');
      btn.className = `btn-toggle-incident ${isClosed ? 'closed' : 'operational'}`;
      btn.textContent = isClosed ? 'CLOSED (ALERT)' : 'OPERATIONAL';

      btn.addEventListener('click', () => this.toggleConnectorIncident(conn.id));

      row.appendChild(label);
      row.appendChild(btn);
      list.appendChild(row);
    });

    // Update active incident counter
    const activeCountBadge = document.getElementById('active-incident-count');
    const alertsList = document.getElementById('incident-alerts-list');
    alertsList.innerHTML = '';

    const incidents = state.active_incidents || [];
    activeCountBadge.textContent = `${incidents.length} ACTIVE`;

    if (incidents.length === 0) {
      alertsList.innerHTML = '<p style="color: var(--text-dim); font-style: italic;">No active corridor or connector disruptions.</p>';
    } else {
      incidents.forEach(inc => {
        const item = document.createElement('div');
        item.style.padding = '6px 10px';
        item.style.background = 'rgba(239, 68, 68, 0.15)';
        item.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        item.style.borderRadius = '6px';
        item.innerHTML = `<strong>${inc.target_id}</strong>: ${inc.reason}`;
        alertsList.appendChild(item);
      });
    }
  }

  async toggleConnectorIncident(connectorId) {
    const activeNodes = this.activeRoute ? this.activeRoute.path_nodes : [];
    try {
      const res = await fetch('/api/incident', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'toggle',
          target_id: connectorId,
          reason: 'Manual operator toggle via digital twin',
          active_route_nodes: activeNodes
        })
      });
      const data = await res.json();

      // Refresh building state
      await this.loadBuildingState(this.currentState.building.id);

      // If active route was affected, trigger reroute
      if (this.activeRoute) {
        this.calculateRoute(true);
      }
    } catch (err) {
      console.error("Failed to toggle connector incident:", err);
    }
  }

  async addDynamicDoor() {
    const spaceA = document.getElementById('door-space-a').value;
    const spaceB = document.getElementById('door-space-b').value;

    if (!spaceA || !spaceB || spaceA === spaceB) {
      alert("Please select two distinct adjacent rooms to join with a synthetic door.");
      return;
    }

    try {
      const res = await fetch('/api/incident', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'add_door',
          params: { space_a: spaceA, space_b: spaceB, width_m: 1.0 },
          reason: 'Dynamic counterfactual door created'
        })
      });
      const data = await res.json();
      if (data.success) {
        this.voiceAgent.speak("Dynamic synthetic door added. Pathfinding topology updated.");
        await this.loadBuildingState(this.currentState.building.id);
        if (this.activeRoute) this.calculateRoute();
      } else {
        alert(data.error || "Failed to add door. Rooms must be adjacent on the same floor.");
      }
    } catch (err) {
      console.error("Add door failed:", err);
    }
  }

  async calculateRoute(isRerouteAlert = false) {
    const start = document.getElementById('nav-start').value;
    const dest = document.getElementById('nav-dest').value;
    const stepFree = document.getElementById('check-step-free').checked;

    let minWidth = 0.0;
    if (this.vehicleProfile === 'pallet_jack') minWidth = 1.2;
    if (this.vehicleProfile === 'forklift') minWidth = 1.5;

    if (!start || !dest) return;

    try {
      const res = await fetch('/api/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start: start,
          destination: dest,
          step_free: stepFree,
          min_width: minWidth,
          building: this.currentState.building.id
        })
      });
      const data = await res.json();

      if (!data.success) {
        alert(data.error_message || "Route calculation failed.");
        this.scene3d.clearRoute();
        return;
      }

      this.activeRoute = data;

      // Update 3D Scene route ribbon
      this.scene3d.renderRoute(data.waypoints);

      // Update AR view waypoints
      this.arView.setRoute(data.waypoints);

      // Update UI panels
      const summaryCard = document.getElementById('route-summary-card');
      const distVal = document.getElementById('route-distance-val');
      const stepsContainer = document.getElementById('landmark-steps-container');

      summaryCard.style.display = 'block';
      distVal.textContent = `${data.distance_m.toFixed(1)} m`;

      stepsContainer.innerHTML = '';
      data.landmark_instructions.forEach((step, idx) => {
        const item = document.createElement('div');
        item.className = 'step-item';
        item.innerHTML = `<span class="step-badge">${idx + 1}</span><span>${step}</span>`;
        stepsContainer.appendChild(item);
      });

      if (isRerouteAlert) {
        this.voiceAgent.speak("Route rerouted due to facility incident closure.");
      }
    } catch (err) {
      console.error("Route calculation error:", err);
    }
  }

  runDemoRoute() {
    if (!this.currentState) return;
    const f0Spaces = this.currentState.spaces.filter(s => s.floor_id.endsWith('F0') && s.type === 'room');
    const f1Spaces = this.currentState.spaces.filter(s => s.floor_id.endsWith('F1') && s.type === 'room');

    if (f0Spaces.length > 0 && f1Spaces.length > 0) {
      document.getElementById('nav-start').value = f0Spaces[0].id;
      document.getElementById('nav-dest').value = f1Spaces[f1Spaces.length - 1].id;
      this.calculateRoute();
      this.voiceAgent.speak("Plotting sample multi-floor route across elevations.");
    }
  }

  toggleMode() {
    const arViewport = document.getElementById('ar-viewport');
    const sceneCanvas = document.getElementById('scene3d-canvas');
    const btn = document.getElementById('btn-toggle-mode');
    const modeIcon = document.getElementById('mode-icon');
    const modeText = document.getElementById('mode-text');
    const explodeGroup = document.getElementById('group-exploded-view');

    if (this.currentMode === '3d') {
      this.currentMode = 'ar';
      arViewport.style.display = 'block';
      sceneCanvas.style.display = 'none';
      explodeGroup.style.display = 'none';
      modeIcon.textContent = '🏢';
      modeText.textContent = 'Switch to 3D Twin';
      this.arView.start();
    } else {
      this.currentMode = '3d';
      arViewport.style.display = 'none';
      sceneCanvas.style.display = 'block';
      explodeGroup.style.display = 'flex';
      modeIcon.textContent = '📱';
      modeText.textContent = 'Switch to Mobile AR';
      this.arView.stop();
    }
  }

  onVoiceResult(result) {
    if (result.intent === 'NAVIGATE' && result.route && result.route.success) {
      this.activeRoute = result.route;
      this.scene3d.renderRoute(result.route.waypoints);
      this.arView.setRoute(result.route.waypoints);

      const summaryCard = document.getElementById('route-summary-card');
      const distVal = document.getElementById('route-distance-val');
      const stepsContainer = document.getElementById('landmark-steps-container');

      summaryCard.style.display = 'block';
      distVal.textContent = `${result.route.distance_m.toFixed(1)} m`;

      stepsContainer.innerHTML = '';
      result.route.landmark_instructions.forEach((step, idx) => {
        const item = document.createElement('div');
        item.className = 'step-item';
        item.innerHTML = `<span class="step-badge">${idx + 1}</span><span>${step}</span>`;
        stepsContainer.appendChild(item);
      });
    } else if (result.intent === 'REPORT_INCIDENT' || result.intent === 'ADD_DOOR') {
      this.loadBuildingState(this.currentState.building.id);
    }
  }

  showClarificationModal(data) {
    const backdrop = document.getElementById('modal-backdrop');
    const promptText = document.getElementById('modal-prompt-text');
    const candidatesList = document.getElementById('modal-candidates-list');

    promptText.textContent = data.prompt;
    candidatesList.innerHTML = '';

    data.candidates.forEach((cand, idx) => {
      const btn = document.createElement('button');
      btn.className = 'candidate-btn';
      btn.innerHTML = `
        <span><strong>${idx + 1}.</strong> ${cand.name}</span>
        <span style="font-family: var(--font-mono); font-size: 11px; color: var(--cyan-bright);">${cand.type.toUpperCase()}</span>
      `;
      btn.addEventListener('click', () => {
        backdrop.style.display = 'none';
        document.getElementById('nav-dest').value = cand.space_id || cand.id;
        this.calculateRoute();
        this.voiceAgent.speak(`Routing to ${cand.name}.`);
      });
      candidatesList.appendChild(btn);
    });

    backdrop.style.display = 'flex';
  }
}

// Initialize on DOM load
window.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});

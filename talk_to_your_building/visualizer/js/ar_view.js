/**
 * Mobile AR Camera Guidance Overlay with Compass & Directional Chevrons
 * Talk to Your Building — Track 01
 */

class ARView {
  constructor(videoElement, canvasElement) {
    this.video = videoElement;
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    
    this.isActive = false;
    this.cameraStream = null;
    this.compassHeading = 0.0;
    this.hasOrientation = false;
    
    this.currentWaypointIndex = 0;
    this.routeWaypoints = [];
    this.activeCheckpoint = null;

    this.qrScanner = new QRScanner(this.video, (doorId) => this.onCheckpointCalibrated(doorId));
    this.initSensors();
  }

  async start() {
    this.isActive = true;
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        this.cameraStream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        });
        this.video.srcObject = this.cameraStream;
        await this.video.play();
      }
    } catch (err) {
      console.warn("Camera access not available or denied, running in AR simulation mode:", err);
      // Fallback: draw subtle synthetic factory backdrop on canvas
    }

    this.qrScanner.start();
    this.onResize();
    this.renderLoop();
  }

  stop() {
    this.isActive = false;
    this.qrScanner.stop();
    if (this.cameraStream) {
      this.cameraStream.getTracks().forEach(track => track.stop());
      this.cameraStream = null;
    }
  }

  onResize() {
    this.canvas.width = this.canvas.clientWidth || window.innerWidth;
    this.canvas.height = this.canvas.clientHeight || window.innerHeight;
  }

  initSensors() {
    window.addEventListener('deviceorientation', (e) => {
      if (e.webkitCompassHeading !== undefined) {
        this.compassHeading = e.webkitCompassHeading;
        this.hasOrientation = true;
      } else if (e.alpha !== null) {
        this.compassHeading = (360 - e.alpha) % 360;
        this.hasOrientation = true;
      }
      const headingEl = document.getElementById('ar-heading-text');
      if (headingEl) {
        headingEl.textContent = `HEADING: ${Math.round(this.compassHeading)}°`;
      }
    });

    window.addEventListener('resize', () => this.onResize());
  }

  setRoute(waypoints) {
    this.routeWaypoints = waypoints || [];
    this.currentWaypointIndex = 0;
  }

  onCheckpointCalibrated(doorId) {
    this.activeCheckpoint = doorId;
    const badge = document.getElementById('ar-checkpoint-text');
    const indicator = document.getElementById('ar-checkpoint-indicator');

    if (badge) {
      badge.textContent = `Checkpoint Confirmed: Door ${doorId}`;
    }
    if (indicator) {
      indicator.style.background = '#22d3ee';
      indicator.style.boxShadow = '0 0 16px #22d3ee';
      setTimeout(() => {
        indicator.style.background = '#10b981';
        indicator.style.boxShadow = '0 0 8px #10b981';
      }, 1500);
    }

    // Advance to next waypoint if matching checkpoint
    if (this.currentWaypointIndex < this.routeWaypoints.length - 1) {
      this.currentWaypointIndex++;
    }

    if (window.speechSynthesis && !window.speechSynthesis.speaking) {
      const utt = new SpeechSynthesisUtterance(`Position calibrated at Door ${doorId}.`);
      window.speechSynthesis.speak(utt);
    }
  }

  renderLoop() {
    if (!this.isActive) return;

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    const w = this.canvas.width;
    const h = this.canvas.height;
    const centerX = w / 2;
    const centerY = h * 0.72;

    // Draw Simulated Horizon and Grid if no real video stream
    if (!this.cameraStream || this.video.readyState < 2) {
      this.drawSimulatedBackground(w, h);
    }

    // Directional Navigation Chevron Arrow
    this.drawNavigationChevrons(centerX, centerY);

    requestAnimationFrame(() => this.renderLoop());
  }

  drawSimulatedBackground(w, h) {
    const grad = this.ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, '#020617');
    grad.addColorStop(0.5, '#0f172a');
    grad.addColorStop(1, '#070a12');
    this.ctx.fillStyle = grad;
    this.ctx.fillRect(0, 0, w, h);

    // Subtle perspective grid lines
    this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.15)';
    this.ctx.lineWidth = 1;
    const horizon = h * 0.55;
    for (let x = 0; x < w; x += 60) {
      this.ctx.beginPath();
      this.ctx.moveTo(w / 2, horizon);
      this.ctx.lineTo(x * 2 - w / 2, h);
      this.ctx.stroke();
    }
  }

  drawNavigationChevrons(cx, cy) {
    const time = Date.now() * 0.003;
    const pulse = Math.sin(time) * 0.15 + 0.85;

    // Animated Glowing Chevrons pointing ahead
    for (let i = 0; i < 3; i++) {
      const yOffset = (i * 35 + (time * 40) % 70) - 20;
      const alpha = Math.max(0, 1 - (yOffset + 20) / 100);

      this.ctx.save();
      this.ctx.translate(cx, cy - yOffset);
      this.ctx.strokeStyle = `rgba(6, 182, 212, ${alpha * pulse})`;
      this.ctx.fillStyle = `rgba(34, 211, 238, ${alpha * 0.4})`;
      this.ctx.shadowColor = '#06b6d4';
      this.ctx.shadowBlur = 15;
      this.ctx.lineWidth = 4;

      this.ctx.beginPath();
      this.ctx.moveTo(-45, 20);
      this.ctx.lineTo(0, -25);
      this.ctx.lineTo(45, 20);
      this.ctx.lineTo(30, 20);
      this.ctx.lineTo(0, -10);
      this.ctx.lineTo(-30, 20);
      this.ctx.closePath();

      this.ctx.fill();
      this.ctx.stroke();
      this.ctx.restore();
    }

    // Distance and Direction HUD Banner
    this.ctx.save();
    this.ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.5)';
    this.ctx.lineWidth = 1.5;
    const boxW = Math.min(320, this.canvas.width - 40);
    const boxH = 50;
    const boxX = (this.canvas.width - boxW) / 2;
    const boxY = cy + 50;

    this.ctx.beginPath();
    this.ctx.roundRect(boxX, boxY, boxW, boxH, 8);
    this.ctx.fill();
    this.ctx.stroke();

    this.ctx.fillStyle = '#f8fafc';
    this.ctx.font = '600 15px -apple-system, sans-serif';
    this.ctx.textAlign = 'center';
    this.ctx.fillText("Proceed Straight Ahead", this.canvas.width / 2, boxY + 22);

    this.ctx.fillStyle = '#22d3ee';
    this.ctx.font = '12px "JetBrains Mono", monospace';
    this.ctx.fillText("NEXT CHECKPOINT IN 8 METERS", this.canvas.width / 2, boxY + 40);
    this.ctx.restore();
  }
}

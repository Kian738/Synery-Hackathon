/**
 * Client-Side jsQR Code Doorway Checkpoint Scanner
 * Zero-Drift Absolute Calibration for Talk to Your Building
 */

class QRScanner {
  constructor(videoElement, onCheckpointDetected) {
    this.video = videoElement;
    this.onCheckpointDetected = onCheckpointDetected;
    this.isScanning = false;
    this.scanCanvas = document.createElement('canvas');
    this.scanCtx = this.scanCanvas.getContext('2d', { willReadFrequently: true });
    
    this.lastDetectedCode = null;
    this.lastDetectedTime = 0;
    this.cooldownMs = 3000;
  }

  start() {
    this.isScanning = true;
    this.scanLoop();
  }

  stop() {
    this.isScanning = false;
  }

  scanLoop() {
    if (!this.isScanning) return;

    if (this.video && this.video.readyState === this.video.HAVE_ENOUGH_DATA) {
      const vWidth = this.video.videoWidth || 640;
      const vHeight = this.video.videoHeight || 480;

      // Downsample to 480p for efficient 60fps frame processing
      const targetWidth = 480;
      const targetHeight = Math.round(targetWidth * (vHeight / vWidth));

      this.scanCanvas.width = targetWidth;
      this.scanCanvas.height = targetHeight;
      this.scanCtx.drawImage(this.video, 0, 0, targetWidth, targetHeight);

      const imageData = this.scanCtx.getImageData(0, 0, targetWidth, targetHeight);

      if (typeof jsQR !== 'undefined') {
        const qr = jsQR(imageData.data, imageData.width, imageData.height, {
          inversionAttempts: 'dontInvert'
        });

        if (qr && qr.data) {
          const now = Date.now();
          if (qr.data !== this.lastDetectedCode || (now - this.lastDetectedTime) > this.cooldownMs) {
            this.lastDetectedCode = qr.data;
            this.lastDetectedTime = now;
            this.handleCodeFound(qr.data);
          }
        }
      }
    }

    requestAnimationFrame(() => this.scanLoop());
  }

  handleCodeFound(payload) {
    let checkpointId = payload.trim();
    if (checkpointId.startsWith('checkpoint:door:')) {
      checkpointId = checkpointId.replace('checkpoint:door:', '');
    } else if (checkpointId.startsWith('door:')) {
      checkpointId = checkpointId.replace('door:', '');
    }

    if (navigator.vibrate) {
      navigator.vibrate([60, 40, 60]);
    }

    if (this.onCheckpointDetected) {
      this.onCheckpointDetected(checkpointId);
    }
  }
}

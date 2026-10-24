/**
 * Talk to Your Building — Web Speech Recognition & Guidance Engine (voice.js)
 * Implements push-to-talk SpeechRecognition and spoken SpeechSynthesis feedback
 * with deterministic fallback to textual command processing.
 */

class VoiceController {
  constructor(app) {
    this.app = app;
    this.recognition = null;
    this.isListening = false;
    this.audioEnabled = true;
    this.synth = window.speechSynthesis || null;

    this.micBtn = document.getElementById("btnMic");
    this.statusBadge = document.getElementById("voiceStatusBadge");
    this.statusText = document.getElementById("voiceStatusText");
    this.transcriptDisplay = document.getElementById("voiceTranscript");
    this.textInput = document.getElementById("voiceTextInput");
    this.sendBtn = document.getElementById("btnSendVoice");
    this.audioToggleBtn = document.getElementById("btnAudioToggle");

    this._initSpeechRecognition();
    this._bindEvents();
  }

  _initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
      this.recognition = new SpeechRec();
      this.recognition.continuous = false;
      this.recognition.interimResults = false;
      this.recognition.lang = "en-US";

      this.recognition.onstart = () => {
        this.isListening = true;
        this.updateStatus("LISTENING", "Listening for speech command...", "listening");
        if (this.micBtn) this.micBtn.classList.add("listening");
      };

      this.recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        this.updateStatus("PROCESSING", "Analyzing natural language command...", "processing");
        if (this.transcriptDisplay) {
          this.transcriptDisplay.textContent = `"${transcript}"`;
        }
        this.sendCommand(transcript);
      };

      this.recognition.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        this.updateStatus("READY", `Mic error (${event.error}). Type command below.`, "ready");
        this.isListening = false;
        if (this.micBtn) this.micBtn.classList.remove("listening");
      };

      this.recognition.onend = () => {
        this.isListening = false;
        if (this.micBtn) this.micBtn.classList.remove("listening");
      };
    } else {
      console.log("Web Speech API not natively available in this browser. Using text fallback.");
      this.updateStatus("TEXT MODE", "Microphone unavailable in browser. Type commands below.", "ready");
    }
  }

  _bindEvents() {
    if (this.micBtn) {
      this.micBtn.addEventListener("click", () => {
        if (!this.recognition) {
          this.updateStatus("INPUT", "Speech recognition unavailable. Please use text box.", "ready");
          if (this.textInput) this.textInput.focus();
          return;
        }

        if (this.isListening) {
          this.recognition.stop();
        } else {
          try {
            this.recognition.start();
          } catch (e) {
            console.warn("Recognition start failed:", e);
          }
        }
      });
    }

    if (this.sendBtn && this.textInput) {
      const handleSend = () => {
        const val = this.textInput.value.trim();
        if (val) {
          if (this.transcriptDisplay) {
            this.transcriptDisplay.textContent = `"${val}"`;
          }
          this.sendCommand(val);
          this.textInput.value = "";
        }
      };

      this.sendBtn.addEventListener("click", handleSend);
      this.textInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleSend();
      });
    }

    if (this.audioToggleBtn) {
      this.audioToggleBtn.addEventListener("click", () => {
        this.audioEnabled = !this.audioEnabled;
        if (this.audioEnabled) {
          this.audioToggleBtn.classList.add("active");
          this.audioToggleBtn.innerHTML = '<span class="icon">🔊</span> AUDIO ON';
          this.speak("Audio guidance enabled.");
        } else {
          this.audioToggleBtn.classList.remove("active");
          this.audioToggleBtn.innerHTML = '<span class="icon">🔇</span> AUDIO OFF';
          if (this.synth) this.synth.cancel();
        }
      });
    }
  }

  updateStatus(badgeText, statusText, badgeClass) {
    if (this.statusBadge) {
      this.statusBadge.textContent = badgeText;
      this.statusBadge.className = `status-badge ${badgeClass}`;
    }
    if (this.statusText) {
      this.statusText.textContent = statusText;
    }
  }

  speak(text) {
    if (!this.audioEnabled || !this.synth) return;
    try {
      this.synth.cancel(); // Stop prior speech
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.lang = "en-US";
      this.synth.speak(utterance);
    } catch (err) {
      console.warn("Speech synthesis error:", err);
    }
  }

  async sendCommand(transcript) {
    this.updateStatus("PROCESSING", "Dispatching to facility agent...", "processing");
    try {
      const res = await fetch("/api/voice_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript }),
      });
      const data = await res.json();

      if (data.response_text) {
        if (this.transcriptDisplay) {
          this.transcriptDisplay.textContent = `"${transcript}" → ${data.response_text}`;
        }
        this.speak(data.response_text);
      }

      this.updateStatus("READY", "Command executed. Ready.", "ready");

      // Execute dispatch action in app
      if (data.action && this.app) {
        this.app.executeAction(data.action, data);
      }
    } catch (err) {
      console.error("Voice command error:", err);
      this.updateStatus("ERROR", "Failed to dispatch command to server.", "ready");
    }
  }
}

window.VoiceController = VoiceController;

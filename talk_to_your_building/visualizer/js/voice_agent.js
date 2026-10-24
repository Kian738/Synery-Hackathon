/**
 * Hands-Free Bidirectional Voice Agent with SpeechRecognition & SpeechSynthesis
 * Talk to Your Building — Track 01
 */

class VoiceAgent {
  constructor(onVoiceQueryProcessed, onClarificationRequested) {
    this.onVoiceQueryProcessed = onVoiceQueryProcessed;
    this.onClarificationRequested = onClarificationRequested;

    this.recognition = null;
    this.isListening = false;
    this.isSpeaking = false;
    this.pendingCandidates = null;

    this.initSpeechRecognition();
    this.initSynthesis();
  }

  initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
      this.recognition = new SpeechRec();
      this.recognition.continuous = false;
      this.recognition.interimResults = false;
      this.recognition.lang = 'en-US';

      this.recognition.onstart = () => {
        this.isListening = true;
        this.updateUI();
      };

      this.recognition.onend = () => {
        this.isListening = false;
        this.updateUI();
      };

      this.recognition.onerror = (e) => {
        console.warn("Speech recognition error:", e.error);
        this.isListening = false;
        this.updateUI();
      };

      this.recognition.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        console.log("Voice transcript received:", transcript);
        this.handleTranscript(transcript);
      };
    } else {
      console.warn("SpeechRecognition API not supported in this browser.");
    }
  }

  initSynthesis() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = () => {
        this.voices = window.speechSynthesis.getVoices();
      };
    }
  }

  toggleListening() {
    if (!this.recognition) {
      // Simulate input prompt for environments without native Web Speech
      const promptText = prompt("Voice recognition not supported. Type your query (e.g. 'take me to CNC mill' or 'elevator V01 is down'):");
      if (promptText) {
        this.handleTranscript(promptText);
      }
      return;
    }

    if (this.isListening) {
      this.recognition.stop();
    } else {
      try {
        this.recognition.start();
      } catch (err) {
        console.error("Failed to start speech recognition:", err);
      }
    }
  }

  async handleTranscript(transcript) {
    const statusText = document.getElementById('voice-status-text');
    if (statusText) statusText.textContent = `Processing: "${transcript}"`;

    // Send to backend intent parser
    try {
      const resp = await fetch('/api/voice/intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: transcript })
      });
      const data = await resp.json();

      if (data.ambiguous && data.candidates) {
        this.pendingCandidates = data.candidates;
        this.speak(data.prompt);
        if (this.onClarificationRequested) {
          this.onClarificationRequested(data);
        }
      } else {
        this.pendingCandidates = null;
        this.speak(data.prompt);
        if (this.onVoiceQueryProcessed) {
          this.onVoiceQueryProcessed(data);
        }
      }
    } catch (err) {
      console.error("Voice intent processing failed:", err);
      this.speak("Sorry, I could not connect to the spatial dispatcher.");
    }
  }

  speak(text) {
    if (!text || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    // Pick a natural English voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha')));
    if (preferredVoice) utterance.voice = preferredVoice;

    utterance.onstart = () => {
      this.isSpeaking = true;
      this.updateUI();
    };

    utterance.onend = () => {
      this.isSpeaking = false;
      this.updateUI();
    };

    utterance.onerror = () => {
      this.isSpeaking = false;
      this.updateUI();
    };

    window.speechSynthesis.speak(utterance);
  }

  updateUI() {
    const btn = document.getElementById('btn-voice');
    const bar = document.getElementById('voice-indicator-bar');
    const statusText = document.getElementById('voice-status-text');

    if (btn) {
      if (this.isListening) {
        btn.classList.add('listening');
      } else {
        btn.classList.remove('listening');
      }
    }

    if (bar) {
      if (this.isSpeaking) {
        bar.classList.add('speaking');
        if (statusText) statusText.textContent = "Speaking...";
      } else {
        bar.classList.remove('speaking');
        if (statusText && !this.isListening) statusText.textContent = "Voice Idle";
      }
    }

    if (statusText && this.isListening) {
      statusText.textContent = "Listening...";
    }
  }
}

// Voice in/out. Integrates server-side TTS (ElevenLabs / OpenAI) with automatic fallback to Web Speech API.
// Language is strictly English (en-US) for both recognition and speech synthesis.

const Recognition: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export const canListen = () => Boolean(Recognition);
export const canSpeak = () => typeof window !== "undefined" && ("speechSynthesis" in window || typeof Audio !== "undefined");

let activeAudio: HTMLAudioElement | null = null;
let activeUtterance: SpeechSynthesisUtterance | null = null;
let activeBlobUrl: string | null = null;

let englishVoice: SpeechSynthesisVoice | null = null;

if (typeof window !== "undefined" && "speechSynthesis" in window) {
  const updateVoices = () => {
    const voices = window.speechSynthesis.getVoices();
    englishVoice =
      voices.find((v) => (v.lang === "en-US" || v.lang === "en_US") && v.name.includes("Samantha")) ||
      voices.find((v) => (v.lang === "en-US" || v.lang === "en_US") && v.localService) ||
      voices.find((v) => v.lang === "en-US" || v.lang === "en_US") ||
      voices.find((v) => v.lang.startsWith("en")) ||
      null;
  };
  updateVoices();
  window.speechSynthesis.onvoiceschanged = updateVoices;
}

/**
 * Queue for real-time streaming audio chunks from ElevenLabs.
 * Plays sequential audio chunks with zero gap and dispatches speech events.
 */
export class AudioStreamQueue {
  private queue: { index: number; url: string; text?: string }[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private currentUrl: string | null = null;
  private isPlaying = false;
  private isStreamActive = false;
  public hadChunks = false;
  private onEndCallbacks: (() => void)[] = [];

  reset() {
    this.stop();
    this.hadChunks = false;
    this.isStreamActive = true;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
      activeUtterance = null;
    }
    if (activeAudio) {
      try {
        activeAudio.pause();
        activeAudio.currentTime = 0;
      } catch {}
      activeAudio = null;
    }
  }

  markDone() {
    this.isStreamActive = false;
    if (!this.isPlaying && this.queue.length === 0) {
      this.notifyEnd();
    }
  }

  stop() {
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } catch {}
      this.currentAudio = null;
    }
    if (this.currentUrl) {
      URL.revokeObjectURL(this.currentUrl);
      this.currentUrl = null;
    }
    for (const item of this.queue) {
      URL.revokeObjectURL(item.url);
    }
    this.queue = [];
    const wasPlaying = this.isPlaying;
    this.isPlaying = false;
    this.isStreamActive = false;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
      activeUtterance = null;
    }
    if (activeAudio) {
      try {
        activeAudio.pause();
        activeAudio.currentTime = 0;
      } catch {}
      activeAudio = null;
    }
    if (wasPlaying && typeof window !== "undefined") {
      window.dispatchEvent(new Event("floorwise:speech-end"));
    }
  }

  enqueue(base64Audio: string, index = 0, text?: string) {
    this.hadChunks = true;
    // Silence browser speech synthesis as soon as real audio chunks arrive
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
      activeUtterance = null;
    }
    if (activeAudio) {
      try {
        activeAudio.pause();
        activeAudio.currentTime = 0;
      } catch {}
      activeAudio = null;
    }
    try {
      const binary = atob(base64Audio);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);
      this.queue.push({ index, url, text });
      this.queue.sort((a, b) => a.index - b.index);

      if (!this.isPlaying) {
        this.playNext();
      }
    } catch (e) {
      console.warn("Failed to decode audio chunk:", e);
    }
  }

  private playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      if (!this.isStreamActive) {
        this.notifyEnd();
      }
      return;
    }

    const next = this.queue.shift()!;
    this.isPlaying = true;
    this.currentUrl = next.url;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
      activeUtterance = null;
    }
    if (activeAudio) {
      try {
        activeAudio.pause();
        activeAudio.currentTime = 0;
      } catch {}
      activeAudio = null;
    }
    const audio = new Audio(next.url);
    this.currentAudio = audio;

    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("floorwise:speech-start"));
      if (next.text) {
        window.dispatchEvent(
          new CustomEvent("floorwise:speech-chunk", {
            detail: { index: next.index, text: next.text, audio },
          })
        );
      }
    }

    audio.onended = () => {
      if (this.currentUrl) {
        URL.revokeObjectURL(this.currentUrl);
        this.currentUrl = null;
      }
      this.currentAudio = null;
      this.playNext();
    };

    audio.onerror = (e) => {
      console.warn("Error playing audio chunk:", e);
      if (this.currentUrl) {
        URL.revokeObjectURL(this.currentUrl);
        this.currentUrl = null;
      }
      this.currentAudio = null;
      this.playNext();
    };

    audio.play().catch((err) => {
      console.warn("audio.play() rejected:", err);
      audio.onended?.(new Event("ended") as any);
    });
  }

  private notifyEnd() {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("floorwise:speech-end"));
    }
    const cbs = [...this.onEndCallbacks];
    this.onEndCallbacks = [];
    for (const cb of cbs) {
      try {
        cb();
      } catch {}
    }
  }

  onEnd(cb: () => void) {
    if (!this.isPlaying && !this.isStreamActive) {
      cb();
    } else {
      this.onEndCallbacks.push(cb);
    }
  }

  get active(): boolean {
    return this.isPlaying;
  }
}

export const audioStreamQueue = new AudioStreamQueue();

export function isSpeaking(): boolean {
  if (audioStreamQueue.active) return true;
  if (activeAudio && !activeAudio.paused && !activeAudio.ended) return true;
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    return window.speechSynthesis.speaking;
  }
  return false;
}

export function stopSpeaking() {
  const wasSpeaking = isSpeaking();
  audioStreamQueue.stop();
  if (activeAudio) {
    try {
      activeAudio.pause();
      activeAudio.currentTime = 0;
    } catch {}
    activeAudio = null;
  }
  if (activeBlobUrl) {
    URL.revokeObjectURL(activeBlobUrl);
    activeBlobUrl = null;
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch {}
    activeUtterance = null;
  }
  // Only dispatch speech-end if we were actually speaking, avoiding unwanted re-render cascades
  if (wasSpeaking && typeof window !== "undefined") {
    window.dispatchEvent(new Event("floorwise:speech-end"));
  }
}

export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "") // remove code blocks
    .replace(/`([^`]+)`/g, "$1")     // remove inline code markers
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1") // replace markdown links with label
    .replace(/\*\*(.*?)\*\*/g, "$1") // bold
    .replace(/\*(.*?)\*/g, "$1")   // italic
    .replace(/^#+\s+/gm, "")         // headers
    .replace(/^Answer:\s*/gim, "")   // prompt artifacts
    .replace(/^[-*•]\s+/gm, "")      // list bullets
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Normalizes language tags strictly to English ("en-US")
 */
export function normalizeLanguageTag(_lang?: string): string {
  return "en-US";
}

/**
 * Speak text out loud in English.
 * Attempts cloud TTS (/api/tts with ElevenLabs or OpenAI) first,
 * and seamlessly falls back to browser speechSynthesis with an English voice.
 */
export async function speak(text: string, onEnd?: () => void) {
  stopSpeaking();
  if (audioStreamQueue.active || audioStreamQueue.hadChunks) {
    onEnd?.();
    return;
  }
  const clean = cleanTextForSpeech(text);
  if (!clean) {
    onEnd?.();
    return;
  }

  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("floorwise:speech-start"));
  }

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    stopSpeaking();
    onEnd?.();
  };

  // 1. Try server-side TTS (ElevenLabs / OpenAI)
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    });

    if (res.ok && res.headers.get("content-type")?.includes("audio")) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      activeBlobUrl = url;
      const audio = new Audio(url);
      activeAudio = audio;

      audio.onended = () => {
        finish();
      };
      audio.onerror = () => {
        // Fallback to browser synthesis on audio playback error
        speakBrowser(clean, finish);
      };

      try {
        await audio.play();
        return;
      } catch (playErr) {
        console.warn("Audio play rejected, falling back to browser synthesis:", playErr);
        speakBrowser(clean, finish);
        return;
      }
    }
  } catch {
    // Server TTS not available or network error -> proceed to browser fallback
  }

  // 2. Fallback to browser speechSynthesis
  speakBrowser(clean, finish);
}

function speakBrowser(clean: string, onEnd: () => void) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    onEnd();
    return;
  }
  if (audioStreamQueue.active || audioStreamQueue.hadChunks) {
    onEnd();
    return;
  }

  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(clean);
  activeUtterance = u;

  // Language is strictly English (en-US)
  u.lang = "en-US";
  u.rate = 1.05;

  if (englishVoice) {
    u.voice = englishVoice;
  } else if (typeof window.speechSynthesis.getVoices === "function") {
    const voices = window.speechSynthesis.getVoices();
    const voice =
      voices.find((v) => (v.lang === "en-US" || v.lang === "en_US") && v.name.includes("Samantha")) ||
      voices.find((v) => v.lang === "en-US" || v.lang === "en_US") ||
      voices.find((v) => v.lang.startsWith("en"));
    if (voice) {
      englishVoice = voice;
      u.voice = voice;
    }
  }

  u.onend = () => {
    activeUtterance = null;
    onEnd();
  };

  u.onerror = (e) => {
    if (e.error !== "canceled" && e.error !== "interrupted") {
      console.warn("Speech synthesis error:", e.error);
    }
    activeUtterance = null;
    onEnd();
  };

  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("floorwise:speech-chunk", {
        detail: { index: 0, text: clean },
      })
    );
  }

  window.speechSynthesis.speak(u);
}

export function listen(
  onPartial: (t: string) => void,
  onFinal: (t: string) => void,
  onEnd: () => void,
  onError?: (message: string) => void,
  lang: string = "en-US"
): (submitIfText?: boolean) => void {
  if (!Recognition) {
    onError?.("Voice input is unavailable in this browser. Type your request instead.");
    onEnd();
    return () => {};
  }

  // Request browser microphone permission prompt if not yet granted
  if (typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      stream.getTracks().forEach((track) => track.stop());
    }).catch((err) => {
      console.warn("Microphone access check:", err);
    });
  }

  const r = new Recognition();
  // Strictly English (en-US)
  r.lang = lang || "en-US";
  r.interimResults = true;
  r.continuous = true;

  let latestTranscript = "";
  let finished = false;
  let silenceTimer: any = null;

  // 2.0s silence buffer gives user comfortable breathing/thinking room without premature cutoff
  const SILENCE_TIMEOUT_MS = 2000;

  const finish = (send: boolean, textToSend?: string) => {
    if (finished) return;
    finished = true;
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    try {
      r.stop();
    } catch {}
    const text = (textToSend ?? latestTranscript).trim();
    if (send && text) {
      onFinal(text);
    } else {
      onEnd();
    }
  };

  const resetSilenceTimer = (textToSubmit: string) => {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (!finished && textToSubmit.trim()) {
        finish(true, textToSubmit);
      }
    }, SILENCE_TIMEOUT_MS);
  };

  r.onresult = (event: any) => {
    if (finished) return;
    let accumulatedFinal = "";
    let interim = "";
    for (let i = 0; i < event.results.length; i++) {
      const res = event.results[i];
      if (res.isFinal) {
        accumulatedFinal += res[0].transcript;
      } else {
        interim += res[0].transcript;
      }
    }
    const current = (accumulatedFinal + interim).trim();
    if (current) {
      latestTranscript = current;
      onPartial(current);
      resetSilenceTimer(current);
    }
  };

  r.onerror = (event: any) => {
    console.warn("SpeechRecognition error:", event.error, event);
    // 'no-speech' (user was silent) and 'aborted' (user or app stopped listening) are NOT errors
    if (event.error === "no-speech" || event.error === "aborted") {
      finish(false);
      return;
    }

    let message = `Voice input error (${event.error}). Please retry or type your request.`;
    if (event.error === "not-allowed") {
      message = "Microphone access was denied. Please allow microphone access in your browser address bar.";
    } else if (event.error === "network") {
      message = "Speech network error. Note: In Chrome/Brave, Web Speech requires internet connection to Google services (check Brave Shields if using Brave).";
    } else if (event.error === "audio-capture") {
      message = "No microphone found. Please check your Mac's audio input in System Settings.";
    } else if (event.error === "service-not-allowed") {
      message = "Speech recognition service is disabled or blocked by your browser settings.";
    } else if (event.error === "language-not-supported") {
      message = `Language '${r.lang}' is not supported by speech recognition.`;
    }

    onError?.(message);
    finish(false);
  };

  r.onend = () => {
    if (!finished) {
      finish(Boolean(latestTranscript.trim()));
    }
  };

  try {
    r.start();
  } catch (err: any) {
    console.warn("SpeechRecognition start exception:", err);
    onError?.("Voice input could not start. Please retry.");
    finish(false);
  }

  return (submitIfText = false) => {
    finish(submitIfText && Boolean(latestTranscript.trim()));
    try {
      r.abort();
    } catch {}
  };
}

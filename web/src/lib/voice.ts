// Voice in/out. Output goes through ONE speaker (lib/speaker.ts): one voice at a time, ElevenLabs through the server proxy
// (/api/voice/tts), the browser voice only when the server voice fails. Language is English (en-US). Design: docs/VOICE_DESIGN.md.
import { useSyncExternalStore } from "react";
import { cleanTextForSpeech, createSpeaker, type Backend, type Channel, type EndReason, type Fetched, type SayOptions, type SpeakerState } from "./speaker";

export { cleanTextForSpeech, splitSentences, PRIORITY } from "./speaker";
export type { Channel, EndReason, SayOptions, SpeakerState } from "./speaker";

const hasWindow = typeof window !== "undefined";
const Recognition: any = hasWindow ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export const canListen = () => Boolean(Recognition);
export const canSpeak = () => hasWindow && ("speechSynthesis" in window || typeof Audio !== "undefined");

// ---------- browser backend ----------

let englishVoice: SpeechSynthesisVoice | null = null;
const pickVoice = () => {
  if (!hasWindow || !("speechSynthesis" in window) || typeof window.speechSynthesis.getVoices !== "function") return null;
  const voices = window.speechSynthesis.getVoices() ?? [];
  const us = (v: SpeechSynthesisVoice) => v.lang === "en-US" || v.lang === "en_US";
  englishVoice = voices.find(v => us(v) && v.name.includes("Samantha")) || voices.find(v => us(v) && v.localService) || voices.find(us) || voices.find(v => v.lang?.startsWith("en")) || null;
  return englishVoice;
};
if (hasWindow && "speechSynthesis" in window) { try { pickVoice(); window.speechSynthesis.addEventListener?.("voiceschanged", pickVoice); } catch { /* old browsers */ } }

/** One audio element for every server clip: two clips can never overlap, and once a tap has unlocked it (iOS) later clips play too. */
let element: HTMLAudioElement | null = null;
const audio = () => (element ??= new Audio());
let unlockUrl: string | null = null;

let status: Promise<boolean> | null = null;
const serverVoice = () => (status ??= fetch("/api/voice/status").then(r => (r.ok ? r.json() : null)).then(j => Boolean(j?.tts)).catch(() => false));

const browserBackend: Backend<string> = {
  async fetch(text, context, signal): Promise<Fetched<string>> {
    if (!(await serverVoice())) return { off: "permanent" };
    try {
      const res = await fetch("/api/voice/tts", { method: "POST", signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, previous_text: context.previous, next_text: context.next }) });
      if (!res.ok || !res.headers.get("content-type")?.includes("audio")) return { off: [401, 403, 429, 503].includes(res.status) ? "permanent" : "transient" };
      return { clip: URL.createObjectURL(await res.blob()) };
    } catch (e) {
      return { off: (e as Error)?.name === "AbortError" ? "aborted" : "transient" };
    }
  },
  playClip(url, on) {
    const el = audio();
    el.onended = () => on.end();
    el.onerror = () => on.fail(false);
    el.src = url;
    el.play().then(() => on.start(Number.isFinite(el.duration) ? el.duration : undefined)).catch((e: Error) => { if (e?.name !== "AbortError") on.fail(e?.name === "NotAllowedError"); });
    return { stop: () => { el.onended = null; el.onerror = null; try { el.pause(); } catch { /* not started */ } } };
  },
  speakBrowser(text, on) {
    if (!hasWindow || !("speechSynthesis" in window)) return null;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 1.05;
    const voice = englishVoice ?? pickVoice();
    if (voice) u.voice = voice;
    u.onstart = () => on.start();
    u.onend = () => on.end();
    u.onerror = (e: SpeechSynthesisErrorEvent) => { if (e?.error === "canceled" || e?.error === "interrupted") return; on.fail(e?.error === "not-allowed"); };
    window.speechSynthesis.speak(u);
    on.start();
    return { stop: () => { u.onend = null; u.onerror = null; u.onstart = null; try { window.speechSynthesis.cancel(); } catch { /* none */ } } };
  },
  release(url) { URL.revokeObjectURL(url); },
  hush() {
    if (element) { element.onended = null; element.onerror = null; try { element.pause(); } catch { /* idle */ } }
    if (hasWindow && "speechSynthesis" in window) { try { window.speechSynthesis.cancel(); } catch { /* none */ } }
  },
};

const store = {
  get: () => { try { return localStorage.getItem("floorwise:voice"); } catch { return null; } },
  set: (v: string) => { try { localStorage.setItem("floorwise:voice", v); } catch { /* private mode */ } },
};

const fire = (name: string, detail?: unknown) => { if (hasWindow) window.dispatchEvent(detail === undefined ? new Event(name) : new CustomEvent(name, { detail })); };

/** The app's only voice. */
export const speaker = createSpeaker<string>(browserBackend, {
  store,
  hooks: {
    start: (id, channel) => fire("floorwise:speech-start", { id, channel }),
    sentence: (id, channel, text, durationS) => fire("floorwise:speech-chunk", { id, channel, text, duration: durationS }),
    idle: () => fire("floorwise:speech-end"),
  },
});

/** Mobile browsers only play sound after a tap: play a silent clip on the shared element during the first gesture. */
if (hasWindow) {
  const unlock = () => {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("keydown", unlock, true);
    const el = audio();
    if (!el.paused || speaker.isSpeaking()) return;
    try {
      const rate = 8000, n = 800, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
      const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
      v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
      unlockUrl = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
      el.src = unlockUrl;
      el.play().then(() => { if (el.src === unlockUrl) el.pause(); }).catch(() => undefined);
    } catch { /* nothing to unlock */ }
  };
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
}

/** React view of the speaker: speaking / idle / muted, the channel and whether the microphone is open. */
export function useSpeaker(): SpeakerState {
  return useSyncExternalStore(speaker.subscribe, speaker.getState, speaker.getState);
}

// ---------- compatibility API ----------

/** Speak on a channel (default "chat"). onEnd runs once, however it ends. */
export function speak(text: string, onEnd?: () => void, o: SayOptions = {}): Promise<EndReason> {
  return speaker.say(text, { ...o, onEnd: r => { o.onEnd?.(r); onEnd?.(); } });
}
export function stopSpeaking(channel?: Channel) {
  if (channel) speaker.cancel(channel); else speaker.stopAll();
}
export const isSpeaking = () => speaker.isSpeaking();
export const normalizeLanguageTag = (_lang?: string) => "en-US";
export const setVoiceMuted = (muted: boolean) => speaker.setMuted(muted);

/** The chat stream's own audio chunks are not played: the finished reply is spoken once by the speaker instead (no half answers, no second
 *  voice model, nothing while muted). The object stays so older callers keep compiling. */
export const audioStreamQueue = {
  reset() { /* no-op */ },
  enqueue(_audio: string, _index = 0, _text?: string) { /* ignored on purpose */ },
  markDone() { /* no-op */ },
  onEnd(cb: () => void) { cb(); },
  stop() { /* no-op */ },
  active: false,
  hadChunks: false,
};
void cleanTextForSpeech;

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

  speaker.micStart();  // nothing talks over the user
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
    speaker.micEnd();
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

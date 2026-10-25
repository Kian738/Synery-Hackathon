// Voice in/out. ElevenLabs through the server proxy (/api/voice, the key never reaches the browser) when it is configured,
// the browser speech APIs otherwise and whenever the proxy fails (no key, budget used up, offline).

const Recognition: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

let remote: Promise<boolean> | null = null;
/** True when the server has an ElevenLabs key. Asked once; any failure means "use the browser voice". */
export const remoteVoice = () => (remote ??= typeof fetch === "undefined" ? Promise.resolve(false)
  : fetch("/api/voice/status").then(r => (r.ok ? r.json() : null)).then(j => Boolean(j?.tts)).catch(() => false));
const canRecord = () => typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== "undefined";
export const canListen = () => Boolean(Recognition) || canRecord();
export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

/** Server transcription: record until 1.4 s of silence (or 12 s), then send the audio to /api/voice/stt. */
function listenRemote(onFinal: (t: string) => void, onEnd: () => void, onError?: (message: string) => void) {
  let stopped = false, stop = () => { stopped = true; };
  void (async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (stopped) { stream.getTracks().forEach(t => t.stop()); return onEnd(); }
      const rec = new MediaRecorder(stream), chunks: Blob[] = [];
      const ctx = new AudioContext(), analyser = ctx.createAnalyser(), data = new Uint8Array(analyser.fftSize);
      ctx.createMediaStreamSource(stream).connect(analyser);
      let spoke = false, quietSince = performance.now();
      const timer = setInterval(() => {
        analyser.getByteTimeDomainData(data);
        const level = Math.max(...data.map(v => Math.abs(v - 128))) / 128, now = performance.now();
        if (level > 0.06) { spoke = true; quietSince = now; }
        if (stopped || (spoke && now - quietSince > 1400) || (!spoke && now - quietSince > 6000)) rec.state === "recording" && rec.stop();
      }, 120);
      const hardStop = setTimeout(() => rec.state === "recording" && rec.stop(), 12000);
      stop = () => { stopped = true; };
      rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        clearInterval(timer); clearTimeout(hardStop); stream.getTracks().forEach(t => t.stop()); void ctx.close();
        if (stopped || !spoke) return onEnd();
        try {
          const r = await fetch("/api/voice/stt", { method: "POST", headers: { "content-type": rec.mimeType || "audio/webm" }, body: new Blob(chunks, { type: rec.mimeType }) });
          const text = r.ok ? String((await r.json()).text ?? "").trim() : "";
          if (text) onFinal(text); else { onError?.("Nothing was understood. Please retry or type your request."); onEnd(); }
        } catch { onError?.("Voice input failed. Type your request instead."); onEnd(); }
      };
      rec.start();
    } catch { onError?.("Microphone access was denied. Type your request instead."); onEnd(); }
  })();
  return () => stop();
}

export function listen(onPartial: (t: string) => void, onFinal: (t: string) => void, onEnd: () => void, onError?: (message:string)=>void) {
  if (!Recognition && canRecord()) return listenRemote(onFinal, onEnd, onError);
  if (!Recognition) { onError?.("Voice input is unavailable in this browser. Type your request instead."); onEnd(); return () => {}; }
  const r = new Recognition();
  r.lang = document.documentElement.lang || "en-US";
  r.interimResults = true; r.continuous = false;
  let final = "", finished = false;
  const finish = (send:boolean) => {
    if(finished)return; finished=true;
    if(send && final.trim())onFinal(final.trim());else onEnd();
  };
  r.onresult = (event: any) => {
    if(finished)return;
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += t; else interim += t;
    }
    onPartial(final + interim);
  };
  r.onerror = (event:any) => { onError?.(event.error === "not-allowed" ? "Microphone access was denied. Type your request instead." : "Voice input stopped. Please retry or type your request."); finish(false); };
  r.onend = () => finish(true);
  try { r.start(); } catch { onError?.("Voice input could not start. Type your request instead."); finish(false); }
  return () => { finish(false); r.abort(); };
}

let player: HTMLAudioElement | null = null;
let ticket = 0;
const clean = (text: string) => text.replace(/\*\*/g, "").replace(/^Answer:.*$/gim, "").replace(/\s+/g, " ").trim();

let finishCurrent: (() => void) | null = null;

function speakBrowser(text: string, done: () => void) {
  if (!canSpeak()) return done();
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  u.onend = done; u.onerror = done;
  window.speechSynthesis.speak(u);
}

/** Speak immediately, cutting off anything still talking (barge-in friendly). ElevenLabs first, browser voice on any failure.
 *  `onSpeaking(true)` fires when the voice starts and `onSpeaking(false)` when it ends or is cut off, so the screen can highlight
 *  what is being talked about for exactly as long as it is talked about. */
export function speak(text: string, onSpeaking?: (speaking: boolean) => void) {
  const line = clean(text).slice(0, 600);
  stopSpeaking();
  if (!line) return;
  const mine = ++ticket;
  let ended = false;
  const end = () => { if (ended) return; ended = true; if (finishCurrent === end) finishCurrent = null; onSpeaking?.(false); };
  finishCurrent = end;
  const begin = () => { if (mine === ticket && !ended) onSpeaking?.(true); };
  void remoteVoice().then(async ok => {
    if (mine !== ticket) return end();
    if (!ok) { begin(); return speakBrowser(line, end); }
    try {
      const r = await fetch("/api/voice/tts", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: line }) });
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      if (mine !== ticket) { URL.revokeObjectURL(url); return end(); }
      player = new Audio(url);
      player.onended = () => { URL.revokeObjectURL(url); end(); };
      player.onerror = end;
      await player.play();
      begin();
    } catch { if (mine === ticket) { begin(); speakBrowser(line, end); } else end(); }
  });
}
export function stopSpeaking() {
  ticket++;
  const finish = finishCurrent; finishCurrent = null; finish?.();
  if (player) { player.pause(); player = null; }
  if (canSpeak()) window.speechSynthesis.cancel();
}

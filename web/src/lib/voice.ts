// Voice in/out. Browser speech APIs for now; ElevenLabs/Groq Orpheus can replace speak() via the server.

const Recognition: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export const canListen = () => Boolean(Recognition);
export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function listen(onPartial: (t: string) => void, onFinal: (t: string) => void, onEnd: () => void, onError?: (message:string)=>void) {
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

/** Speak immediately, cutting off anything still talking (barge-in friendly). */
export function speak(text: string) {
  if (!canSpeak()) return;
  window.speechSynthesis.cancel();
  const clean = text.replace(/\*\*/g, "").replace(/^Answer:.*$/gim, "").replace(/\s+/g, " ").trim();
  if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 1.05;
  window.speechSynthesis.speak(u);
}

export const stopSpeaking = () => canSpeak() && window.speechSynthesis.cancel();

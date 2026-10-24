// Voice in/out. Browser speech APIs for now; ElevenLabs/Groq Orpheus can replace speak() via the server.

const Recognition: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export const canListen = () => Boolean(Recognition);
export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function listen(onPartial: (t: string) => void, onFinal: (t: string) => void, onEnd: () => void) {
  const r = new Recognition();
  r.lang = navigator.language || "en-US";
  r.interimResults = true;
  r.continuous = false;
  let final = "";
  r.onresult = (event: any) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += t;
      else interim += t;
    }
    onPartial(final + interim);
  };
  r.onerror = onEnd;
  r.onend = () => (final.trim() ? onFinal(final) : onEnd());
  r.start();
  return () => r.abort();
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

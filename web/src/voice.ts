// Voice in/out with the browser's speech APIs. ElevenLabs can replace speak() later via a server endpoint.

const Recognition: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export const speechSupported = () => Boolean(Recognition);

export function listen(onPartial: (text: string) => void, onFinal: (text: string) => void, onEnd: () => void) {
  const recognition = new Recognition();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = true;
  recognition.continuous = false;
  let finalText = "";
  recognition.onresult = (event: any) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += transcript;
      else interim += transcript;
    }
    onPartial(finalText + interim);
  };
  recognition.onerror = onEnd;
  recognition.onend = () => (finalText.trim() ? onFinal(finalText) : onEnd());
  recognition.start();
}

export function speak(text: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  // Read the directions, not ids or markdown.
  const clean = text.replace(/\*\*/g, "").replace(/\[[^\]]*\]/g, "").replace(/^Answer:.*$/gim, "");
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 1.05;
  window.speechSynthesis.speak(utterance);
}

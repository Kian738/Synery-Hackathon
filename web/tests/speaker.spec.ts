import { test, expect } from "@playwright/test";
import { cleanTextForSpeech, createSpeaker, splitSentences, type Backend, type SoundCallbacks } from "../src/lib/speaker";

/** A fake audio world: counts sounds that are playing at once and lets the test end them. */
function world(serverOk = true) {
  const playing = new Set<{ text: string; on: SoundCallbacks }>();
  let maxAtOnce = 0, fetches = 0, browser = 0;
  const log: string[] = [];
  const add = (text: string, on: SoundCallbacks) => {
    const s = { text, on }; playing.add(s); maxAtOnce = Math.max(maxAtOnce, playing.size); log.push(text);
    return { stop: () => playing.delete(s) };
  };
  const backend: Backend<string> = {
    async fetch(text) { fetches++; return serverOk ? { clip: text } : { off: "permanent" }; },
    playClip: (clip, on) => add(clip, on),
    speakBrowser: (text, on) => { browser++; return add(text, on); },
    hush: () => playing.clear(),
  };
  const endCurrent = () => { const s = [...playing][0]; if (s) { playing.delete(s); s.on.end(); } };
  return { backend, playing, log, endCurrent, stats: () => ({ maxAtOnce, fetches, browser }) };
}
const tick = () => new Promise(r => setTimeout(r, 0));

test("never more than one voice, and a higher channel interrupts a lower one", async () => {
  const w = world(); const sp = createSpeaker(w.backend);
  sp.say("Fire in the hall.", { channel: "narration", id: "n1" });
  sp.say("In 10 m, turn left.", { channel: "guide", id: "g1" });
  sp.say("The toilets are on floor 2.", { channel: "chat", id: "c1" });
  await tick(); await tick();
  expect(w.playing.size).toBe(1);
  expect([...w.playing][0].text).toContain("toilets");
  expect(w.stats().maxAtOnce).toBe(1);
});

test("a new Guide me step replaces the old one but never cuts the chat answer", async () => {
  const w = world(); const sp = createSpeaker(w.backend);
  const chat = sp.say("Here is your answer.", { channel: "chat", id: "c" });
  sp.say("Step one.", { channel: "guide", id: "g1" });
  sp.say("Step two.", { channel: "guide", id: "g2" });
  await tick(); await tick();
  expect([...w.playing][0].text).toContain("answer");
  w.endCurrent(); expect(await chat).toBe("done");
  await tick(); await tick();
  expect([...w.playing][0].text).toBe("Step two.");
  expect(w.log).not.toContain("Step one.");
});

test("the same id is spoken once; cancel and mute clean up", async () => {
  const w = world(); const sp = createSpeaker(w.backend);
  sp.say("Turn right.", { channel: "guide", id: "x" }); sp.say("Turn right.", { channel: "guide", id: "x" });
  await tick(); await tick();
  expect(w.log).toEqual(["Turn right."]);
  sp.cancel("guide");
  expect(w.playing.size).toBe(0); expect(sp.getState().status).toBe("idle");
  sp.setMuted(true);
  expect(await sp.say("Hello there.", { channel: "chat" })).toBe("muted");
  expect(sp.getState().status).toBe("muted");
});

test("the browser voice is used only when the server voice fails, never both", async () => {
  const w = world(false); const sp = createSpeaker(w.backend);
  sp.say("The lift is closed. Use the stairs.", { channel: "chat" });
  await tick(); await tick();
  expect(w.stats().browser).toBe(1); expect(w.stats().maxAtOnce).toBe(1);
  expect(splitSentences("Room 0.08 is here. Go now.")).toEqual(["Room 0.08 is here. Go now."]);
});

test("the microphone silences everything", async () => {
  const w = world(); const sp = createSpeaker(w.backend);
  sp.say("Long answer.", { channel: "chat" }); await tick(); await tick();
  sp.micStart(); expect(w.playing.size).toBe(0);
  sp.say("Step.", { channel: "guide" }); await tick(); expect(w.playing.size).toBe(0);
  sp.micEnd(); await tick(); await tick(); expect(w.playing.size).toBe(1);
});

test("speech text is normalised for the ear: floors, areas, percent, WC, singular minute", () => {
  expect(cleanTextForSpeech("Go to F1, then F-1.")).toBe("Go to floor 1, then floor minus 1.");
  expect(cleanTextForSpeech("The room has 24 m2 and 30 m².")).toBe("The room has 24 square metres and 30 square metres.");
  expect(cleanTextForSpeech("Occupancy is 80%.")).toBe("Occupancy is 80 percent.");
  expect(cleanTextForSpeech("The WC is near two WCs.")).toBe("The toilet is near two toilets.");
  expect(cleanTextForSpeech("About 1 min, or 3 min.")).toBe("About 1 minute, or 3 minutes.");
  expect(cleanTextForSpeech("In 12 m, turn left.")).toBe("In 12 metres, turn left.");
});

test("the next sentence is fetched before the current one ends", async () => {
  const w = world(); const sp = createSpeaker(w.backend);
  sp.say("This is the first long sentence of the answer. This is the second long sentence of the answer.", { channel: "chat" });
  await tick(); await tick(); await tick();
  expect(w.playing.size).toBe(1);
  expect(w.stats().fetches).toBe(2);
});

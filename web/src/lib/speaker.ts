// One speaker for the whole app: exactly one voice at any time (docs/VOICE_DESIGN.md).
// Pure logic: the browser side (audio element, speechSynthesis, fetch) is a Backend injected by voice.ts, so this file is unit-tested without a browser.

export type Channel = "mic" | "chat" | "guide" | "narration" | "ambient";
/** Higher wins. The microphone is not a voice: holding it silences everything until it is released. */
export const PRIORITY: Record<Channel, number> = { mic: 4, chat: 3, guide: 2, narration: 1, ambient: 0 };
/** interrupt: replaces what its own channel is saying (and anything lower). queue: waits its turn. skip-if-busy: only speaks into silence. */
export type Policy = "interrupt" | "queue" | "skip-if-busy";
const DEFAULT_POLICY: Record<Channel, Policy> = { mic: "interrupt", chat: "interrupt", guide: "interrupt", narration: "queue", ambient: "skip-if-busy" };
export type EndReason = "done" | "cancelled" | "muted" | "skipped" | "blocked" | "failed";
export type Engine = "server" | "browser";

export interface SayOptions {
  /** Same id while it is queued, playing, or started under 1.5 s ago: the call is a no-op (StrictMode double effects, re-renders). */
  id?: string;
  channel?: Channel;
  policy?: Policy;
  onStart?: () => void;
  onEnd?: (reason: EndReason) => void;
}

export interface SpeakerState {
  status: "speaking" | "idle" | "muted";
  channel: Channel | null;
  id: string | null;
  text: string;
  engine: Engine | null;
  listening: boolean;
}

/** The answer of the server voice for one sentence. off: "permanent" (no key, budget used up) keeps the browser voice for the session. */
export type Fetched<C> = { clip: C } | { off: "permanent" | "transient" | "aborted" };
export interface SoundCallbacks { start(durationS?: number): void; end(): void; fail(blocked: boolean): void }
export interface Sound { stop(): void }
export interface Backend<C = unknown> {
  fetch(text: string, context: { previous?: string; next?: string }, signal: AbortSignal): Promise<Fetched<C>>;
  playClip(clip: C, on: SoundCallbacks): Sound;
  speakBrowser(text: string, on: SoundCallbacks): Sound | null;
  release?(clip: C): void;
  /** Silence both engines, whatever they are doing. Called before every new sound and on every cancel. */
  hush(): void;
}
export interface SpeakerHooks {
  start?(id: string, channel: Channel): void;
  sentence?(id: string, channel: Channel, text: string, durationS?: number): void;
  idle?(): void;
}
export interface Store { get(): string | null; set(v: string): void }

interface Job<C> {
  id: string; channel: Channel; text: string; sentences: string[]; opts: SayOptions;
  done: boolean; started: boolean; abort: AbortController; sound: Sound | null; browser: boolean;
  fetches: Map<number, Promise<Fetched<C>>>; clips: C[];
  promise: Promise<EndReason>; resolve: (r: EndReason) => void;
}

// ---------- text ----------

/** Words for the ear: no markdown, units spoken out ("12 m" -> "12 metres"), no symbols the voice would spell. */
export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/^#+\s+/gm, "")
    .replace(/^Answer:\s*/gim, "")
    .replace(/^\s*[-*•]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/(\d)\s?m²/g, "$1 square metres")
    .replace(/\b1\s?m\b(?![²\w])/g, "1 metre")
    .replace(/(\d)\s?m\b(?![²\w])/g, "$1 metres")
    .replace(/(\d)\s?km\b/g, "$1 kilometres")
    .replace(/\b1\s?s\b/g, "1 second")
    .replace(/(\d)\s?s\b/g, "$1 seconds")
    .replace(/(\d)\s?min\b/g, "$1 minutes")
    .replace(/\s*[→⟶➜]\s*/g, ", then ")
    .replace(/\s*[|·•]\s*/g, ", ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Sentences for faster first audio: split after . ! ? (not inside 0.08 or "e.g."), merge short ones, cut very long ones at a comma. */
export function splitSentences(text: string, max = 220, min = 24): string[] {
  const raw = text.split(/(?<=[.!?])\s+(?=["'(]?[A-Z0-9])/).map(s => s.trim()).filter(Boolean);
  const cut: string[] = [];
  for (const s of raw) {
    let rest = s;
    while (rest.length > max) {
      const at = Math.max(rest.lastIndexOf(", ", max), rest.lastIndexOf("; ", max), rest.lastIndexOf(" ", max));
      const i = at > max / 3 ? at + 1 : max;
      cut.push(rest.slice(0, i).trim()); rest = rest.slice(i).trim();
    }
    if (rest) cut.push(rest);
  }
  const out: string[] = [];
  for (const s of cut) {
    const last = out[out.length - 1];
    if (last !== undefined && (last.length < min || s.length < min) && last.length + s.length + 1 <= max) out[out.length - 1] = `${last} ${s}`;
    else out.push(s);
  }
  return out;
}

// ---------- the speaker ----------

let autoId = 0;
const DEDUPE_MS = 1500;

export function createSpeaker<C>(backend: Backend<C>, opts: { hooks?: SpeakerHooks; store?: Store; now?: () => number; transientOffMs?: number } = {}) {
  const now = opts.now ?? (() => Date.now());
  const hooks = opts.hooks ?? {};
  let muted = opts.store?.get() === "off";
  let micHeld = false;
  let current: Job<C> | null = null;
  const queues: Record<Channel, Job<C>[]> = { mic: [], chat: [], guide: [], narration: [], ambient: [] };
  const recent = new Map<string, number>();
  let serverOffUntil = 0;
  let engine: Engine | null = null;
  const listeners = new Set<() => void>();
  let snapshot: SpeakerState = makeState();

  function makeState(): SpeakerState {
    return { status: muted ? "muted" : current ? "speaking" : "idle", channel: current?.channel ?? null, id: current?.id ?? null, text: current?.text ?? "", engine: current ? engine : null, listening: micHeld };
  }
  function emit() {
    const next = makeState();
    const s = snapshot;
    if (s.status === next.status && s.channel === next.channel && s.id === next.id && s.engine === next.engine && s.listening === next.listening) return;
    snapshot = next;
    listeners.forEach(l => { try { l(); } catch { /* a listener must not break the speaker */ } });
  }
  const serverOn = () => now() >= serverOffUntil;

  function settle(job: Job<C>, reason: EndReason) {
    if (job.done) return;
    job.done = true;
    if (reason === "cancelled" || reason === "muted") recent.delete(job.id);  // StrictMode mount-cancel-mount may say it again
    job.abort.abort();
    if (job.sound) { try { job.sound.stop(); } catch { /* already silent */ } job.sound = null; }
    for (const c of job.clips) backend.release?.(c);
    job.clips = [];
    job.fetches.forEach(p => p.then(f => { if ("clip" in f) backend.release?.(f.clip); }).catch(() => undefined));
    job.fetches.clear();
    try { job.opts.onEnd?.(reason); } catch { /* caller bug must not leave the speaker stuck */ }
    job.resolve(reason);
  }

  function stopCurrent(reason: EndReason) {
    const job = current;
    if (!job) return;
    current = null;
    backend.hush();
    settle(job, reason);
  }

  function next() {
    if (current || micHeld || muted) { emit(); return; }
    for (const ch of (Object.keys(PRIORITY) as Channel[]).sort((a, b) => PRIORITY[b] - PRIORITY[a])) {
      const job = queues[ch].shift();
      if (job) { start(job); return; }
    }
    emit();
    hooks.idle?.();
  }

  function start(job: Job<C>) {
    current = job;
    job.started = true;
    recent.set(job.id, now());
    engine = serverOn() ? "server" : "browser";
    backend.hush();
    emit();
    try { job.opts.onStart?.(); } catch { /* ignore */ }
    hooks.start?.(job.id, job.channel);
    void play(job, 0);
  }

  function getClip(job: Job<C>, i: number): Promise<Fetched<C>> {
    let p = job.fetches.get(i);
    if (!p) {
      p = backend.fetch(job.sentences[i], { previous: job.sentences[i - 1], next: job.sentences[i + 1] }, job.abort.signal).catch(() => ({ off: "transient" as const }));
      job.fetches.set(i, p);
    }
    return p;
  }

  function finishSentence(job: Job<C>, i: number) {
    if (job !== current || job.done) return;
    job.sound = null;
    if (i + 1 >= job.sentences.length) { current = null; settle(job, "done"); next(); return; }
    void play(job, i + 1);
  }

  async function play(job: Job<C>, i: number) {
    if (job !== current || job.done) return;
    const text = job.sentences[i];
    if (!job.browser && serverOn()) {
      const got = await getClip(job, i);
      job.fetches.delete(i);
      if (job !== current || job.done) { if ("clip" in got) backend.release?.(got.clip); return; }
      if ("clip" in got) {
        job.clips.push(got.clip);
        // One request in flight at a time (ElevenLabs counts concurrent requests): prefetch the next sentence only now.
        if (i + 1 < job.sentences.length && serverOn()) void getClip(job, i + 1);
        let once = false;
        const guard = (f: () => void) => () => { if (once || job !== current || job.done) return; once = true; f(); };
        backend.hush();
        engine = "server"; emit();
        job.sound = backend.playClip(got.clip, {
          start: d => { if (job === current && !job.done) hooks.sentence?.(job.id, job.channel, text, d); },
          end: guard(() => finishSentence(job, i)),
          fail: blocked => guard(() => {
            if (blocked) { current = null; settle(job, "blocked"); next(); return; }
            job.browser = true; void play(job, i);
          })(),
        });
        return;
      }
      if (got.off === "aborted") return;
      serverOffUntil = got.off === "permanent" ? Infinity : now() + (opts.transientOffMs ?? 30000);
      job.browser = true;
    }
    // Browser voice: only when the server voice failed, and then for the rest of this utterance so one answer never changes voice.
    job.browser = true;
    engine = "browser"; emit();
    let once = false;
    const guard = (f: () => void) => () => { if (once || job !== current || job.done) return; once = true; f(); };
    backend.hush();
    const sound = backend.speakBrowser(text, {
      start: () => { if (job === current && !job.done) hooks.sentence?.(job.id, job.channel, text); },
      end: guard(() => finishSentence(job, i)),
      fail: blocked => guard(() => { current = null; settle(job, blocked ? "blocked" : "failed"); next(); })(),
    });
    if (!sound) { if (job === current) { current = null; settle(job, "failed"); next(); } return; }
    if (job === current && !job.done) job.sound = sound; else sound.stop();
  }

  function find(id: string): Job<C> | undefined {
    if (current?.id === id && !current.done) return current;
    for (const ch of Object.keys(queues) as Channel[]) { const j = queues[ch].find(x => x.id === id); if (j) return j; }
    return undefined;
  }

  function clearQueue(ch: Channel, reason: EndReason) {
    const q = queues[ch].splice(0);
    q.forEach(j => settle(j, reason));
  }

  /** Speak text on a channel. Resolves when it has ended, for any reason. */
  function say(text: string, o: SayOptions = {}): Promise<EndReason> {
    const channel = o.channel ?? "chat";
    const policy = o.policy ?? DEFAULT_POLICY[channel];
    const id = o.id ?? `auto-${++autoId}`;
    if (muted) { o.onEnd?.("muted"); return Promise.resolve("muted"); }
    const same = find(id);
    if (same) return same.promise;
    const at = recent.get(id);
    if (at !== undefined && now() - at < DEDUPE_MS) { o.onEnd?.("skipped"); return Promise.resolve("skipped"); }
    const clean = cleanTextForSpeech(text);
    const sentences = splitSentences(clean);
    if (!sentences.length) { o.onEnd?.("skipped"); return Promise.resolve("skipped"); }
    let resolve!: (r: EndReason) => void;
    const promise = new Promise<EndReason>(r => { resolve = r; });
    const job: Job<C> = { id, channel, text: clean, sentences, opts: o, done: false, started: false, abort: new AbortController(), sound: null, browser: false, fetches: new Map(), clips: [], promise, resolve };
    const cur = current;
    if (policy === "skip-if-busy" && (cur || micHeld)) { settle(job, "skipped"); return promise; }
    if (policy === "interrupt") clearQueue(channel, "cancelled");  // a newer line of the same kind makes older waiting ones stale
    if (micHeld) { queues[channel].push(job); emit(); return promise; }
    if (!cur) { start(job); return promise; }
    const wins = PRIORITY[channel] > PRIORITY[cur.channel] || (channel === cur.channel && policy === "interrupt");
    if (wins) { stopCurrent("cancelled"); start(job); return promise; }
    queues[channel].push(job);
    return promise;
  }

  /** Stop and forget everything on one channel (leaving a mode). */
  function cancel(channel: Channel) {
    clearQueue(channel, "cancelled");
    if (current?.channel === channel) { stopCurrent("cancelled"); next(); }
  }

  function stopAll(reason: EndReason = "cancelled") {
    (Object.keys(queues) as Channel[]).forEach(ch => clearQueue(ch, reason));
    if (current) stopCurrent(reason); else backend.hush();
    emit();
    hooks.idle?.();
  }

  return {
    say,
    cancel,
    stopAll,
    /** Microphone open: nothing speaks over the user. Queued lines are dropped; what follows the question is new anyway. */
    micStart() { micHeld = true; stopAll("cancelled"); emit(); },
    micEnd() { if (!micHeld) return; micHeld = false; next(); },
    setMuted(m: boolean) {
      if (m === muted) return;
      muted = m;
      opts.store?.set(m ? "off" : "on");
      if (m) stopAll("muted");
      emit();
    },
    isMuted: () => muted,
    isSpeaking: (channel?: Channel) => !!current && (!channel || current.channel === channel),
    getState: () => snapshot,
    subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; },
    /** For tests: forget that the server voice failed. */
    resetServer() { serverOffUntil = 0; },
  };
}

export type Speaker = ReturnType<typeof createSpeaker>;

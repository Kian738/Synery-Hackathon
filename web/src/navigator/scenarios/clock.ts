import { useSyncExternalStore } from "react";
import type { ScenarioMove } from "../../lib/types";

/** What the 3D ScenarioLayer draws. "flow": exact moves from the evacuation engine. "rooms": headcounts per room per step from the stress engine
 *  (dots are synthesised from them, so they are approximate). */
export type ScenarioScene =
  | { kind: "flow"; schedule: ScenarioMove[]; hazard?: string; bottleneck: string[]; byExit: Record<string, number>; stranded: Record<string, number> }
  | { kind: "rooms"; step_s: number; rooms: Record<string, number[]>; queues: { id: string; floor_id: string; x: number; y: number; queue: number }[] };

type State = { t: number; T: number; playing: boolean; replaySeconds: number; scene: ScenarioScene | null };

/** One clock for every scenario engine: the scrubber, the results, the map colours and the 3D people all read this time. */
let state: State = { t: 0, T: 0, playing: false, replaySeconds: 15, scene: null };
const subs = new Set<() => void>();
const set = (patch: Partial<State>) => { state = { ...state, ...patch }; subs.forEach(f => f()); };
let raf = 0, last = 0;
const loop = (now: number) => {
  raf = 0;
  if (!state.playing || state.T <= 0) return;
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  const t = Math.min(state.T, state.t + dt * state.T / state.replaySeconds);
  set({ t, playing: t < state.T });
  if (state.playing) raf = requestAnimationFrame(loop);
};

export const clock = {
  get: () => state,
  subscribe: (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; },
  /** A new result: horizon T seconds of simulated time, replayed in `replaySeconds` of wall time; starts at 0. */
  load: (T: number, replaySeconds = 15, autoplay = true) => { set({ T, t: 0, replaySeconds, playing: false }); if (autoplay) clock.play(); },
  seek: (t: number) => set({ t: Math.max(0, Math.min(state.T, t)), playing: false }),
  play: () => {
    if (state.T <= 0) return;
    set({ playing: true, t: state.t >= state.T ? 0 : state.t });
    if (!raf) { last = performance.now(); raf = requestAnimationFrame(loop); }
  },
  pause: () => set({ playing: false }),
  setScene: (scene: ScenarioScene | null) => set({ scene }),
  reset: () => { if (raf) cancelAnimationFrame(raf); raf = 0; set({ t: 0, T: 0, playing: false, scene: null }); },
};

export const useClock = () => useSyncExternalStore(clock.subscribe, clock.get);
export const mmss = (s: number) => { const r = Math.round(s); return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`; };

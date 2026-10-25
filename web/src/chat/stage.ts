import { useSyncExternalStore } from "react";

/** Shared highlight state between the chat and the 3D view: which result rows are numbered and which one is hovered/focused. */
type State = { numbered: { id: string; n: number }[]; pulse: string | null };
let state: State = { numbered: [], pulse: null };
const subs = new Set<() => void>();
const set = (next: Partial<State>) => { state = { ...state, ...next }; subs.forEach(f => f()); };
export const stage = {
  setNumbered: (numbered: State["numbered"]) => set({ numbered }),
  pulse: (id: string | null) => { if (state.pulse !== id) set({ pulse: id }); },
  clear: () => set({ numbered: [], pulse: null }),
};
export function useStage(): State {
  return useSyncExternalStore(f => { subs.add(f); return () => subs.delete(f); }, () => state, () => state);
}

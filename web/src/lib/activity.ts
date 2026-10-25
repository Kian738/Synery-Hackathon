import { useEffect, useState, useSyncExternalStore } from "react";

/** What the app is waiting for. Every /api request (except long streams and polling) is tracked so the person always sees that something is
 *  happening: a thin bar after 200 ms, a named status with a stopwatch after 1.2 s, and an honest "large building" note after 8 s. */
interface Pending { since: number; label: string }
const pending = new Map<number, Pending>();
const listeners = new Set<() => void>();
let counter = 0, installed = false, snapshot: { count: number; since: number; label: string } = { count: 0, since: 0, label: "" };

const emit = () => {
  const first = [...pending.values()].sort((a, b) => a.since - b.since)[0];
  snapshot = { count: pending.size, since: first?.since ?? 0, label: first?.label ?? "" };
  listeners.forEach(l => l());
};

export function labelFor(url: string, method = "GET"): string {
  if (/\/route\b|route-preview/.test(url)) return "Planning your route";
  if (/\/scene\b/.test(url)) return "Building the 3D model";
  if (/weak-points/.test(url)) return "Stress-testing the building";
  if (/\/door|\/close|\/undo|\/items?\b/.test(url) && method !== "GET") return "Applying the change";
  if (/\/api\/sessions$/.test(url)) return "Opening the building";
  if (/\/api\/buildings\/[^/]+$/.test(url)) return "Loading the building";
  if (/thumb\.svg/.test(url)) return "";
  if (/\/scenario/.test(url)) return "Running the scenario";
  return "Working";
}

/** Wrap window.fetch once. Chat (server-sent stream), voice and thumbnails are not tracked: they have their own indicators or are decoration. */
export function installActivityTracking() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? (input instanceof Request ? input.method : "GET");
    if (!url.includes("/api/") || /\/chat\b|\/api\/voice|thumb\.svg|\/stream\b|\/api\/companion/.test(url)) return original(input, init);
    const label = labelFor(url, method);
    if (!label) return original(input, init);
    const key = ++counter;
    pending.set(key, { since: performance.now(), label });
    emit();
    return original(input, init).finally(() => { pending.delete(key); emit(); });
  };
}

export function useActivity() {
  const state = useSyncExternalStore(cb => { listeners.add(cb); return () => { listeners.delete(cb); }; }, () => snapshot, () => snapshot);
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!state.count) return;
    const t = setInterval(() => setNow(performance.now()), 400);
    return () => clearInterval(t);
  }, [state.count]);
  const elapsed = state.count ? Math.max(0, (now - state.since) / 1000) : 0;
  return { busy: state.count > 0, label: state.label, elapsed, count: state.count };
}

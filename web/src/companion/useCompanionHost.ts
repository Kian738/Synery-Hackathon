import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CompanionClient, REASON_TEXT, type ClientOptions, type ClientState } from "./client";
import type { LookMode, PairRequest, RouteState, StepAction } from "./protocol";

export interface CompanionHostOptions extends Omit<ClientOptions, "role" | "resume"> {
  /** The phone asked to turn the camera. Degrees, right/up positive. Apply to camera heading only. */
  onHeading?: (dyaw: number, dpitch: number, mode: LookMode) => void;
  /** The phone asked for the previous/next/same instruction. A request, not progress: the laptop decides. */
  onStep?: (action: StepAction) => void;
  /** The phone asked to reset the camera to the route direction. */
  onRecenter?: () => void;
}

export interface CompanionHost {
  state: ClientState;
  /** Current pairing code while one is valid, else null. */
  code: string | null;
  codeExpiresAt: number | null;
  /** Phones waiting for the user's confirmation. Each shows `verify` on the phone too. */
  pending: PairRequest[];
  phoneOnline: boolean;
  /** Plain-words reason the session ended, if it did. */
  ended: string | null;
  error: string | null;
  lanAddresses: string[];
  /** Create a session and a pairing code. Safe to call again after the session ended. */
  start(): Promise<void>;
  approve(requestId: string): void;
  deny(requestId: string): void;
  newCode(): void;
  /** End the pairing for everyone. Desktop navigation is unaffected. */
  revoke(): void;
  /** Publish the current instruction. Cheap to call on every step change; ignored while no phone is connected. */
  publish(state: RouteState): void;
}

/**
 * Laptop-side controller for the companion. Integration: call `publish(routeStateFromGuide(steps, stepIndex))` whenever
 * the displayed step changes, and map `onHeading`/`onStep`/`onRecenter` onto the existing camera and step controls.
 * If the socket drops, nothing else in the Navigator changes.
 */
export function useCompanionHost(options: CompanionHostOptions = {}): CompanionHost {
  const [state, setState] = useState<ClientState>("idle");
  const [code, setCode] = useState<string | null>(null);
  const [codeExpiresAt, setCodeExpiresAt] = useState<number | null>(null);
  const [pending, setPending] = useState<PairRequest[]>([]);
  const [phoneOnline, setPhoneOnline] = useState(false);
  const [ended, setEnded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lanAddresses, setLan] = useState<string[]>([]);
  const client = useRef<CompanionClient | null>(null);
  const handlers = useRef(options);
  handlers.current = options;
  const last = useRef<RouteState | null>(null);

  const start = useCallback(async () => {
    client.current?.disconnect();
    setEnded(null); setError(null); setPending([]); setPhoneOnline(false);
    const { onHeading: _a, onStep: _b, onRecenter: _c, ...transport } = handlers.current;
    const c = new CompanionClient({ ...transport, role: "laptop" });
    client.current = c;
    c.on("state", setState);
    c.on("pair_request", r => setPending(list => [...list.filter(x => x.request_id !== r.request_id), r]));
    c.on("code", (value, seconds) => { setCode(value); setCodeExpiresAt(Date.now() + seconds * 1000); });
    c.on("peer", online => setPhoneOnline(online));
    c.on("heading", (y, p, m) => handlers.current.onHeading?.(y, p, m));
    c.on("step", a => handlers.current.onStep?.(a));
    c.on("recenter", () => handlers.current.onRecenter?.());
    c.on("notice", (name, message) => { if (name !== "stale_seq" && name !== "rate_limited") setError(message); });
    c.on("ended", reason => { setEnded(REASON_TEXT[reason] ?? "The pairing ended."); setCode(null); setPending([]); setPhoneOnline(false); });
    c.on("state", s => { if (s === "paired" && last.current) c.publish(last.current); });
    try {
      const info = await c.info().catch(() => null);
      if (info && info.websocket === false) throw new Error("This server cannot open WebSocket connections yet. Install the 'websockets' package for the backend (uv add websockets), then restart it.");
      setLan(info?.lan_addresses ?? []);
      const made = await c.startSession();
      setCode(made.code); setCodeExpiresAt(Date.now() + made.expiresIn * 1000);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not start pairing.");
    }
  }, []);

  useEffect(() => () => client.current?.disconnect(), []);

  return useMemo<CompanionHost>(() => ({
    state, code, codeExpiresAt, pending, phoneOnline, ended, error, lanAddresses, start,
    approve: id => { client.current?.approve(id); setPending(list => list.filter(r => r.request_id !== id)); },
    deny: id => { client.current?.deny(id); setPending(list => list.filter(r => r.request_id !== id)); },
    newCode: () => client.current?.newCode(),
    revoke: () => client.current?.revoke(),
    publish: s => { last.current = s; if (client.current?.state === "paired") client.current.publish(s); },
  }), [state, code, codeExpiresAt, pending, phoneOnline, ended, error, lanAddresses, start]);
}

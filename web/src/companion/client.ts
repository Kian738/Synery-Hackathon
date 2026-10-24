// CompanionClient: REST pairing, one WebSocket, numbering, coalesced heading, reconnect with resume.
// No React, no globals beyond optional defaults: WebSocket, fetch and timers are injectable so every path is testable.
import {
  FINAL_CLOSE_CODES, HEADING_FLUSH_MS, PROTOCOL_VERSION, parseFrame, splitDelta,
  type LookMode, type PairRequest, type Relayed, type Role, type RouteState, type ServerMessage, type StepAction,
} from "./protocol";

export type ClientState = "idle" | "pairing" | "connecting" | "waiting" | "paired" | "reconnecting" | "ended";
export interface Scheduler { set(fn: () => void, ms: number): unknown; clear(id: unknown): void }
export interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number; reason?: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}
export type SocketFactory = (url: string) => SocketLike;

export interface ClientOptions {
  role: Role;
  /** Origin of the server, e.g. "http://192.168.1.20:8000". Defaults to the page's own origin. */
  baseUrl?: string;
  prefix?: string;
  socketFactory?: SocketFactory;
  fetchImpl?: typeof fetch;
  scheduler?: Scheduler;
  /** Reconnect delays in ms: first, then doubling up to max. Gives up after maxAttempts. */
  reconnect?: { minMs: number; maxMs: number; maxAttempts: number };
  /** Phone only: credentials from a previous page load of the same tab (see PhoneCompanion). */
  resume?: Credentials;
}
export interface Credentials { session: string; token: string; verify?: number }

type Handlers = {
  state: (state: ClientState) => void;
  route_state: (state: RouteState, replay: boolean) => void;
  heading: (dyaw: number, dpitch: number, mode: LookMode) => void;
  step: (action: StepAction) => void;
  recenter: () => void;
  pair_request: (request: PairRequest) => void;
  code: (code: string, expiresIn: number) => void;
  peer: (online: boolean) => void;
  verify: (verify: number) => void;
  notice: (code: string, message: string) => void;
  ended: (reason: string) => void;
};

const OPEN = 1;
const defaultScheduler: Scheduler = { set: (fn, ms) => setTimeout(fn, ms), clear: id => clearTimeout(id as ReturnType<typeof setTimeout>) };

export class CompanionClient {
  state: ClientState = "idle";
  credentials: Credentials | null = null;
  peerOnline = false;
  endedReason: string | null = null;
  code: string | null = null;
  private readonly o: Required<Pick<ClientOptions, "role" | "prefix" | "reconnect">> & ClientOptions;
  private socket: SocketLike | null = null;
  private seq = 0;
  private attempts = 0;
  private retry: unknown = null;
  private flush: unknown = null;
  private pending = { dyaw: 0, dpitch: 0, mode: "touch" as LookMode };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private listeners: Record<string, ((...args: any[]) => void)[]> = {};
  private lastRouteSeq = -1;

  constructor(options: ClientOptions) {
    // Explicit `undefined` options (an unset React prop) must not erase the defaults.
    this.o = { ...options, prefix: options.prefix ?? "/companion", reconnect: options.reconnect ?? { minMs: 800, maxMs: 12_000, maxAttempts: 10 } };
    if (options.resume) this.credentials = options.resume;
  }

  on<K extends keyof Handlers>(event: K, handler: Handlers[K]): () => void {
    (this.listeners[event] ??= []).push(handler);
    return () => { this.listeners[event] = (this.listeners[event] ?? []).filter(h => h !== handler); };
  }
  private emit<K extends keyof Handlers>(event: K, ...args: Parameters<Handlers[K]>) {
    for (const h of [...(this.listeners[event] ?? [])]) h(...args);
  }
  private set(state: ClientState) { if (this.state !== state) { this.state = state; this.emit("state", state); } }
  private get sched() { return this.o.scheduler ?? defaultScheduler; }
  private base() { return (this.o.baseUrl ?? (typeof location !== "undefined" ? location.origin : "")).replace(/\/$/, ""); }

  private async rest(path: string, init: RequestInit & { token?: string } = {}): Promise<Record<string, unknown>> {
    const f = this.o.fetchImpl ?? fetch;
    const headers: Record<string, string> = { "content-type": "application/json", ...(init.token ? { authorization: `Bearer ${init.token}` } : {}) };
    const response = await f(`${this.base()}${this.o.prefix}${path}`, { method: init.method, body: init.body, headers });
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
    return body;
  }

  // ---------- laptop ----------

  /** Laptop: create a session and connect. Resolves with the pairing code to show. */
  async startSession(): Promise<{ code: string; expiresIn: number }> {
    this.set("pairing");
    try {
      const made = await this.rest("/sessions", { method: "POST" });
      this.credentials = { session: String(made.session), token: String(made.laptop_token) };
      this.code = String(made.code);
      this.connect();
      return { code: this.code, expiresIn: Number(made.code_expires_in) };
    } catch (error) {
      this.set("idle");
      throw error;
    }
  }
  /** Public server hints: protocol version, LAN addresses, whether this page is a secure context. */
  async info(): Promise<{ v: number; websocket: boolean; lan_addresses: string[]; secure_context: boolean; sensor_note: string }> {
    const f = this.o.fetchImpl ?? fetch;
    const response = await f(`${this.base()}${this.o.prefix}/info`);
    return (await response.json()) as never;
  }
  approve(requestId: string) { this.send({ t: "approve", request_id: requestId }); }
  deny(requestId: string) { this.send({ t: "deny", request_id: requestId }); }
  newCode() { this.send({ t: "new_code" }); }
  /** Laptop: ends the session for everyone. Desktop navigation is untouched. */
  revoke() { this.send({ t: "revoke" }); }
  publish(state: RouteState) { this.send({ t: "route_state", ...state }); }

  // ---------- phone ----------

  /** Phone: reconnect with credentials kept from an earlier page load of the same tab. */
  resume() { this.connect(); }

  /** Phone: exchange the code for a request the laptop's user must confirm. Resolves with the number to compare. */
  async pair(code: string): Promise<number> {
    this.set("pairing");
    try {
      const paired = await this.rest("/pair", { method: "POST", body: JSON.stringify({ code }) });
      this.credentials = { session: String(paired.session), token: String(paired.phone_secret), verify: Number(paired.verify) };
      this.connect();
      return Number(paired.verify);
    } catch (error) {
      this.set("idle");
      throw error;
    }
  }
  /** Phone: accumulate a look delta (degrees, clockwise/up positive). Sent at most every HEADING_FLUSH_MS. */
  look(dyaw: number, dpitch: number, mode: LookMode) {
    if (!Number.isFinite(dyaw) || !Number.isFinite(dpitch)) return;
    this.pending.dyaw += dyaw; this.pending.dpitch += dpitch; this.pending.mode = mode;
    if (this.flush === null) this.flush = this.sched.set(() => this.flushLook(), HEADING_FLUSH_MS);
  }
  private flushLook() {
    this.flush = null;
    const { dyaw, dpitch, mode } = this.pending;
    this.pending = { dyaw: 0, dpitch: 0, mode };
    if (Math.abs(dyaw) < 1e-3 && Math.abs(dpitch) < 1e-3) return;
    for (const [y, p] of splitDelta(dyaw, dpitch)) this.send({ t: "heading", dyaw: round3(y), dpitch: round3(p), mode });
  }
  step(action: StepAction) { this.send({ t: "step", action }); }
  recenter() { this.send({ t: "recenter" }); }

  // ---------- transport ----------

  private connect() {
    if (!this.credentials || this.state === "ended") return;
    const url = `${this.base().replace(/^http/, "ws")}${this.o.prefix}/ws`;
    const socket = (this.o.socketFactory ?? ((u: string) => new WebSocket(u) as unknown as SocketLike))(url);
    this.socket = socket;
    this.set(this.attempts > 0 ? "reconnecting" : "connecting");
    socket.onopen = () => {
      // The secret goes in the first frame, never in the URL.
      socket.send(JSON.stringify({ v: PROTOCOL_VERSION, t: "hello", role: this.o.role, session: this.credentials!.session, token: this.credentials!.token }));
    };
    socket.onmessage = ev => { const frame = parseFrame(ev.data); if (frame && this.socket === socket) this.receive(frame); };
    socket.onclose = ev => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.peerOnline = false;
      if (this.state === "ended") return;
      if (FINAL_CLOSE_CODES.has(ev.code)) return this.end(this.endedReason ?? closeReason(ev.code, ev.reason));
      this.scheduleRetry();
    };
    socket.onerror = () => { /* onclose follows */ };
  }

  private scheduleRetry() {
    const { minMs, maxMs, maxAttempts } = this.o.reconnect;
    if (this.attempts >= maxAttempts) return this.end("connection_lost");
    const delay = Math.min(maxMs, minMs * 2 ** this.attempts);
    this.attempts++;
    this.set("reconnecting");
    this.retry = this.sched.set(() => { this.retry = null; this.connect(); }, delay);
  }

  private receive(frame: ServerMessage | Relayed) {
    switch (frame.t) {
      case "hello_ok":
        this.attempts = 0;
        this.seq = Math.max(this.seq, frame.last_seq);       // continue numbering after the last accepted message
        this.peerOnline = frame.peer_online;
        this.set(frame.approved ? "paired" : "waiting");
        this.emit("peer", frame.peer_online);
        for (const request of frame.pending ?? []) this.emit("pair_request", request);
        break;
      case "pending": this.emit("verify", frame.verify); break;
      case "approved": this.seq = Math.max(this.seq, frame.last_seq); this.set("paired"); break;
      case "pair_request": this.emit("pair_request", frame); break;
      case "code": this.code = frame.code; this.emit("code", frame.code, frame.code_expires_in); break;
      case "peer": this.peerOnline = frame.online; this.emit("peer", frame.online); break;
      case "route_state": {
        if (frame.seq < this.lastRouteSeq) break;             // out-of-order or stale snapshot
        this.lastRouteSeq = frame.seq;
        const { t: _t, seq: _s, replay, ...state } = frame;
        this.emit("route_state", state as RouteState, Boolean(replay));
        break;
      }
      case "heading": this.emit("heading", frame.dyaw, frame.dpitch, frame.mode); break;
      case "step": this.emit("step", frame.action); break;
      case "recenter": this.emit("recenter"); break;
      case "bye": this.endedReason = frame.reason; break;     // the close frame that follows decides
      case "error": this.emit("notice", frame.code, frame.message); break;
      case "pong": break;
    }
  }

  private send(message: Record<string, unknown>) {
    if (!this.socket || this.socket.readyState !== OPEN || this.state === "ended") return false;
    this.seq += 1;
    this.socket.send(JSON.stringify({ v: PROTOCOL_VERSION, seq: this.seq, ...message }));
    return true;
  }

  private end(reason: string) {
    this.endedReason = reason;
    this.set("ended");
    this.emit("ended", reason);
  }

  /** Close without ending the server session (e.g. the page is going away). The phone can resume later. */
  disconnect() {
    if (this.retry !== null) this.sched.clear(this.retry);
    if (this.flush !== null) this.sched.clear(this.flush);
    this.retry = this.flush = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000, "client_closed");
    this.set("idle");
  }
}

const round3 = (n: number) => Math.round(n * 1000) / 1000;

function closeReason(code: number, reason?: string): string {
  if (reason) return reason;
  return ({ 4401: "auth_failed", 4403: "origin", 4409: "replaced", 4410: "revoked", 4426: "unsupported_version", 1008: "policy" } as Record<number, string>)[code] ?? "closed";
}

export const REASON_TEXT: Record<string, string> = {
  revoked: "The laptop ended this pairing.",
  replaced: "Another phone took over this pairing.",
  denied: "The laptop did not accept this phone.",
  request_expired: "The laptop did not confirm in time. Ask for a new code.",
  expired: "This pairing expired. Pair again.",
  idle: "This pairing timed out after a long pause. Pair again.",
  auth_failed: "This pairing is no longer valid. Pair again.",
  connection_lost: "The connection could not be restored. Pair again.",
  too_fast: "Too many movement updates were sent, so the laptop closed the link. Pair again.",
};

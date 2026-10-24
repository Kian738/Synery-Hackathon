// Companion protocol v1: the messages between a laptop (shows the building) and a phone (controller).
// Mirrors server/companion.py, which validates every frame again. Full contract: docs/parallel/phone-handoff.md.
import type { GuideStep } from "../lib/types";

export const PROTOCOL_VERSION = 1;
export const MAX_DELTA_DEG = 90;           // per heading message; the client splits larger turns
export const HEADING_FLUSH_MS = 50;        // client sends at most 20 heading messages per second (server allows 30)
export const ICONS = ["start", "straight", "left", "right", "back", "lift", "stairs", "outside", "arrive"] as const;
export type Icon = (typeof ICONS)[number];
export type StepAction = "next" | "back" | "repeat";
export type Role = "laptop" | "phone";
export type LookMode = "touch" | "gyro";

export interface Instruction { text: string; short: string; icon: Icon; metres?: number }
export interface RouteState {
  status: "idle" | "guiding" | "arrived";
  route_id?: string | null;
  step_index?: number;
  step_count?: number;
  instruction?: Instruction;
  next?: Instruction;
  /** Laptop camera heading in degrees clockwise from the plan's +Y axis, informational only. */
  heading_deg?: number;
}

/** What the laptop publishes: a snapshot, never a command to the phone. */
export type LaptopMessage =
  | ({ t: "route_state" } & RouteState)
  | { t: "approve" | "deny"; request_id: string }
  | { t: "new_code" | "revoke" | "ping" };

/** What the phone may ask for. The laptop decides what to do with each; none of them move the person. */
export type PhoneMessage =
  | { t: "heading"; dyaw: number; dpitch: number; mode: LookMode }
  | { t: "step"; action: StepAction }
  | { t: "recenter" | "ping" };

export type ServerMessage =
  | { t: "hello_ok"; role: Role; session: string; last_seq: number; peer_online: boolean; approved: boolean; pending?: PairRequest[]; phone_paired?: boolean }
  | { t: "pending"; verify: number }
  | { t: "approved"; last_seq: number }
  | ({ t: "pair_request" } & PairRequest)
  | { t: "code"; code: string; code_expires_in: number }
  | { t: "peer"; role: Role; online: boolean }
  | { t: "pong" }
  | { t: "bye"; reason: string }
  | { t: "error"; code: string; message: string };

export interface PairRequest { request_id: string; verify: number; expires_in: number }

/** Relayed frames carry the sender's seq; replayed state after a reconnect carries replay: true. */
export type Relayed =
  | ({ t: "route_state"; seq: number; replay?: boolean } & RouteState)
  | { t: "heading"; seq: number; dyaw: number; dpitch: number; mode: LookMode }
  | { t: "step"; seq: number; action: StepAction }
  | { t: "recenter"; seq: number };

/** WebSocket close codes after which reconnecting would be wrong or useless. */
export const FINAL_CLOSE_CODES = new Set([1008, 4401, 4403, 4409, 4410, 4426]);

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function parseFrame(raw: unknown): (ServerMessage | Relayed) | null {
  if (typeof raw !== "string" || raw.length > 16_384) return null;
  let value: unknown;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!isRecord(value) || value.v !== PROTOCOL_VERSION || typeof value.t !== "string") return null;
  switch (value.t) {
    case "hello_ok": return typeof value.session === "string" && Number.isInteger(value.last_seq) ? (value as unknown as ServerMessage) : null;
    case "pending": return finite(value.verify) ? (value as unknown as ServerMessage) : null;
    case "approved": return Number.isInteger(value.last_seq) ? (value as unknown as ServerMessage) : null;
    case "pair_request": return typeof value.request_id === "string" && finite(value.verify) ? (value as unknown as ServerMessage) : null;
    case "code": return typeof value.code === "string" ? (value as unknown as ServerMessage) : null;
    case "peer": return (value.role === "laptop" || value.role === "phone") && typeof value.online === "boolean" ? (value as unknown as ServerMessage) : null;
    case "pong": return value as unknown as ServerMessage;
    case "bye": return typeof value.reason === "string" ? (value as unknown as ServerMessage) : null;
    case "error": return typeof value.code === "string" ? (value as unknown as ServerMessage) : null;
    case "heading": return finite(value.dyaw) && finite(value.dpitch) && (value.mode === "touch" || value.mode === "gyro") && Number.isInteger(value.seq) ? (value as unknown as Relayed) : null;
    case "step": return (value.action === "next" || value.action === "back" || value.action === "repeat") && Number.isInteger(value.seq) ? (value as unknown as Relayed) : null;
    case "recenter": return Number.isInteger(value.seq) ? (value as unknown as Relayed) : null;
    case "route_state": return validRouteState(value) ? (value as unknown as Relayed) : null;
    default: return null;
  }
}

function validInstruction(v: unknown): v is Instruction {
  return isRecord(v) && typeof v.text === "string" && v.text.length > 0 && typeof v.short === "string" && ICONS.includes(v.icon as Icon);
}
function validRouteState(v: Record<string, unknown>): boolean {
  if (!Number.isInteger(v.seq) || !(v.status === "idle" || v.status === "guiding" || v.status === "arrived")) return false;
  if (v.status === "idle") return true;
  return Number.isInteger(v.step_count) && Number.isInteger(v.step_index) && (v.step_index as number) >= 0 && (v.step_index as number) < (v.step_count as number) && validInstruction(v.instruction);
}

/** Splits a turn into messages the server accepts (|delta| <= MAX_DELTA_DEG each). */
export function splitDelta(dyaw: number, dpitch: number): [number, number][] {
  if (!finite(dyaw) || !finite(dpitch)) return [];
  const n = Math.max(1, Math.ceil(Math.max(Math.abs(dyaw), Math.abs(dpitch)) / MAX_DELTA_DEG));
  return Array.from({ length: n }, () => [dyaw / n, dpitch / n]);
}

export const wrapDeg = (d: number) => ((((d + 180) % 360) + 360) % 360) - 180;

/** Laptop helper: the Navigator's GuideStep list to a route_state snapshot. The index is the laptop's, not the phone's. */
export function routeStateFromGuide(steps: GuideStep[], index: number, opts: { routeId?: string; headingDeg?: number } = {}): RouteState {
  if (!steps.length) return { status: "idle", route_id: opts.routeId ?? null };
  const i = Math.min(Math.max(0, Math.floor(index)), steps.length - 1);
  const toInstruction = (s: GuideStep): Instruction => ({ text: s.text.slice(0, 240), short: s.short.slice(0, 240), icon: s.icon, ...(Number.isFinite(s.metres) && s.metres >= 0 ? { metres: Math.round(s.metres * 10) / 10 } : {}) });
  return {
    status: steps[i].kind === "arrive" ? "arrived" : "guiding",
    route_id: opts.routeId ?? null,
    step_index: i,
    step_count: steps.length,
    instruction: toInstruction(steps[i]),
    ...(steps[i + 1] ? { next: toInstruction(steps[i + 1]) } : {}),
    ...(opts.headingDeg !== undefined && Number.isFinite(opts.headingDeg) ? { heading_deg: opts.headingDeg } : {}),
  };
}

import type { BuildingRow, Geometry, Route, UiEvent } from "./types";

export class ApiError extends Error {
  candidates: { id: string; label?: string }[];
  constructor(message: string, candidates: { id: string; label?: string }[] = []) {
    super(message);
    this.candidates = candidates;
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    if (typeof detail === "string") throw new ApiError(detail);
    throw new ApiError(detail?.error ?? `Request failed (${response.status})`, detail?.candidates ?? []);
  }
  return response.json();
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

type WithEvents<T> = { result: T; events: UiEvent[] };

export const api = {
  buildings: () => fetch("/api/buildings").then(json<BuildingRow[]>),
  geometry: (building: string) => fetch(`/api/buildings/${building}`).then(json<Geometry>),
  newSession: (building_id: string) => post("/api/sessions", { building_id }).then(json<{ session_id: string }>),
  sessionGeometry: (sessionId: string) => fetch(`/api/sessions/${sessionId}/geometry`).then(json<Geometry>),
  route: (sessionId: string, body: Record<string, unknown>) =>
    post(`/api/sessions/${sessionId}/route`, body).then(json<WithEvents<any>>),
  close: (sessionId: string, element: string, closed: boolean) =>
    post(`/api/sessions/${sessionId}/close`, { element, closed }).then(json<WithEvents<any>>),
  door: (sessionId: string, first: string, second: string, confirm: boolean) =>
    post(`/api/sessions/${sessionId}/door`, { first, second, confirm }).then(json<WithEvents<any>>),
  routePreview: (building: string, start: string, destination = "", stepFree = false) =>
    fetch(`/api/lab/route-preview?building=${building}&start=${encodeURIComponent(start)}&destination=${encodeURIComponent(destination)}&step_free=${stepFree}`).then(json<Route>),
};

export type ChatEvent =
  | { type: "tool"; data: { name: string; input: Record<string, any> } }
  | { type: "ui"; data: UiEvent }
  | { type: "reply"; data: { text: string; usage: Record<string, number>; model: string } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: null };

/** Read a server-sent-events body line by line. */
export async function readEvents<T>(response: Response, onEvent: (e: T) => void) {
  if (!response.body) throw new ApiError("no stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)));
    }
  }
}

export const chat = (sessionId: string, text: string, onEvent: (e: ChatEvent) => void) =>
  post(`/api/sessions/${sessionId}/chat`, { text }).then((r) => readEvents(r, onEvent));

// ---------- Lab ----------

export interface RunSummary {
  run: string;
  suite: string;
  config: Record<string, unknown>;
  git: string;
  seconds: number;
  total: number;
  correct: number;
  accuracy: number | null;
  ci95_wilson?: [number, number];
  ci95_clustered?: [number, number] | null;
  buildings?: number;
  by_kind: Record<string, { correct?: number; wrong?: number }>;
  by_source?: Record<string, { correct?: number; wrong?: number }>;
  usage: Record<string, number>;
  started: string;
}

export const lab = {
  suites: () => fetch("/api/lab/suites").then(json<{ suites: Record<string, { label: string; llm: boolean | string; args: string[] }>; provider: { name: string; available: boolean; models: Record<string, string | null> } }>),
  runs: () => fetch("/api/lab/runs").then(json<RunSummary[]>),
  run: (run: string) => fetch(`/api/lab/runs/${run}`).then(json<{ summary: RunSummary; rows: any[] }>),
  compare: (a: string, b: string) => fetch(`/api/lab/compare?a=${a}&b=${b}`).then(json<{ a: RunSummary; b: RunSummary; changes: any[]; counts: Record<string, number> }>),
  dataset: () => fetch("/api/lab/dataset").then(json<{ buildings: any[]; splits: Record<string, number> }>),
  launch: (suite: string, args: string[]) => post("/api/lab/jobs", { suite, args }).then(json<{ id: string }>),
  jobs: () => fetch("/api/lab/jobs").then(json<any[]>),
  stream: (id: string, onEvent: (e: { type: string; text?: string; code?: number; run?: string }) => void) =>
    fetch(`/api/lab/jobs/${id}/stream`).then((r) => readEvents(r, onEvent)),
};

import type { BuildingRow, Geometry, Route, UiEvent, Audience, ScenarioReport, RobustReport } from "./types";

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
  resultPage: (session:string,result:string,offset=0,view='default',room='') => fetch(`/api/sessions/${session}/results/${result}?offset=${offset}&limit=25&view=${view}${room?`&room=${encodeURIComponent(room)}`:""}`).then(json<{rows:Record<string,unknown>[];total:number;next_offset:number|null}>),
  profile: (id: string, body: Record<string, unknown>) => post(`/api/sessions/${id}/profile`, body).then(json<{profile: unknown; events: UiEvent[]; route_update?: any}>),
  widen: (id: string, opening_id: string, width_m: number) => post(`/api/sessions/${id}/widen`, {opening_id, width_m}).then(json<WithEvents<any>>),
  closePreview: (sessionId: string, element: string) => post(`/api/sessions/${sessionId}/close/preview`, { element, closed: true }).then(json<WithEvents<any>>),
  scenario: (id: string, hazardSpace: string, audience: Audience, capacities: { element: string; kind: "total_persons"; value: number }[] = []) => post(`/api/sessions/${id}/scenario`, {template: "evacuation", params: {spec: {hazards: [{spaces: [hazardSpace]}, ...(capacities.some(c => c.value === 0) ? [{elements: capacities.filter(c => c.value === 0).map(c => c.element)}] : [])], responders: {auto: true}, ...(capacities.some(c => c.value > 0) ? {capacities: capacities.filter(c => c.value > 0)} : {})}}, audience}).then(json<ScenarioReport>),
  scenarioRobust: (id: string, hazardSpace: string) => post(`/api/sessions/${id}/scenario/robust`, {params: {spec: {hazards: [{spaces: [hazardSpace]}]}}}).then(json<RobustReport>),
  weakPoints: (id: string) => fetch(`/api/sessions/${id}/weak-points`).then(json<WithEvents<any>>),
  buildings: () => fetch("/api/buildings").then(json<BuildingRow[]>),
  geometry: (building: string) => fetch(`/api/buildings/${building}`).then(json<Geometry>),
  newSession: (building_id: string) => post("/api/sessions", { building_id }).then(json<{ session_id: string }>),
  sessionGeometry: (sessionId: string) => fetch(`/api/sessions/${sessionId}/scene`).then(json<Geometry>),
  route: (sessionId: string, body: Record<string, unknown>) =>
    post(`/api/sessions/${sessionId}/route`, body).then(json<WithEvents<any>>),
  close: (sessionId: string, element: string, closed: boolean) =>
    post(`/api/sessions/${sessionId}/close`, { element, closed }).then(json<WithEvents<any>>),
  door: (sessionId: string, first: string, second: string, confirm: boolean) =>
    post(`/api/sessions/${sessionId}/door`, { first, second, confirm }).then(json<WithEvents<any>>),
  routePreview: (building: string, start: string, destination = "", stepFree = false) =>
    fetch(`/api/lab/route-preview?building=${building}&start=${encodeURIComponent(start)}&destination=${encodeURIComponent(destination)}&step_free=${stepFree}`).then(json<Route>),
};

const buildingPreloadCache = new Map<string, Promise<{ session_id: string; geometry: Geometry }>>();

/** Preload a building's session and 3D geometry in the background while still on the exterior map. */
export function preloadBuilding(buildingId: string): Promise<{ session_id: string; geometry: Geometry }> {
  if (!buildingPreloadCache.has(buildingId)) {
    const promise = (async () => {
      const { session_id } = await api.newSession(buildingId);
      const geometry = await api.sessionGeometry(session_id);
      return { session_id, geometry };
    })();
    buildingPreloadCache.set(buildingId, promise);
  }
  return buildingPreloadCache.get(buildingId)!;
}

/** Retrieve preloaded building data and consume it so it's not reused with stale sessions. */
export function consumePreloadedBuilding(buildingId: string): Promise<{ session_id: string; geometry: Geometry }> | null {
  const cached = buildingPreloadCache.get(buildingId);
  if (cached) {
    buildingPreloadCache.delete(buildingId);
    return cached;
  }
  return null;
}

export type ChatEvent =
  | { type: "assistant_start"; data: {message_id:string;model:string} }
  | { type: "assistant_delta"; data: {message_id:string;text:string} }
  | { type: "assistant_end"; data: {message_id:string} }
  | { type: "progress"; data: {stage:string;message:string} }
  | { type: "tool"; data: { name: string; input: Record<string, any> } }
  | { type: "tool_result"; data: { name: string; content: string; is_error?: boolean } }
  | { type: "ui"; data: UiEvent }
  | { type: "reply"; data: { text: string; usage: Record<string, unknown>; model: string; message_id?: string } }
  | { type: "text_delta"; data: { text: string } }
  | { type: "clear_deltas"; data?: Record<string, unknown> }
  | { type: "audio_chunk"; data: { audio: string; text?: string; index?: number; format?: string } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: null };

/** Read a server-sent-events body line by line. */
export async function readEvents<T>(response: Response, onEvent: (e: T) => void) {
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(`Chat request failed (${response.status}): ${detail.slice(0, 160)}`);
  }
  if (!response.body) throw new ApiError("Chat stream unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let ended=false;
  try { for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");
    if (done && buffer.trim()) buffer += "\n\n";
    let index;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      const data = chunk.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      if (data) {
        let event: T;
        try { event = JSON.parse(data); } catch { throw new ApiError("Chat returned an invalid event. Please retry."); }
        onEvent(event);
      }
    }
    if (done) {ended=true;break;}
  }} finally {if(!ended)await reader.cancel().catch(()=>{});reader.releaseLock();}
}

export const chat = async(sessionId: string, text: string, onEvent: (e: ChatEvent) => void,selectedSpace?:string|null,requestId?:string,signal?:AbortSignal) => {
  let finished=false;
  const response=await fetch(`/api/sessions/${sessionId}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,selected_space:selectedSpace??null,request_id:requestId}),signal});
  await readEvents<ChatEvent>(response,e=>{if(e.type==='done')finished=true;onEvent(e);});
  if(!finished)throw new ApiError('Connection ended before the answer completed. Your partial answer and computed results remain available.');
};

export const cancelChat=(session:string,request_id:string)=>post(`/api/sessions/${session}/chat/cancel`,{request_id});

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

export interface CheckSheet {
  groups: { id: string; title: string; about: string }[];
  checks: { id: string; group: string; title: string; proves: string; suite: string; args: string[]; target: number; cost: string;
    status: "pass" | "fail" | "not run"; latest: (RunSummary & { config: Record<string, any> }) | null; history: (number | null)[] }[];
  counts: Record<string, number>;
}

export const lab = {
  checks: () => fetch("/api/lab/checks").then(json<CheckSheet>),
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

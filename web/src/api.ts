import type { BuildingRow, Geometry, UiEvent } from "./types";

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.error ?? `HTTP ${response.status}`);
  }
  return response.json();
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  buildings: (split?: string) => fetch(`/api/buildings${split ? `?split=${split}` : ""}`).then(json<BuildingRow[]>),
  newSession: (building_id: string) => post("/api/sessions", { building_id }).then(json<{ session_id: string }>),
  geometry: (sessionId: string) => fetch(`/api/sessions/${sessionId}/geometry`).then(json<Geometry>),
  route: (sessionId: string, body: Record<string, unknown>) =>
    post(`/api/sessions/${sessionId}/route`, body).then(json<{ result: any; events: UiEvent[] }>),
  close: (sessionId: string, element: string, closed: boolean) =>
    post(`/api/sessions/${sessionId}/close`, { element, closed }).then(json<{ result: any; events: UiEvent[] }>),
  door: (sessionId: string, first: string, second: string, confirm: boolean) =>
    post(`/api/sessions/${sessionId}/door`, { first, second, confirm }).then(json<{ result: any; events: UiEvent[] }>),
};

export type ChatStreamEvent =
  | { type: "tool"; data: { name: string; input: Record<string, unknown> } }
  | { type: "ui"; data: UiEvent }
  | { type: "reply"; data: { text: string; usage: Record<string, number> } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: null };

/** POST a chat turn and read the server-sent events as they arrive. */
export async function chatStream(sessionId: string, text: string, onEvent: (e: ChatStreamEvent) => void) {
  const response = await post(`/api/sessions/${sessionId}/chat`, { text });
  if (!response.body) throw new Error("no stream");
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

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, chat } from "../lib/api";
import { label as labelOf } from "../lib/geometry";
import type { Geometry, Opening, Route, UiEvent } from "../lib/types";

export type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "agent"; text: string; model?: string }
  | { id: number; role: "activity"; text: string }
  | { id: number; role: "error"; text: string }
  | { id: number; role: "options"; text: string; options: { id: string; label: string }[]; purpose: "destination" | "start" }
  | { id: number; role: "change"; text: string; first: string; second: string; state: "pending" | "applied" | "discarded" };

type NewMessage = Message extends infer M ? (M extends Message ? Omit<M, "id"> : never) : never;

let nextId = 1;

const ACTIVITY: Record<string, (i: any) => string> = {
  building_overview: () => "Reading the building",
  search: (i) => `Looking for “${i.query}”`,
  room_info: (i) => `Checking ${i.room}`,
  find_route: (i) => `Planning a route to ${i.destination}`,
  reachable_rooms: (i) => `Checking what can be reached on ${i.floor}`,
  rank_rooms: (i) => `Comparing ${i.room_type} rooms`,
  nearest: (i) => `Finding the nearest ${i.what}`,
  remember_person: () => "Remembering this for later routes",
  set_closed: (i) => `${i.closed ? "Closing" : "Reopening"} ${i.element}`,
  add_door: (i) => (i.confirm ? "Adding the door" : "Previewing a new door"),
  move_item: (i) => `Moving ${i.item}`,
};

/** All Navigator state: one session per building; map actions and the agent share it. */
export function useNavigator(buildingId: string) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [floorId, setFloorId] = useState("");
  const [route, setRoute] = useState<Route | null>(null);
  const [routeMeta, setRouteMeta] = useState<{ from: string; to: string; alternatives?: { room: string; walk_m: number }[] } | null>(null);
  const [highlights, setHighlights] = useState<Set<string>>(new Set());
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [here, setHere] = useState<string | null>(null);
  const [stepFree, setStepFree] = useState(false);
  const [previewDoor, setPreviewDoor] = useState<Opening | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const geometryRef = useRef<Geometry | null>(null);
  geometryRef.current = geometry;

  const push = (m: NewMessage) => setMessages((all) => [...all, { ...(m as Message), id: nextId++ }]);

  useEffect(() => {
    let cancelled = false;
    setGeometry(null);
    (async () => {
      const { session_id } = await api.newSession(buildingId);
      const g = await api.sessionGeometry(session_id);
      if (cancelled) return;
      setSessionId(session_id);
      setGeometry(g);
      const ground = [...g.floors].sort((a, b) => Math.abs(a.level) - Math.abs(b.level))[0];
      setFloorId(ground.id);
      setRoute(null); setRouteMeta(null); setHighlights(new Set()); setClosed(new Set()); setPreviewDoor(null);
      setMessages([]); setActiveStep(0);
      const at = new URLSearchParams(window.location.search).get("at");
      setHere(at && g.spaces.some((s) => s.id === at) ? at : null);
    })().catch((e) => setNotice(String(e.message ?? e)));
    return () => { cancelled = true; };
  }, [buildingId]);

  const showRoute = useCallback((r: Route) => {
    setRoute(r);
    setPreviewDoor(null);
    setActiveStep(0);
    if (r.polyline.length) setFloorId(r.polyline[0].floor_id);
  }, []);

  const apply = useCallback((events: UiEvent[]) => {
    const g = geometryRef.current;
    for (const e of events) {
      if (e.type === "route") showRoute(e.route);
      else if (e.type === "highlight") {
        setHighlights(new Set(e.ids));
        const first = g?.spaces.find((s) => s.id === e.ids[0]) ?? g?.assets.find((a) => a.id === e.ids[0]);
        if (first) setFloorId(first.floor_id);
      } else if (e.type === "closure") {
        setClosed((c) => { const n = new Set(c); e.closed ? n.add(e.id) : n.delete(e.id); return n; });
      } else if (e.type === "preview_door") {
        setPreviewDoor(e.door);
        setFloorId(e.door.floor_id);
      } else if (e.type === "edit") {
        setPreviewDoor(null);
        if (sessionIdRef.current) api.sessionGeometry(sessionIdRef.current).then(setGeometry);
      } else if (e.type === "profile") {
        if (e.profile.step_free) setStepFree(true);
        if (e.profile.location) setHere(e.profile.location);
      }
    }
  }, [showRoute]);
  const sessionIdRef = useRef<string | null>(null);
  sessionIdRef.current = sessionId;

  /** Deterministic routing (no LLM): from "here" to a place, a room id, or a category word. */
  const goTo = useCallback(async (destination: string, from?: string | null, stepFreeOverride?: boolean) => {
    if (!sessionId || !geometry) return;
    const start = from ?? here;
    if (!start) {
      setNotice("Where are you? Tap your room on the plan, then choose “I'm here”.");
      return;
    }
    try {
      const { result, events } = await api.route(sessionId, { start, destination, step_free: stepFreeOverride ?? stepFree });
      if (result.error) {
        setNotice(result.error);
        return;
      }
      setRouteMeta({ from: result.from, to: result.to, alternatives: result.other_matches_further_away });
      apply(events);
      setNotice(null);
    } catch (e) {
      const err = e as ApiError;
      if (err.candidates?.length) {
        push({ role: "options", text: `Which one do you mean?`, options: err.candidates.map((c) => ({ id: c.id, label: c.label ?? c.id })), purpose: "destination" });
      } else setNotice(err.message);
    }
  }, [sessionId, geometry, here, stepFree, apply]);

  const toggleClosed = useCallback(async (id: string) => {
    if (!sessionId) return;
    const { result, events } = await api.close(sessionId, id, !closed.has(id));
    apply(events);
    const impact = result.impact;
    setNotice(`${result.element} ${result.closed ? "closed" : "reopened"}. ` +
      (impact.cut_off_count ? `${impact.cut_off_count} rooms lose their way out. ` : "") +
      (impact.longer_way_out_count ? `${impact.longer_way_out_count} rooms have a longer way out.` : "No room is cut off."));
  }, [sessionId, closed, apply]);

  const decideChange = useCallback(async (message: Extract<Message, { role: "change" }>, accept: boolean) => {
    setMessages((all) => all.map((m) => (m.id === message.id ? { ...m, state: accept ? "applied" : "discarded" } as Message : m)));
    if (!accept || !sessionId) { setPreviewDoor(null); return; }
    const { events } = await api.door(sessionId, message.first, message.second, true);
    apply(events);
  }, [sessionId, apply]);

  const ask = useCallback(async (text: string) => {
    if (!sessionId) return;
    push({ role: "user", text });
    setBusy(true);
    const g = geometryRef.current;
    const context = [here ? `(I am in ${labelOf(g!, here)}.)` : "", stepFree ? "(I need step-free routes.)" : ""].filter(Boolean).join(" ");
    try {
      await chat(sessionId, context ? `${text} ${context}` : text, (event) => {
        if (event.type === "tool") push({ role: "activity", text: (ACTIVITY[event.data.name] ?? (() => event.data.name))(event.data.input) });
        else if (event.type === "ui") {
          apply([event.data]);
          if (event.data.type === "preview_door") {
            const d = event.data.door;
            push({ role: "change", text: `New door between ${labelOf(g!, d.space_ids[0])} and ${labelOf(g!, d.space_ids[1])}. ${event.data.impact.shorter_way_out_count} rooms get a shorter way out.`, first: d.space_ids[0], second: d.space_ids[1], state: "pending" });
          }
          if (event.data.type === "route") {
            const r = event.data.route;
            setRouteMeta({ from: labelOf(g!, r.stops[0]), to: labelOf(g!, r.stops[r.stops.length - 1]) });
          }
        } else if (event.type === "reply") push({ role: "agent", text: event.data.text, model: event.data.model });
        else if (event.type === "error") push({ role: "error", text: event.data.message });
      });
    } catch (e) {
      push({ role: "error", text: String(e) });
    } finally {
      setBusy(false);
    }
  }, [sessionId, here, stepFree, apply]);

  const clearRoute = () => { setRoute(null); setRouteMeta(null); setActiveStep(0); };

  return {
    sessionId, geometry, floorId, setFloorId, route, routeMeta, clearRoute, highlights, setHighlights, closed,
    here, setHere, stepFree, setStepFree, previewDoor, messages, busy, notice, setNotice, activeStep, setActiveStep,
    goTo, ask, toggleClosed, decideChange,
  };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { isRoute, isVisualResult } from "../lib/validation";
import { fixCardText, impactText } from "../lib/impact";
import { ApiError, api, chat } from "../lib/api";
import { label as labelOf } from "../lib/geometry";
import { audioStreamQueue } from "../lib/voice";
import type { Geometry, Opening, Route, UiEvent, WeakPoint, VisualResult } from "../lib/types";

export type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "agent"; text: string; model?: string; streaming?: boolean }
  | { id: number; role: "activity"; text: string }
  | { id: number; role: "error"; text: string }
  | { id: number; role: "options"; text: string; options: { id: string; label: string }[]; purpose: "destination" | "start" }
  | { id: number; role: "change"; text: string; first: string; second: string; widenings?: {opening_id:string;to_m:number}[]; kind?: "widen"; openingId?: string; width?: number; start?: string; destination?: string; state: "pending" | "applied" | "discarded" };

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

/** The space behind an entrance, preferring lobbies on the floor nearest the ground. */
export function mainEntrance(g: Geometry): string | null {
  const levels = new Map(g.floors.map((f) => [f.id, Math.abs(f.level)]));
  const behind = entrances(g);
  const rank = (x: Geometry["spaces"][number]) => (x.room_type === "lobby" ? 0 : 10) + (levels.get(x.floor_id) ?? 0) + (x.type === "room" ? 0.5 : 0);
  return [...behind].sort((a, b) => rank(a) - rank(b))[0]?.id ?? null;
}

export function entrances(g: Geometry): Geometry["spaces"] {
  const ids = new Set(g.openings.filter((o) => o.space_ids.includes("outside")).flatMap((o) => o.space_ids.filter((x) => x !== "outside")));
  return g.spaces.filter((x) => ids.has(x.id));
}

/** All Navigator state: one session per building; map actions and the agent share it. */
export function useNavigator(buildingId: string) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [floorId, setFloorId] = useState("");
  const [route, setRoute] = useState<Route | null>(null);
  const [visualResult,setVisualResult]=useState<(VisualResult & {total_rows:number})|null>(null);
  const [turnUsage,setTurnUsage]=useState<Record<string,unknown>|null>(null);
  const [previousRoute, setPreviousRoute] = useState<Route | null>(null);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const routeRef = useRef<Route | null>(null); routeRef.current = route;
  const generation = useRef(0);
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
    generation.current++;
    setSessionId(null); setBusy(false); setNotice(null); setGeometry(null);
    setPreviousRoute(null); setWeakPoints([]); setVisualResult(null);setTurnUsage(null);
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
      // Start where a visitor actually stands: the QR/deep-link spot, else the main entrance.
      const at = new URLSearchParams(window.location.search).get("at");
      setHere(at && g.spaces.some((s) => s.id === at) ? at : mainEntrance(g));
    })().catch((e) => setNotice(String(e.message ?? e)));
    return () => { cancelled = true; };
  }, [buildingId]);

  const showRoute = useCallback((r: Route) => {
    if (!isRoute(r)) {
      setNotice("The route response was incomplete. Please try again."); return;
    }
    setRoute(r);setVisualResult(null);
    const building = geometryRef.current;
    if (building) setRouteMeta({from:labelOf(building,r.stops[0]),to:labelOf(building,r.stops[r.stops.length-1])});
    setPreviewDoor(null);
    setActiveStep(0);
    if (r.polyline.length) setFloorId(r.polyline[0].floor_id);
  }, []);

  const apply = useCallback((events: UiEvent[]) => {
    const g = geometryRef.current;
    for (const e of events) {
      if (!e || typeof e.type !== "string") { setNotice("An invalid update was ignored. Please retry."); continue; }
      if (e.type === "route") showRoute(e.route);
      else if(e.type==="visual_result") {
        const result=e.result;
        if(!isVisualResult(result)||!Number.isInteger(e.total_rows)||e.total_rows<0){setNotice("An incomplete visual answer was ignored. Please retry.");continue;}
        setVisualResult({...result,total_rows:e.total_rows});
        setHighlights(new Set(result.entities.map(entity=>entity.id)));
        const primary=(result.measurements.primary_ids as string[]|undefined)?.[0];
        const primaryFloor=result.entities.find(e=>e.id===primary)?.floor_id;
        if(primaryFloor||result.floor_ids.length)setFloorId(primaryFloor??result.floor_ids[0]);
      }
      else if (e.type === "highlight") {
        setHighlights(new Set(e.ids));
        const first = g?.spaces.find((s) => s.id === e.ids[0]) ?? g?.assets.find((a) => a.id === e.ids[0]);
        if (first) setFloorId(first.floor_id);
      } else if (e.type === "closure") {
        setPreviousRoute(routeRef.current); setRoute(null);
        setClosed((c) => { const n = new Set(c); e.closed ? n.add(e.id) : n.delete(e.id); return n; });
        setNotice(impactText(e.impact));
        setHighlights(new Set(e.impact.step_free?.cut_off_ids ?? e.impact.cut_off_ids ?? []));
      } else if (e.type === "fix_preview") {
        setPreviewDoor(e.opening); setFloorId(e.opening.floor_id);
        push({role: "change", kind: "widen", text: fixCardText(e.fix),
              first: "", second: "", widenings:e.fix.widen, openingId: e.opening.id, width: e.opening.width_m, start: e.start, destination: e.destination, state: "pending"});
      } else if (e.type === "weak_points") {
        setWeakPoints(e.items);
      } else if (e.type === "preview_door") {
        setPreviewDoor(e.door);
        setFloorId(e.door.floor_id);
      } else if (e.type === "edit") {
        setVisualResult(null); setPreviewDoor(null);
        if (sessionIdRef.current) api.sessionGeometry(sessionIdRef.current).then(setGeometry);
      } else if (e.type === "profile") {
        setStepFree(e.profile.step_free);
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
      const current = generation.current;
      const { result, events } = await api.route(sessionId, { start, destination, step_free: stepFreeOverride ?? stepFree });
      if (current !== generation.current) return;
      if (result.error) {
        setPreviousRoute(routeRef.current); setRoute(null); apply(events);
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
    setNotice(impactText(impact));
  }, [sessionId, closed, apply]);

  const decideChange = useCallback(async (message: Extract<Message, { role: "change" }>, accept: boolean) => {
    if (!accept) {
      setMessages(all => all.map(m => m.id === message.id ? {...m, state: "discarded"} as Message : m));
      setPreviewDoor(null); return;
    }
    if (!sessionId) return;
    try {
      if (message.kind === "widen" && message.openingId && message.width) {
        for(const widening of message.widenings ?? [{opening_id:message.openingId,to_m:message.width}]) {
          const {events} = await api.widen(sessionId, widening.opening_id, widening.to_m); apply(events);
        }
        if (message.start && message.destination) {
          const next = await api.route(sessionId, {start:message.start, destination:message.destination, step_free:true, min_door_width_m:message.width});
          apply(next.events); if (next.result.error) setNotice(next.result.error);
        }
      } else { const {events} = await api.door(sessionId, message.first, message.second, true); apply(events); }
      setMessages(all => all.map(m => m.id === message.id ? {...m, state: "applied"} as Message : m));
    } catch (error) { setNotice(String(error)); }

  }, [sessionId, apply]);

  const ask = useCallback(async (text: string,selectedSpace?:string|null) => {
    if (!sessionId) return;
    setVisualResult(null);setHighlights(new Set());
    push({ role: "user", text });
    setBusy(true);
    audioStreamQueue.reset();
    const current = generation.current;
    const g = geometryRef.current;

    try {
      await chat(sessionId, text, (event) => {
        if (current !== generation.current || !event || typeof event !== "object") return;
        if (event.type === "tool") push({ role: "activity", text: (ACTIVITY[event.data.name] ?? (() => event.data.name))(event.data.input) });
        else if (event.type === "ui") {
          apply([event.data]);
          if (event.data.type === "preview_door") {
            const d = event.data.door;
            push({ role: "change", text: `New door between ${labelOf(g!, d.space_ids[0])} and ${labelOf(g!, d.space_ids[1])}. ${event.data.impact.shorter_way_out_count} rooms get a shorter way out.`, first: d.space_ids[0], second: d.space_ids[1], state: "pending" });
          }
          if (event.data.type === "route" && isRoute(event.data.route)) {
            const r = event.data.route;
            setRouteMeta({ from: labelOf(g!, r.stops[0]), to: labelOf(g!, r.stops[r.stops.length - 1]) });
          }
        } else if (event.type === "text_delta" && typeof event.data?.text === "string") {
          const delta = event.data.text;
          setMessages((all) => {
            const last = all[all.length - 1];
            if (last && last.role === "agent" && last.streaming) {
              return [
                ...all.slice(0, -1),
                { ...last, text: last.text + delta },
              ];
            }
            return [
              ...all,
              { id: nextId++, role: "agent", text: delta, streaming: true },
            ];
          });
        } else if (event.type === "clear_deltas") {
          setMessages((all) => {
            const last = all[all.length - 1];
            if (last && last.role === "agent" && last.streaming) {
              return all.slice(0, -1);
            }
            return all;
          });
        } else if (event.type === "audio_chunk" && event.data?.audio) {
          audioStreamQueue.enqueue(event.data.audio, event.data.index ?? 0, event.data.text);
        } else if (event.type === "reply" && typeof event.data?.text === "string") {
          setTurnUsage(event.data.usage ?? null);
          setMessages((all) => {
            const last = all[all.length - 1];
            if (last && last.role === "agent" && last.streaming) {
              return [
                ...all.slice(0, -1),
                {
                  ...last,
                  text: event.data.text,
                  model: event.data.model,
                  streaming: false,
                },
              ];
            }
            return [
              ...all,
              {
                id: nextId++,
                role: "agent",
                text: event.data.text,
                model: event.data.model,
                streaming: false,
              },
            ];
          });
        } else if (event.type === "done") {
          audioStreamQueue.markDone();
        } else if (event.type === "error") push({ role: "error", text: typeof event.data?.message === "string" ? event.data.message : "Chat failed. Please retry." });
      },selectedSpace);
    } catch (e) {
      if (current === generation.current) push({ role: "error", text: String(e) });
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }, [sessionId, here, stepFree, apply]);

  useEffect(() => {
    if (sessionId && geometry) api.profile(sessionId, {step_free:stepFree, location:here}).then(response => {apply(response.events);if(response.route_update?.error){setPreviousRoute(routeRef.current);setRoute(null);setNotice(response.route_update.error);}}).catch(e => setNotice(e.message));
  }, [sessionId, geometry?.building.id, here, stepFree]);
  const inspectWeakPoints = async () => {
    if (!sessionId) return; setBusy(true);
    try { const response = await api.weakPoints(sessionId); apply(response.events); }
    catch(e) { setNotice(String(e)); } finally { setBusy(false); }
  };
  const clearRoute = () => { setRoute(null); setRouteMeta(null); setActiveStep(0); };

  return {
    visualResult,setVisualResult,turnUsage,previousRoute, weakPoints, inspectWeakPoints, sessionId, geometry, floorId, setFloorId, route, routeMeta, clearRoute, highlights, setHighlights, closed,
    here, setHere, stepFree, setStepFree, previewDoor, messages, busy, notice, setNotice, activeStep, setActiveStep,
    goTo, ask, toggleClosed, decideChange,
  };
}

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { RoomText } from "../components/RoomText";
import { ToolTrace } from "../components/ToolTrace";
import { CompanionControl } from "./CompanionControl";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { BuildDialog } from "../components/BuildDialog";
import { FloorRail } from "../components/FloorRail";
import { Pictogram } from "../components/Pictogram";
import { PlanView, type Pin } from "../components/PlanView";
import { api } from "../lib/api";
import type { ScenarioMark } from "../lib/types";
import { area, categories, centroid, label as labelOf, ZONE_LABEL, zoneOf } from "../lib/geometry";
import type { BuildingRow, GuideStep, Space, VisualResult } from "../lib/types";
import { audioStreamQueue, canListen, listen, speak, stopSpeaking } from "../lib/voice";
import { ScenarioPanel } from "./ScenarioPanel";
import { entrances, type Message, useNavigator } from "./useNavigator";

const DEFAULT_BUILDING = "proc-campus-dev-000";
const Building3D = lazy(() => import("../components/Building3D"));

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function findSpacesMentionedInText(
  text: string,
  spaces: Space[],
  visualResult?: VisualResult | null,
  highlights?: Set<string>
): Space[] {
  const found: Space[] = [];
  const addedIds = new Set<string>();

  const add = (s: Space) => {
    if (!addedIds.has(s.id)) {
      addedIds.add(s.id);
      found.push(s);
    }
  };

  const candidateIds = new Set<string>();
  if (visualResult?.entities) {
    for (const ent of visualResult.entities) {
      if (ent.kind === "room") candidateIds.add(ent.id);
    }
  }
  if (highlights) {
    for (const id of highlights) candidateIds.add(id);
  }

  // 1. Check candidate spaces first (from visual results or active highlights)
  for (const candId of candidateIds) {
    const s = spaces.find((sp) => sp.id === candId);
    if (!s) continue;
    const baseName = s.name.replace(/\s+\d+(\.\d+)?$/, "").trim();
    const pattern = new RegExp(
      `\\b(?:${escapeRegExp(s.name)}|${escapeRegExp(baseName)}${s.ref ? `|${escapeRegExp(s.ref)}` : ""})\\b`,
      "i"
    );
    if (pattern.test(text)) {
      add(s);
    }
  }

  // 2. Match room numbers, e.g. 0.08, 2.02, 2.08, 204, or "room 3", "office 02"
  const numberMatches = Array.from(
    text.matchAll(/\b\d+\.\d+\b|\b\d{2,4}\b|\b(?:room|office|kitchen|lab|corridor|hall|space)?\s*#?(\d{1,4})\b/gi)
  );
  for (const match of numberMatches) {
    const num = match[1] || match[0];
    if (!num) continue;
    const matchInCandidates = spaces.find(
      (s) => candidateIds.has(s.id) && (s.name.includes(num) || s.id.includes(num) || (s.ref && s.ref.includes(num)))
    );
    if (matchInCandidates) {
      add(matchInCandidates);
      continue;
    }
    const matchInAll = spaces.find((s) => {
      const tokens: string[] = s.name.match(/\b\d+\.\d+\b|\b\d{1,4}\b/g) ?? [];
      const idEnd = s.id.split("-").pop();
      return tokens.includes(num) || idEnd === num || s.name.includes(` ${num}`) || s.ref === num;
    });
    if (matchInAll) {
      add(matchInAll);
    }
  }

  // 3. Match distinctive room names (e.g. Makerspace, Main lobby, Cafeteria, Kitchen, Lab)
  const GENERIC = new Set([
    "room", "rooms", "floor", "space", "spaces", "corridor", "corridors",
    "office", "offices", "staircase", "elevator", "lift", "printer", "printers",
    "place", "places", "door", "doors", "level", "levels", "area", "areas"
  ]);

  for (const s of spaces) {
    const fullName = s.name.trim();
    if (fullName.length >= 4) {
      const pattern = new RegExp(`\\b${escapeRegExp(fullName)}\\b`, "i");
      if (pattern.test(text)) {
        add(s);
        continue;
      }
    }
    const baseName = s.name.replace(/\s+\d+(\.\d+)?$/, "").trim();
    if (baseName.length >= 3 && !GENERIC.has(baseName.toLowerCase())) {
      const pattern = new RegExp(`\\b${escapeRegExp(baseName)}\\b`, "i");
      if (pattern.test(text)) {
        add(s);
        continue;
      }
    }
    if (s.ref && s.ref.length >= 2) {
      const pattern = new RegExp(`\\b${escapeRegExp(s.ref)}\\b`, "i");
      if (pattern.test(text)) {
        add(s);
      }
    }
  }

  // Prioritize specific rooms over corridors if any rooms match
  if (found.length > 1) {
    const nonCorridors = found.filter((s) => !/corridor/i.test(s.name) && s.type !== "corridor");
    if (nonCorridors.length > 0) {
      return nonCorridors;
    }
  }

  return found;
}

export default function Navigator() {
  const [params, setParams] = useSearchParams();
  const buildingId = params.get("building") ?? DEFAULT_BUILDING;
  const nav = useNavigator(buildingId);
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [selected, setSelected] = useState<Space | null>(null);
  const [voiceOut, setVoiceOut] = useState(true);
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceFocusSpace, setVoiceFocusSpace] = useState<Space | null>(null);
  const [voiceHighlightId, setVoiceHighlightId] = useState<string | null>(null);
  const voiceTourTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [currentlySpeakingId, setCurrentlySpeakingId] = useState<number | null>(null);
  const [heading, setHeading] = useState<string>("");
  const [weakOpen, setWeakOpen] = useState(false);
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [scenarioMark,setScenarioMark]=useState<ScenarioMark|null>(null);
  const scenarioZones=useMemo(()=>{const z:Record<string,string>={};Object.entries(scenarioMark?.crowd??{}).forEach(([id,n])=>{z[id]=n===2?"crowd2":"crowd1";});scenarioMark?.responder?.spaces.forEach(id=>{z[id]="responder";});return z;},[scenarioMark]);
  useEffect(()=>{if(nav.scenarioIn)setScenarioOpen(true);},[nav.scenarioIn]);
  const [questionOpen, setQuestionOpen] = useState(false);
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [compact, setCompact] = useState(() => matchMedia("(max-width:1023px)").matches);
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsRef = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!toolsOpen) return;
    const outside = (e: PointerEvent) => { if (!toolsRef.current?.contains(e.target as Node)) setToolsOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { setToolsOpen(false); toolsRef.current?.querySelector("summary")?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [toolsOpen]);
  useEffect(() => {
    const q = matchMedia("(max-width:1023px)");
    const changed = () => { setCompact(q.matches); setToolsOpen(false); };
    q.addEventListener("change", changed);
    return () => q.removeEventListener("change", changed);
  }, []);
  const [lookOffset, setLookOffset] = useState({ yaw: 0, pitch: 0 });
  const [focusRequest, setFocusRequest] = useState<{ id: string; revision: number } | null>(null);
  const selectSpace = useCallback((space: Space) => {
    setSelected(space);
    setPlanExpanded(false);
    setWeakOpen(false);
    nav.setFloorId(space.floor_id);
  }, [nav.setFloorId]);
  const [stepMode, setStepMode] = useState(false);
  const [view, setView] = useState<"2d" | "3d" | "guide" | "follow">(params.get("view") === "2d" ? "2d" : "3d");
  const [scope, setScope] = useState<"current"|"route"|"building">("current");
  const [exploded,setExploded]=useState(true);
  const [planExpanded,setPlanExpanded]=useState(false);
  const [stageExpanded,setStageExpanded]=useState(params.get("explore")==="1");
  const [seekRequest,setSeekRequest]=useState(0);
  const [previewPosition,setPreviewPosition]=useState<{x:number;y:number;floor_id:string}|null>(null);
  const following=view==="follow"||view==="guide";
  const [picking, setPicking] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [buildingImport, setBuildingImport] = useState(false);

  useEffect(() => { api.buildings().then(setBuildings).catch(() => {}); }, []);
  useEffect(() => { setSelected(null); setStepMode(false);setView(params.get("view")==="2d"?"2d":"3d");setPreviewPosition(null);setPlanExpanded(false);setStageExpanded(params.get("explore")==="1");setScope("current");setWeakOpen(false);setQuestionOpen(false);setFocusRequest(null); }, [buildingId]);
  // Deep link (shareable, QR at a door): ?building=…&at=<space id>&to=<place>&step_free=1
  const linked = useRef(false);
  useEffect(() => {
    const to = params.get("to");
    if (linked.current || !to || !nav.geometry || !nav.here || !nav.sessionId) return;
    linked.current = true;
    const stepFree = params.get("step_free") === "1";
    if (stepFree) nav.setStepFree(true);
    nav.goTo(to, nav.here, stepFree);
  }, [nav.geometry, nav.here, nav.sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const g = nav.geometry;
  const steps = nav.route?.guide?.steps ?? [];
  const companionRouteId=nav.route?nav.sessionId??undefined:undefined;
  useEffect(()=>setLookOffset({yaw:0,pitch:0}),[nav.route]);
  const cats = useMemo(() => (g ? categories(g) : []), [g]);
  // Example requests built from this building's own rooms, items and lifts, so every one of them works here.
  const examples = useMemo(() => {
    if (!g) return [];
    const out: string[] = [];
    const toilet = g.spaces.some((x) => /toilet|bathroom/.test(x.room_type));
    const meeting = g.spaces.find((x) => x.room_type === "meeting_room" || x.room_type === "lab" || x.room_type === "office");
    if (toilet) out.push("I use a wheelchair. Take me to the nearest toilet.");
    else if (meeting) out.push(`I use a wheelchair. How do I get to ${meeting.name}?`);
    const machine = g.assets.find((a) => a.category === "machine") ?? g.assets.find((a) => a.category === "equipment");
    if (machine) out.push(`Where is the ${machine.type.replace(/_/g, " ")}?`);
    const lift = g.connectors.find((c) => c.kind === "lift") ?? g.connectors[0];
    if (lift) out.push(`${lift.name} is closed for maintenance. What changes?`);
    return out;
  }, [g]);
  const hereFloor = g?.spaces.find((s) => s.id === nav.here)?.floor_id ?? null;

  // Listen to speech start/end events to keep UI in sync
  useEffect(() => {
    const onStart = () => setIsAgentSpeaking(true);
    const onEnd = () => setIsAgentSpeaking(false);
    window.addEventListener("floorwise:speech-start", onStart);
    window.addEventListener("floorwise:speech-end", onEnd);
    return () => {
      window.removeEventListener("floorwise:speech-start", onStart);
      window.removeEventListener("floorwise:speech-end", onEnd);
    };
  }, []);

  const clearVoiceTour = useCallback(() => {
    voiceTourTimers.current.forEach(clearTimeout);
    voiceTourTimers.current = [];
    setVoiceFocusSpace(null);
    setVoiceHighlightId(null);
    setFocusRequest(null);
  }, []);

  const focusRoom = useCallback((space: Space) => {
    setSelected(space);
    nav.setFloorId(space.floor_id);
    setVoiceFocusSpace(space);
    setVoiceHighlightId(space.id);
    setFocusRequest({ id: space.id, revision: Date.now() });
  }, [nav.setFloorId]);

  const tourRooms = useCallback((matchedSpaces: Space[], totalDurationMs?: number) => {
    clearVoiceTour();
    if (!matchedSpaces.length) return;
    if (matchedSpaces.length === 1) {
      focusRoom(matchedSpaces[0]);
    } else {
      const durationMs = totalDurationMs ?? Math.min(9000, Math.max(3000, matchedSpaces.length * 2500));
      const interval = Math.max(1500, durationMs / matchedSpaces.length);
      matchedSpaces.forEach((space, idx) => {
        const timer = setTimeout(() => {
          focusRoom(space);
        }, idx * interval);
        voiceTourTimers.current.push(timer);
      });
    }
  }, [clearVoiceTour, focusRoom]);

  // Voice camera choreography: automatically zoom in to specific rooms mentioned
  // in speech, tour across multiple mentioned rooms, and dezoom back to the route/overview.
  useEffect(() => {
    const onChunk = (e: Event) => {
      if (!voiceOut && !voiceMode) return;
      if (!g) return;
      const custom = e as CustomEvent<{ index: number; text: string; audio?: HTMLAudioElement }>;
      const text = custom.detail?.text;
      if (!text) return;

      const matchedSpaces = findSpacesMentionedInText(text, g.spaces, nav.visualResult, nav.highlights);

      if (matchedSpaces.length > 0) {
        const audioDuration = custom.detail?.audio?.duration;
        const durationMs =
          audioDuration && isFinite(audioDuration) ? audioDuration * 1000 : Math.max(2500, text.length * 65);
        tourRooms(matchedSpaces, durationMs);
      } else {
        const isRouteChunk = /\b(?:route|directions|way to|head to|walk to|take the|path|exit)\b/i.test(text);
        if (isRouteChunk && nav.route?.polyline.length) {
          clearVoiceTour();
          nav.setFloorId(nav.route.polyline[0].floor_id);
        }
      }
    };

    const onSpeechEnd = () => {
      clearVoiceTour();
    };

    window.addEventListener("floorwise:speech-chunk", onChunk);
    window.addEventListener("floorwise:speech-end", onSpeechEnd);
    return () => {
      window.removeEventListener("floorwise:speech-chunk", onChunk);
      window.removeEventListener("floorwise:speech-end", onSpeechEnd);
      clearVoiceTour();
    };
  }, [voiceOut, voiceMode, g, nav.visualResult, nav.highlights, nav.route, nav.setFloorId, clearVoiceTour, tourRooms]);

  // Response camera zoom: when an agent reply arrives (for both text and voice modes),
  // automatically zoom and frame the room(s) discussed in the response.
  const lastProcessedReplyId = useRef<number | null>(null);

  useEffect(() => {
    if (!g) return;
    const lastMsg = nav.messages[nav.messages.length - 1];
    if (!lastMsg || lastMsg.role !== "agent" || lastMsg.id === lastProcessedReplyId.current) return;
    if (lastMsg.streaming || lastMsg.status === "streaming") return;

    lastProcessedReplyId.current = lastMsg.id;

    const matchedSpaces = findSpacesMentionedInText(lastMsg.text, g.spaces, nav.visualResult, nav.highlights);
    if (matchedSpaces.length > 0) {
      tourRooms(matchedSpaces);
    } else {
      const isRoute = /\b(?:route|directions|way to|head to|walk to|take the|path|exit)\b/i.test(lastMsg.text);
      if (isRoute && nav.route?.polyline.length) {
        clearVoiceTour();
        nav.setFloorId(nav.route.polyline[0].floor_id);
      }
    }
  }, [nav.messages, g, nav.visualResult, nav.highlights, nav.route, tourRooms, clearVoiceTour]);

  // Speak new agent replies and route overviews when voice output or voice mode is on.
  const spokenFor = useRef<string | null>(null);
  const lastSpokenMessageId = useRef<number | null>(null);

  useEffect(() => {
    if (!voiceOut && !voiceMode) {
      lastSpokenMessageId.current = null;
      return;
    }
    const lastMsg = nav.messages[nav.messages.length - 1];
    if (lastMsg && lastMsg.role === "agent" && lastMsg.id !== lastSpokenMessageId.current) {
      if (lastMsg.streaming || nav.busy) {
        if (audioStreamQueue.active) {
          setCurrentlySpeakingId(lastMsg.id);
        }
        return;
      }
      lastSpokenMessageId.current = lastMsg.id;
      if (audioStreamQueue.hadChunks) {
        if (audioStreamQueue.active) {
          setCurrentlySpeakingId(lastMsg.id);
        }
        audioStreamQueue.onEnd(() => {
          setCurrentlySpeakingId(null);
        });
      } else {
        setCurrentlySpeakingId(lastMsg.id);
        speak(lastMsg.text, () => {
          setCurrentlySpeakingId(null);
        });
      }
    }
  }, [nav.messages, nav.busy, voiceOut, voiceMode]);

  useEffect(() => {
    if (!voiceOut && !voiceMode) { spokenFor.current = null; return; }
    if (!nav.route || following) return;
    const key = `${nav.route.length_m}-${nav.route.stops.join()}`;
    if (spokenFor.current === key) return;
    spokenFor.current = key;
    // When a route is computed during an agent turn, the agent's reply already speaks the directions.
    if (nav.busy || audioStreamQueue.hadChunks || audioStreamQueue.active) return;
    speak(nav.route.guide.spoken);
  }, [nav.route, voiceOut, voiceMode, following, nav.busy]);

  useEffect(() => {
    if ((voiceOut || voiceMode) && following && steps[nav.activeStep]) {
      speak(steps[nav.activeStep].short ?? steps[nav.activeStep].text ?? "");
    }
    return () => {
      stopSpeaking();
    };
  }, [voiceOut, voiceMode, following, nav.activeStep]);

  const pins: Pin[] = useMemo(() => {
    if (!g) return [];
    const out: Pin[] = [];
    if(following&&previewPosition)out.push({id:"preview",at:[previewPosition.x,previewPosition.y],floor_id:previewPosition.floor_id,label:"Preview avatar (not your location)",tone:"info"});
    const at = (id: string) => g.spaces.find((s) => s.id === id);
    const here = nav.here ? at(nav.here) : null;
    if (here) out.push({ id: "here", at: here.anchor??centroid(here.polygon), floor_id: here.floor_id, label: `Starting from ${here.name}`, tone: "start" });
    if (nav.route?.polyline.length) {
      const first = nav.route.polyline[0], last = nav.route.polyline[nav.route.polyline.length - 1];
      if(nav.route.stops[0]!==nav.here)out.push({ id: "start", at: [first.x, first.y], floor_id: first.floor_id, label: "Route start", tone: "start" });
      out.push({ id: "end", at: [last.x, last.y], floor_id: last.floor_id, label: "Destination", tone: "end" });
      const step = steps[nav.activeStep];
      if (!following && step?.point && step.floor_id && nav.activeStep > 0 && step.kind !== "arrive")
        out.push({ id: "step", at: step.point, floor_id: step.floor_id, label: step.text, tone: "info", n: nav.activeStep });
    }
    return out;
  }, [g, nav.here, nav.route, nav.activeStep, steps,following,previewPosition]);

  const focusStep = (i: number) => {
    nav.setActiveStep(i);
    setSeekRequest(v=>v+1);
    const s = steps[i];
    if (s?.floor_id) nav.setFloorId(s.floor_id);
  };
  const activeHighlights = useMemo(() => {
    const set = new Set(nav.highlights);
    if (voiceHighlightId) set.add(voiceHighlightId);
    return set;
  }, [nav.highlights, voiceHighlightId]);

  const displayFloor = following && previewPosition ? previewPosition.floor_id : nav.floorId;
  const visualRooms = nav.visualResult?.entities.filter((e) => e.kind === "room") ?? [];
  const visualPrimary = (nav.visualResult?.measurements.primary_ids as string[] | undefined)?.[0];
  const visualRoom = g?.spaces.find((s) => s.id === (visualPrimary ?? (visualRooms.length === 1 ? visualRooms[0].id : null)));
  const visualAnchor = visualRoom ? (visualRoom.anchor ?? centroid(visualRoom.polygon)) : null;
  const voiceAnchor = voiceFocusSpace ? (voiceFocusSpace.anchor ?? centroid(voiceFocusSpace.polygon)) : null;
  const focused = g?.spaces.find((s) => s.id === focusRequest?.id);
  const focusPoint = following && previewPosition
    ? ([previewPosition.x, previewPosition.y] as [number, number])
    : voiceAnchor
    ? voiceAnchor
    : focused
    ? (focused.anchor ?? centroid(focused.polygon))
    : selected
    ? (selected.anchor ?? centroid(selected.polygon))
    : visualAnchor ?? (nav.route && steps[nav.activeStep]?.floor_id === nav.floorId ? steps[nav.activeStep]?.point ?? null : null);

  const handleToggleVoiceMode = useCallback(() => {
    setVoiceMode((prev) => {
      const next = !prev;
      if (next) setVoiceOut(true);
      else stopSpeaking();
      return next;
    });
  }, []);

  const handleSend = useCallback((text: string) => {
    clearVoiceTour();
    nav.ask(text, selected?.id);
    setSelected(null);
    setWeakOpen(false);
    setPhoneOpen(false);
    setToolsOpen(false);
  }, [nav.ask, selected?.id, clearVoiceTour]);

  const toggleMap=()=>{setQuestionOpen(false);setPhoneOpen(false);setWeakOpen(false);setSelected(null);setPlanExpanded(v=>!v);};
  if (!g) {
    return <div className="grid h-full place-items-center bg-ink font-sign text-xl text-concrete">{nav.notice ?? "Loading building…"}</div>;
  }

  return (
    <div className={`navigator-shell flex h-full flex-col lg:flex-row ${!nav.route && nav.messages.length === 0 ? "first-use" : ""} ${stageExpanded?"stage-expanded":""} ${following?"guiding":""} ${questionOpen?"question-open":""} ${planExpanded?"map-open":""} ${weakOpen?"analysis-open":""}`}>
      {/* ---------- sign column ---------- */}
      <aside className="order-2 flex min-h-0 flex-1 flex-col navigation-panel bg-ink text-white lg:order-1 lg:w-[370px] lg:flex-none">
        <header className="flex items-center gap-2 border-b border-ink-2 px-4 py-3">
          <BuildingPicker buildings={buildings} value={buildingId} onChange={(b) => setParams({ building: b })} name={g.building.name} />
          <button onClick={() => setBuildingImport(true)} className="ml-auto text-sm text-concrete">Import plan</button>
        </header>

        <div className="flex flex-wrap items-center gap-2 border-b border-ink-2 px-4 py-2.5">
          <Toggle on={nav.stepFree} onClick={() => nav.setStepFree(!nav.stepFree)} icon="wheelchair" label="Step-free" tone="escape" />
          <Toggle on={voiceOut && !voiceMode} onClick={() => { setVoiceOut(!voiceOut); if (voiceOut) stopSpeaking(); }} icon="speaker" label="Read aloud" tone="mark" />
          <Toggle on={voiceMode} onClick={() => {
            const next = !voiceMode;
            setVoiceMode(next);
            if (next) setVoiceOut(true); else stopSpeaking();
          }} icon="mic" label={voiceMode ? "Voice mode (ON)" : "Voice only"} tone="mark" />
        </div>
        <div className="border-b border-ink-2 px-4 py-2.5">
          <button onClick={() => setPicking(!picking)} aria-expanded={picking}
            className="flex w-full items-center gap-2 text-left text-[15px] hover:text-mark">
            <Pictogram name="here" size={18} className="shrink-0 text-escape" />
            <span className="min-w-0 flex-1 truncate">
              {nav.here ? <>Starting from <b className="font-semibold">{labelOf(g, nav.here)}</b></> : "Where are you? Choose a start"}
            </span>
            <span className="shrink-0 text-sm text-ink-4 underline underline-offset-4">change</span>
          </button>
          {nav.here && <p className="mt-1 text-[13px] text-ink-4">{nav.hereSource === "default" ? "Entrance used as start. Change it if you’re elsewhere." : nav.hereSource === "link" ? "Start supplied by link. Change it if you’re elsewhere." : "Start set by you. Location is not tracked."}</p>}
          {picking && (
            <StartPicker geometry={g} onPick={(id) => { nav.setHere(id); const room=g.spaces.find(s=>s.id===id);if(room)nav.setFloorId(room.floor_id);setPicking(false); nav.setNotice(`Location set: ${labelOf(g,id)}. Your green marker is set manually.`); }} />
          )}
        </div>

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {nav.visualResult&&nav.sessionId&&<VisualAnswer result={nav.visualResult} total={nav.visualResult.total_rows} sessionId={nav.sessionId} onClose={()=>nav.setVisualResult(null)} onPick={id=>{const room=g.spaces.find(s=>s.id===id)??g.spaces.find(s=>s.id===g.assets.find(a=>a.id===id)?.space_id);if(room)focusRoom(room);}} onFloor={nav.setFloorId} geometry={g}/> }
          {nav.route && !nav.visualResult && (
            <RouteSign route={nav.route} meta={nav.routeMeta} stepFree={nav.route.constraints.includes("step-free")}
              active={nav.activeStep} onStep={focusStep} onClear={nav.clearRoute} onStepMode={() => { setView("guide");setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setStageExpanded(false); nav.setVisualResult(null); nav.setActiveStep(0); setSelected(null); }} floors={g.floors} />
          )}
          {!nav.route && nav.messages.length === 0 && (
            <Welcome categories={cats} onPick={(q) => nav.goTo(q)} onAsk={nav.ask} hasHere={!!nav.here} buildingName={g.building.name} examples={examples} />
          )}
          <Conversation
            onResult={(result) => {
              nav.setVisualResult(result);
              nav.setHighlights(new Set(result.entities.map((e) => e.id)));
            }}
            onRerun={(q) => nav.ask(q)}
            busyLabel={nav.busyLabel}
            geometry={g}
            onRoom={(id) => {
              const room = g.spaces.find((s) => s.id === id);
              if (room) {
                setView("3d");
                setQuestionOpen(false);
                focusRoom(room);
              }
            }}
            messages={nav.messages}
            busy={nav.busy}
            currentlySpeakingId={currentlySpeakingId}
            onSpeakMessage={(id, text) => {
              if (currentlySpeakingId === id) {
                stopSpeaking();
                setCurrentlySpeakingId(null);
              } else {
                setCurrentlySpeakingId(id);
                speak(text, () => setCurrentlySpeakingId(null));
              }
            }}
            onOption={(id, purpose) => (purpose === "choice" ? nav.ask(id) : nav.goTo(id))}
            onDecide={nav.decideChange}
          />
        </div>

        {nav.route && cats.length > 0 && (
          <div className="flex gap-1.5 overflow-x-auto border-t border-ink-2 px-4 py-2 scroll-thin">
            {cats.map((c) => (
              <button key={c.key} onClick={() => nav.goTo(c.query)} className="flex shrink-0 items-center gap-1.5 border border-ink-3 px-2.5 py-1 font-sign text-sm hover:border-mark">
                <Pictogram name={c.icon} size={15} /> {c.label}
              </button>
            ))}
          </div>
        )}
        {nav.turnUsage&&<div className="turn-usage" role="status">{nav.turnUsage.dispatch==="deterministic"?"Computed locally · no model tokens":`${nav.turnUsage.dispatch==="parser"?"Language parsed":"Agent response"} · ${Number(nav.turnUsage.input_tokens??0)+Number(nav.turnUsage.output_tokens??0)+Number(nav.turnUsage.cache_read_input_tokens??0)+Number(nav.turnUsage.cache_creation_input_tokens??0)} model tokens`}{typeof nav.turnUsage.estimated_cost_usd==="number"&&nav.turnUsage.dispatch!=="deterministic"?` · est. $${nav.turnUsage.estimated_cost_usd.toFixed(4)}`:""}{typeof nav.turnUsage.latency_ms==="number"?` · ${(nav.turnUsage.latency_ms/1000).toFixed(1)} s`:""}</div>}
        <Composer
          onStop={nav.stop}
          busy={nav.busy}
          voiceMode={voiceMode}
          onToggleVoiceMode={handleToggleVoiceMode}
          isSpeaking={isAgentSpeaking}
          onSend={handleSend}
        />
      </aside>

      <main className="model-panel relative order-1 flex h-[46vh] shrink-0 lg:order-2 lg:h-auto lg:flex-1">
        <div className="model-toolbar">
          <div className="mode-switch" aria-label="View mode">
            {following?<button aria-label="3D" onClick={()=>{setView("3d");setQuestionOpen(false);}}>Back to building</button>:<>
            <button aria-pressed={view === "3d"} onClick={() => setView("3d")}>3D</button>
            <button aria-pressed={view === "2d"} onClick={() => setView("2d")}>Floor plan</button>
            <button disabled={!nav.route || nav.route.preview_available === false} aria-pressed={following} onClick={() => {setView("guide");setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setStageExpanded(false);nav.setVisualResult(null);setSelected(null);}}>Guide me</button>
            <button className="stage-toggle" aria-label={stageExpanded?"Shrink building view":"Expand building view"} onClick={()=>{if(stageExpanded)setPlanExpanded(false);setStageExpanded(!stageExpanded);}}>{stageExpanded?"↙":"↗"}</button>
            </>}
          </div>
          <div className="model-actions">
            <button aria-label="Show map" aria-pressed={planExpanded} onClick={toggleMap}><Pictogram name="map" size={18}/><span>Map</span></button>
            {following&&<button aria-expanded={questionOpen} onClick={()=>{setQuestionOpen(!questionOpen);setPlanExpanded(false);}}>Ask</button>}
            <details ref={toolsRef} className="building-tools" open={toolsOpen}>
              <summary aria-label="Building tools" title="Building tools" onClick={e=>{e.preventDefault();setToolsOpen(v=>!v);}}>Tools</summary><div className="building-tools-content">
            {!following&&<button aria-pressed={scenarioOpen} onClick={()=>{setScenarioOpen(v=>!v);setToolsOpen(false);setWeakOpen(false);setPlanExpanded(false);setSelected(null);setPhoneOpen(false);}}>Scenarios</button>}
            <CompanionControl buildingId={buildingId} steps={steps} index={nav.activeStep} routeId={companionRouteId} open={phoneOpen} onToggle={()=>{setPhoneOpen(v=>!v);setToolsOpen(false);setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setSelected(null);}}
              onStep={action=>{if(!nav.route)return;if(action==="repeat"){speak(steps[nav.activeStep]?.text??"");return;}if(!following)setView("guide");focusStep(Math.max(0,Math.min(steps.length-1,nav.activeStep+(action==="next"?1:-1))));}}
              onLook={(yaw,pitch)=>{if(view==="2d")setView("3d");setLookOffset(v=>({yaw:((v.yaw+yaw+540)%360)-180,pitch:Math.max(-55,Math.min(55,v.pitch+pitch))}));}}
              onRecenter={()=>setLookOffset({yaw:0,pitch:0})}/>
            {view === "3d" && <><select aria-label="Visible floors" value={scope} onChange={e=>{setScope(e.target.value as typeof scope);if(compact)setToolsOpen(false);}}><option value="current">Current floor</option><option value="route" disabled={!nav.route}>Route floors</option><option value="building">Whole building</option></select>{scope!=="current"&&<button aria-pressed={exploded} onClick={()=>setExploded(!exploded)}>{exploded?"Exploded":"Assembled"}</button>}</>}
            {following?<button aria-label="Read aloud" aria-pressed={voiceOut} onClick={()=>{setVoiceOut(!voiceOut);if(voiceOut){stopSpeaking();clearVoiceTour();}}}><Pictogram name="speaker" size={18}/>Read aloud</button>:<><button aria-pressed={scenarioOpen} onClick={()=>{setScenarioOpen(v=>!v);setWeakOpen(false);setToolsOpen(false);setPlanExpanded(false);}}>Fire / evacuation scenario</button><button disabled={nav.busy} onClick={()=>{setWeakOpen(v=>!v);setToolsOpen(false);setPlanExpanded(false);setSelected(null);if(!nav.weakPoints.length)nav.inspectWeakPoints();}}>Stress test</button><Link to="/lab">Evidence</Link></>}
              </div>
            </details>
          </div>
        </div>
        <div className="floor-selector"><FloorRail floors={g.floors} active={displayFloor} route={nav.route} onPick={id=>{if(following)setView("3d");nav.setFloorId(id);}} here={hereFloor} /></div>
        <div className="model-viewport">
          <ErrorBoundary key={`${g.building.id}-${view==="2d"?"plan":"scene"}`} label="The building view needs recovery">
            {view === "2d" ? <PlanView geometry={g} floorId={displayFloor} route={nav.visualResult&&!following?null:nav.route} highlights={activeHighlights} closed={nav.closed} visualResult={nav.visualResult}
              pins={pins} previewDoor={nav.previewDoor} selected={voiceFocusSpace?.id ?? selected?.id} scenario={scenarioMark} focus={focusPoint} onSpaceClick={selectSpace} /> :
              <Suspense fallback={<div className="recovery">Preparing the building model...</div>}>
                <Building3D geometry={g} floorId={nav.floorId} route={nav.visualResult&&!following?null:nav.route} previousRoute={nav.visualResult?null:nav.previousRoute} highlights={activeHighlights} hazard={scenarioMark?.hazard} zones={scenarioZones}
                  closed={nav.closed} previewDoor={nav.previewDoor} showAll={false} scope={scope} exploded={exploded} follow={following} previewMode={view==="follow"} activeStep={nav.activeStep} seekRequest={seekRequest} here={nav.here} selected={voiceFocusSpace?.id ?? selected?.id} visualResult={nav.visualResult} heading={heading?Number(heading):undefined} onPosition={p=>{setPreviewPosition(old=>old&&old.x===p.x&&old.y===p.y&&old.floor_id===p.floor_id?old:p);}} focusRequest={focusRequest} onRepeat={()=>speak(steps[nav.activeStep]?.short??steps[nav.activeStep]?.text??"")} onFinish={()=>{setView("3d");setQuestionOpen(false);setPlanExpanded(false);}} onPreview={()=>{stopSpeaking();setVoiceOut(false);setView("follow");}}
                  onStep={nav.setActiveStep} onSpaceClick={selectSpace} lookOffset={lookOffset}/>
              </Suspense>}
          </ErrorBoundary>
        </div>
        {view!=="2d"&&planExpanded&&<section className="map-drawer" aria-label="Linked floor plan">
          <header><span>{g.floors.find(f=>f.id===displayFloor)?.name}</span><button aria-label="Close map" onClick={()=>setPlanExpanded(false)}><Pictogram name="close" size={18}/></button></header>
          <PlanView geometry={g} floorId={displayFloor} route={nav.visualResult&&!following?null:nav.route} highlights={activeHighlights} closed={nav.closed} visualResult={nav.visualResult} pins={pins} selected={voiceFocusSpace?.id ?? selected?.id} scenario={scenarioMark} focus={focusPoint} focusKey={`${nav.route?.stops.join()}-${focusRequest?.revision}-${nav.visualResult?.id}`} followPosition={following} onSpaceClick={selectSpace} compact/>
        </section>}
        {!nav.notice && nav.route?.warnings?.length ? <div className="model-notice" role="status">{nav.route.warnings.join(" ")}</div> : null}
        {nav.notice && <div role="status" className="model-notice"><span>{nav.notice}</span><button aria-label="Dismiss" onClick={() => nav.setNotice(null)}>×</button></div>}
        {weakOpen&&!following&&!scenarioOpen&&<section className="stress-drawer" aria-label="Building stress test">
          <header><div><span>What-if analysis</span><h2>Exit access under closure</h2></div><button aria-label="Close stress test" onClick={()=>setWeakOpen(false)}><Pictogram name="close"/></button></header>
          <p>Each result closes one connector independently and checks step-free routes to mapped exits.</p>
          {nav.busy?<p role="status">Checking connector closures…</p>:nav.weakPoints.length?nav.weakPoints.map((item,i)=><button className="stress-result" key={i} onClick={()=>{nav.setHighlights(new Set(item.room_ids));const room=g.spaces.find(s=>s.id===item.room_ids[0]);if(room)nav.setFloorId(room.floor_id);}}>
            <span><Pictogram name={item.kind==="lift"?"lift":"stairs"}/><b>{item.name}</b></span><strong>{item.rooms_lost}<small> / {item.of_rooms} rooms</small></strong><span>would lose step-free exit access</span><span className="stress-inspect">Show affected rooms</span>
          </button>):<p>No individual connector closure disconnects mapped rooms for this analysis.</p>}
          <details><summary>Evidence and assumptions</summary><p>Computed by removing each connector from the route graph and comparing exit reachability. This is a single-failure sensitivity check, not a fire or crowd-capacity simulation. Occupancy and door throughput are not supplied.</p></details>
          <button className="stress-rerun" disabled={nav.busy} onClick={nav.inspectWeakPoints}>Run again</button>
        </section>}
        {scenarioOpen&&!following&&nav.sessionId&&<ScenarioPanel onBeat={(say,id)=>{setFocusRequest(r=>({id,revision:(r?.revision??0)+1}));if(voiceOut&&!window.speechSynthesis?.speaking)speak(say);}} incoming={nav.scenarioIn} replayCmd={nav.replayCmd} geometry={g} sessionId={nav.sessionId} selected={selected} onClose={()=>{setScenarioOpen(false);setScenarioMark(null);nav.clearScenarioEvents();nav.setHighlights(new Set());}} onHighlight={nav.setHighlights} onScenario={setScenarioMark} onFloor={nav.setFloorId} apply={nav.applyEvents}/>}
        {selected && !following && !scenarioOpen && <RoomCard space={selected} building={g} onClose={() => setSelected(null)} closed={nav.closed}
          onHere={() => { nav.setHere(selected.id); nav.setFloorId(selected.floor_id); setSelected(null); nav.setNotice(`Location set: ${selected.name}. Your green marker is set manually.`); }}
          onGo={() => { nav.goTo(selected.id); setSelected(null); }} onToggleClosed={nav.toggleClosed} onFocus={()=>focusRoom(selected)} />}
        {stepMode && nav.route && <StepMode steps={steps} index={nav.activeStep} onIndex={focusStep} onClose={() => {setStepMode(false);stopSpeaking();}} />}
      </main>
      {buildingImport && <BuildDialog onClose={() => setBuildingImport(false)} onBuilt={id => {setBuildingImport(false);setParams({building:id});api.buildings().then(setBuildings);}} />}

    </div>
  );
}

function VisualAnswer({result,total,sessionId,onClose,onPick,onFloor,geometry}:{result:VisualResult;total:number;sessionId:string;onClose:()=>void;onPick:(id:string)=>void;onFloor:(id:string)=>void;geometry:NonNullable<ReturnType<typeof useNavigator>["geometry"]>}) {
  const grouped=!!result.measurements.grouped;
  const [rows,setRows]=useState<Record<string,unknown>[]>([]),[offset,setOffset]=useState(0),[error,setError]=useState(''),[pageTotal,setPageTotal]=useState(total),[room,setRoom]=useState('');
  useEffect(()=>{setOffset(0);setRows([]);setRoom('');},[result.id]);
  useEffect(()=>{let current=true;setError('');setRows([]);api.resultPage(sessionId,result.id,offset,grouped?(room?'items':'rooms'):'default',room).then(page=>{if(current){setRows(page.rows);setPageTotal(page.total);}}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[sessionId,result.id,offset,grouped,room]);
  return <section className="visual-answer" aria-label="Visual answer">
    <header><span>{grouped?'Equipment by room':result.kind.replaceAll('_',' ')}</span><button aria-label="Close visual answer" onClick={onClose}>Close</button></header>
    <h2>{result.title}</h2><p className="result-provenance">{result.provenance}</p>
    {grouped&&<p className="result-measure"><b>{String(result.measurements.item_count)} items</b><span>in {String(result.measurements.room_count)} rooms</span></p>}
    {room&&<button onClick={()=>{setRoom('');setOffset(0);}}>Back to rooms</button>}
    <div className="result-floors">{result.floor_ids.map(id=><button key={id} onClick={()=>onFloor(id)}>{geometry.floors.find(f=>f.id===id)?.name??id}</button>)}</div>
    {!grouped&&Object.entries(result.measurements).filter(([,v])=>typeof v==='number').map(([key,value])=><p key={key} className="result-measure"><span>{key.replace(/_m2$|_m$/,' ').replaceAll('_',' ')}</span><b>{String(value)}{key.includes('m2')?' m²':key.endsWith('_m')?' m':''}</b></p>)}
    {result.warnings.map((warning,i)=><p key={i}>{warning}</p>)}
    {Array.isArray(result.measurements.assumptions)&&<details><summary>Inputs, method and assumptions</summary><p>{String(result.measurements.method??'')}</p><ul>{result.measurements.assumptions.map((a,i)=><li key={i}>{String(a)}</li>)}</ul></details>}
    {error&&<p role="alert">{error.includes('404')?'This earlier result expired. Use Run again on its chat card.':error}</p>}
    {!rows.length&&pageTotal>0&&!error&&<p role="status">Loading results…</p>}
    <ol className="result-list">{rows.map((row,i)=><li key={String(row.id??i)}><button onClick={()=>geometry.floors.some(f=>f.id===row.id)?onFloor(String(row.id)):onPick(String(row.id))} disabled={!geometry.spaces.some(s=>s.id===row.id)&&!geometry.assets.some(a=>a.id===row.id)&&!geometry.floors.some(f=>f.id===row.id)}><span>{String(row.label??row.name??row.id)}</span><b>{row.count!==undefined?String(row.count):row.area_m2!==undefined?`${row.area_m2} m²`:row.overlap_m2!==undefined?`${row.overlap_m2} m² overlap`:row.reachable!==undefined?(row.reachable?'Reachable':'Unavailable'):row.before_m!==undefined?`${row.before_m} → ${row.after_m} m`:'Show'}</b></button>{grouped&&!room&&<button aria-label={`Items in ${row.label}`} onClick={()=>{setRoom(String(row.id));setOffset(0);}}>Items</button>}</li>)}</ol>
    {pageTotal>25&&<nav aria-label="Result pages"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button><span>{offset+1}–{Math.min(offset+25,pageTotal)} of {pageTotal}</span><button disabled={offset+25>=pageTotal} onClick={()=>setOffset(offset+25)}>Next</button></nav>}
    <p className="result-provenance">{result.entities.length} matching entities across {result.floor_ids.length} floors. Lists are paged; map matches are complete.</p>
  </section>;
}

function BuildingPicker({ buildings, value, onChange, name }: { buildings: BuildingRow[]; value: string; onChange: (b: string) => void; name: string }) {
  const groups = useMemo(() => {
    const out: Record<string, BuildingRow[]> = {};
    for (const b of buildings) (out[b.split] ??= []).push(b);
    return out;
  }, [buildings]);
  return (
    <label className="flex min-w-0 flex-col">
      <span className="sr-only">Building</span>
      <span title={name} className="building-title font-sign text-[22px] font-bold leading-tight tracking-tight">{name}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Change building"
        className="-ml-1 mt-0.5 w-[150px] cursor-pointer appearance-none bg-transparent text-sm text-ink-4 hover:text-white focus:text-white">
        <option value={value} hidden>Change building ▾</option>
        {Object.entries(groups).map(([split, rows]) => (
          <optgroup key={split} label={split}>
            {rows.map((b) => <option key={b.building_id} value={b.building_id} className="text-ink">{b.name} · {b.building_id}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

function Toggle({ on, onClick, icon, label, tone }: { on: boolean; onClick: () => void; icon: string; label: string; tone: "escape" | "mark" }) {
  const onClass = tone === "escape" ? "bg-escape border-escape text-white" : "bg-mark border-mark text-ink";
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={`flex items-center gap-1.5 border px-2.5 py-1.5 font-sign text-[15px] font-semibold ${on ? onClass : "border-ink-3 text-concrete hover:border-white"}`}>
      <Pictogram name={icon} size={17} /> {label}
    </button>
  );
}

function Welcome({ categories: cats, onPick, onAsk, hasHere, buildingName, examples }: {
  categories: { key: string; label: string; query: string; icon: string }[];
  onPick: (q: string) => void; onAsk: (t: string) => void; hasHere: boolean; buildingName: string; examples: string[];
}) {
  return (
    <section className="welcome-panel px-5 pb-2 pt-7">
      <h1 className="font-sign text-[34px] font-bold leading-[1.05]">Know your building.<br />Find your way.</h1>
      <p className="mt-2 max-w-[34ch] text-[15px] text-ink-4">
        {hasHere ? "Pick a place, or just ask." : `Explore ${buildingName}, or describe where you want to go.`}
      </p>
      {cats.length > 0 && (
        <div className="destination-shortcuts mt-5 grid grid-cols-3 gap-px bg-ink-2">
          {cats.slice(0, 6).map((c) => (
            <button key={c.key} onClick={() => onPick(c.query)}
              className="flex flex-col items-start gap-3 bg-ink px-3 py-3 text-left hover:bg-ink-2">
              <Pictogram name={c.icon} size={26} className="text-mark" />
              <span className="font-sign text-[16px] font-semibold">{c.label}</span>
            </button>
          ))}
        </div>
      )}
      <details className="example-requests mt-5"><summary className="cursor-pointer font-sign text-sm text-ink-4">Things you can say</summary>
      <ul className="mt-2 space-y-1.5">
        {examples.map((t) => (
          <li key={t}><button onClick={() => onAsk(t)} className="text-left text-[15px] text-concrete underline decoration-ink-3 underline-offset-4 hover:decoration-mark">“{t}”</button></li>
        ))}
      </ul></details>
    </section>
  );
}

function RouteSign({ route, meta, stepFree, active, onStep, onClear, onStepMode, floors }: {
  route: NonNullable<ReturnType<typeof useNavigator>["route"]>; meta: ReturnType<typeof useNavigator>["routeMeta"]; stepFree: boolean;
  active: number; onStep: (i: number) => void; onClear: () => void; onStepMode: () => void; floors: { id: string; name: string }[];
}) {
  const steps = route.guide.steps;
  const floorChanges = steps.filter((s) => s.kind === "floor").length;
  const outside = steps.some((s) => s.kind === "outside");
  const minutes = Math.max(1, Math.round((route.walk_m ?? route.length_m) / 1.2 / 60) + floorChanges);
  return (
    <section aria-label="Route">
      <div className="border-b-4 border-mark bg-ink-2 px-4 pb-3 pt-4">
        <div className="flex items-start gap-3">
          <div className="grid h-12 w-12 shrink-0 place-items-center bg-mark text-ink"><Pictogram name="arrive" size={28} /></div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink-4">from {meta?.from ?? "start"}</p>
            <h2 className="font-sign text-[26px] font-bold leading-tight">{meta?.to ?? "Destination"}</h2>
          </div>
          <button onClick={onClear} className="text-sm text-ink-4 hover:text-white" aria-label="Clear route"><Pictogram name="close" size={20} /></button>
        </div>
        <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-sign text-[15px]">
          <span className="font-semibold">{Math.round(route.walk_m ?? route.length_m)} {route.walk_m==null?"route-model m":"m walk"}</span>
          {route.walk_m!=null&&<span>about {minutes} min</span>}
          {floorChanges > 0 && <span>{floorChanges} floor change{floorChanges > 1 ? "s" : ""}</span>}
          {stepFree && <span className="flex items-center gap-1 text-[#7fd4a8]"><Pictogram name="wheelchair" size={15} /> step-free</span>}
          {route.constraints.filter((c) => c !== "step-free").map((c) => <span key={c} className="text-mark">{c}</span>)}
        </p>
        {outside && <p className="mt-1.5 text-sm text-mark">No indoor connection: this route goes outside between two entrances.</p>}
        {meta?.alternatives?.length ? (
          <p className="mt-1.5 text-sm text-ink-4">Nearest match. Also: {meta.alternatives.map((a) => `${a.room} (${a.walk_m} m)`).join(", ")}</p>
        ) : null}
      </div>
      <div className="current-decision"><span>Decision {active+1} of {steps.length}</span><p>{steps[active]?.text}</p></div>
      <details className="route-itinerary"><summary>All {steps.length} instructions</summary><ol className="divide-y divide-ink-2">
        {steps.map((s, i) => (
          <StepRow key={i} step={s} index={i} active={i === active} onClick={() => onStep(i)} floorName={floors.find((f) => f.id === s.floor_id)?.name} />
        ))}
      </ol></details>
      <div className="route-start-actions flex gap-2 px-4 py-3">
        <button disabled={route.preview_available === false} onClick={onStepMode} className="flex-1 bg-mark py-2.5 font-sign text-[17px] font-bold text-ink hover:brightness-95">{route.preview_available === false ? "Preview unavailable: check geometry" : "Guide me step by step"}</button>
      </div>
    </section>
  );
}

function StepRow({ step, index, active, onClick, floorName }: { step: GuideStep; index: number; active: boolean; onClick: () => void; floorName?: string }) {
  const isFloor = step.kind === "floor";
  return (
    <li>
      <button onClick={onClick} aria-current={active ? "step" : undefined}
        className={`flex w-full gap-3 px-4 py-3 text-left ${active ? "bg-ink-2" : "hover:bg-ink-2/60"} ${isFloor ? "border-l-4 border-mark" : "border-l-4 border-transparent"}`}>
        <span className={`grid h-9 w-9 shrink-0 place-items-center ${step.kind === "arrive" ? "bg-mark text-ink" : isFloor ? "bg-white text-ink" : "border border-ink-3 text-white"}`}>
          <Pictogram name={step.icon} size={20} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[15.5px] leading-snug">{step.text}</span>
          {(step.metres > 0 || isFloor) && (
            <span className="mt-0.5 block text-[13px] text-ink-4">{index > 0 && step.metres > 0 ? `${Math.round(step.metres)} m` : ""}{isFloor && floorName ? ` · now on ${floorName}` : ""}</span>
          )}
        </span>
      </button>
    </li>
  );
}

function Conversation({
  messages,
  busy,
  onOption,
  onDecide,
  geometry,
  onRoom,
  busyLabel,
  onResult,
  onRerun,
  currentlySpeakingId,
  onSpeakMessage,
}: {
  busyLabel?: string;
  onResult: (r: VisualResult & { total_rows: number }) => void;
  onRerun: (q: string) => void;
  geometry: NonNullable<ReturnType<typeof useNavigator>["geometry"]>;
  onRoom: (id: string) => void;
  messages: Message[];
  busy: boolean;
  onOption: (id: string, purpose?: string) => void;
  onDecide: (m: Extract<Message, { role: "change" }>, ok: boolean) => void;
  currentlySpeakingId?: number | null;
  onSpeakMessage?: (id: number, text: string) => void;
}) {
  const [history,setHistory]=useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { const panel = end.current?.parentElement; if (panel && panel.scrollHeight-panel.scrollTop-panel.clientHeight<100) panel.scrollTop = panel.scrollHeight; }, [messages, busy]);
  const turns=useMemo(()=>{
    const turns:Message[][]=[];
    messages.forEach(m=>{if(m.role==="user"||!turns.length)turns.push([]);turns[turns.length-1].push(m);});
    return turns;
  },[messages]);
  const shown=history?turns:turns.slice(-2);
  const visible=shown.flatMap(turn=>[
    ...turn.filter(m=>m.role==="user"),
    {role:"trace" as const,id:-(turn[0]?.id??1),activities:turn.filter((m):m is Extract<Message,{role:"activity"}>=>m.role==="activity"),busy:busy&&turn===turns.at(-1)},
    ...turn.filter(m=>m.role!=="activity"&&m.role!=="user")
  ]);
  if (!messages.length && !busy) return null;
  return (
    <section aria-label="Conversation" aria-live="polite" style={{maxHeight:320,overflowY:"auto"}} className="space-y-3 px-4 py-4">
      {turns.length>2&&<button className="conversation-history" aria-expanded={history} onClick={()=>setHistory(!history)}>{history?"Collapse history":`Earlier conversation (${turns.length-2} turns)`}</button>}
      {visible.map((m) => {
        if(m.role==="trace")return <ToolTrace key={m.id} activities={m.activities} busy={m.busy}/>;
        if(m.role==='result')return <div key={m.id} className="answer-reference"><span>{m.text}</span><button onClick={()=>onResult?.(m.result)}>View results</button>{m.query&&<button onClick={()=>onRerun?.(m.query!)} disabled={busy}>Run again</button>}</div>;
        if (m.role === "user") return <p key={m.id} className="ml-10 border-r-4 border-concrete pr-3 text-right text-[15.5px] text-concrete">{m.text}</p>;
        if (m.role === "error") return <p key={m.id} className="border-l-4 border-signal bg-ink-2 px-3 py-2 text-[14.5px]">{m.text}</p>;
        if (m.role === "options")
          return (
            <div key={m.id}>
              <p className="text-[15.5px]">{m.text}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {m.options.map((o, i) => (
                  <button key={o.id} onClick={() => onOption(o.id, m.purpose)} className="flex items-center gap-2 border border-white px-3 py-1.5 font-sign text-[15px] hover:bg-white hover:text-ink">
                    <span className="grid h-5 w-5 place-items-center bg-mandatory text-[12px] font-bold text-white">{i + 1}</span>{o.label}
                  </button>
                ))}
              </div>
            </div>
          );
        if (m.role === "change")
          return (
            <div key={m.id} className="border-2 border-dashed border-mandatory p-3">
              <p className="font-sign text-sm font-semibold text-[#8cb8e6]">Proposed change</p>
              <p className="mt-1 text-[15px]">{m.text}</p>
              {m.state === "pending" ? (
                <div className="mt-3 flex gap-2">
                  <button onClick={() => onDecide(m, true)} className="bg-white px-3 py-1.5 font-sign font-bold text-ink">Apply to model</button>
                  <button onClick={() => onDecide(m, false)} className="border border-ink-3 px-3 py-1.5 font-sign">Discard</button>
                </div>
              ) : <p className="mt-2 text-sm text-ink-4">{m.state === "applied" ? "Applied." : "Discarded."}</p>}
            </div>
          );
        if (m.role === "agent") {
          const isThisPlaying = currentlySpeakingId === m.id;
          return (
            <div key={m.id} className="space-y-1.5 border-l-2 border-mark/80 bg-ink-2/40 py-2 pl-3 pr-2 text-[15.5px] leading-relaxed">
              <div className="flex items-center justify-between gap-2">
                <span className="font-sign text-xs font-semibold uppercase tracking-wider text-concrete">
                  Agent response
                </span>
                {onSpeakMessage && (
                  <button
                    type="button"
                    onClick={() => onSpeakMessage(m.id, m.text)}
                    className={`flex items-center gap-1.5 px-2 py-0.5 font-sign text-xs transition-colors rounded ${
                      isThisPlaying
                        ? "bg-mark text-ink font-bold animate-pulse"
                        : "border border-ink-3 text-concrete hover:border-white hover:text-white"
                    }`}
                    aria-label={isThisPlaying ? "Stop reading" : "Read answer aloud"}
                  >
                    <Pictogram name="speaker" size={13} />
                    <span>{isThisPlaying ? "Stop" : "Read aloud"}</span>
                  </button>
                )}
              </div>
              <div className="space-y-1.5 text-white">
                {m.status === "interrupted" && <p role="status" className="text-signal text-sm">Answer interrupted. Computed results remain available.</p>}
                {m.text.split("\n").filter(Boolean).map((line, i) => (
                  <p key={i}>
                    <RoomText text={line.replace(/\*\*/g, "")} spaces={geometry.spaces} onRoom={onRoom} />
                  </p>
                ))}
                {(m.streaming || m.status === "streaming") && (
                  <span className="inline-block h-4 w-1.5 animate-pulse bg-mark ml-1 align-middle" />
                )}
              </div>
            </div>
          );
        }
        return null;
      })}
      {busy && <p className="flex items-center gap-2 text-[13px] text-ink-4"><span className="h-1.5 w-1.5 animate-pulse bg-mark" />{busyLabel}</p>}
      <div ref={end} />
    </section>
  );
}

function Composer({
  busy,
  onSend,
  onStop,
  voiceMode,
  onToggleVoiceMode,
  isSpeaking,
}: {
  busy: boolean;
  onSend: (t: string) => void;
  onStop?: () => void;
  voiceMode: boolean;
  onToggleVoiceMode: () => void;
  isSpeaking: boolean;
}) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const stopListening = useRef<((submitIfText?: boolean) => void) | null>(null);

  const stopListeningSession = useCallback((submitIfText = false) => {
    if (stopListening.current) {
      const abortFn = stopListening.current;
      stopListening.current = null;
      abortFn(submitIfText);
    }
    setListening(false);
  }, []);

  useEffect(() => () => { stopListeningSession(false); }, [stopListeningSession]);

  const submit = useCallback((value: string) => {
    const t = value.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }, [busy, onSend]);

  const startListeningSession = useCallback(() => {
    if (!canListen()) {
      setVoiceError("Voice input is not supported in this browser.");
      return;
    }
    stopSpeaking();
    window.dispatchEvent(new Event("floorwise:voice-start"));
    setVoiceError("");
    setListening(true);
    stopListening.current = listen(
      setText,
      (t) => {
        setListening(false);
        submit(t);
      },
      () => setListening(false),
      (err) => {
        setListening(false);
        setVoiceError(err);
      }
    );
  }, [submit]);

  // Hands-free continuous loop when voiceMode is active
  useEffect(() => {
    if (!voiceMode) return;
    if (busy || isSpeaking) {
      if (listening) {
        stopListeningSession(false);
      }
      return;
    }
    const timer = setTimeout(() => {
      if (!listening && !busy && !isSpeaking) {
        startListeningSession();
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [voiceMode, busy, isSpeaking, listening, startListeningSession, stopListeningSession]);

  if (voiceMode) {
    return (
      <div className="relative border-t border-ink-2 bg-ink-2 p-3" role="region" aria-label="Voice interaction">
        {voiceError && (
          <p role="status" className="mb-2 border border-signal bg-signal/20 p-2 text-xs text-signal">
            {voiceError}
          </p>
        )}
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => {
              if (isSpeaking) {
                stopSpeaking();
              } else if (listening) {
                stopListeningSession(true);
              } else if (!busy) {
                startListeningSession();
              }
            }}
            aria-label={isSpeaking ? "Interrupt agent" : listening ? "Done speaking" : "Start speaking"}
            className={`grid h-12 w-12 shrink-0 place-items-center rounded-sm transition-all ${
              isSpeaking
                ? "animate-pulse bg-mark text-ink"
                : busy
                ? "bg-ink-3 text-concrete"
                : listening
                ? "animate-bounce bg-signal text-white"
                : "bg-white text-ink hover:bg-concrete"
            }`}
          >
            <Pictogram name={isSpeaking ? "speaker" : "mic"} size={22} />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  isSpeaking
                    ? "animate-ping bg-mark"
                    : busy
                    ? "animate-pulse bg-concrete"
                    : listening
                    ? "animate-pulse bg-signal"
                    : "bg-ink-4"
                }`}
              />
              <p className="font-sign text-sm font-semibold text-white">
                {isSpeaking
                  ? "Building is speaking…"
                  : busy
                  ? "Thinking…"
                  : listening
                  ? "Listening to you…"
                  : "Tap mic to speak"}
              </p>
            </div>
            <p className="mt-0.5 truncate text-xs text-ink-4">
              {isSpeaking
                ? "Tap to interrupt"
                : listening
                ? (text || "Speak your destination or question (take your time)")
                : busy
                ? "Analyzing route & spaces…"
                : "Microphone idle"}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            {isSpeaking && (
              <button
                type="button"
                onClick={() => stopSpeaking()}
                className="border border-ink-3 px-2 py-1 font-sign text-xs text-concrete hover:border-white hover:text-white"
              >
                Interrupt
              </button>
            )}
            <button
              type="button"
              onClick={onToggleVoiceMode}
              className="border border-ink-3 px-2.5 py-1 font-sign text-xs text-concrete hover:border-white hover:text-white"
            >
              Switch to text
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="relative flex gap-2 border-t border-ink-2 p-3">
      {voiceError && <p role="status" className="absolute bottom-full left-0 right-0 bg-ink-2 p-3 text-sm">{voiceError}</p>}
      {canListen() && (
        <button type="button" disabled={busy} aria-label={listening ? "Done speaking" : "Speak"} aria-pressed={listening}
          onClick={() => {
            if (listening) {
              stopListeningSession(true);
            } else {
              startListeningSession();
            }
          }}
          className={`grid h-12 w-12 shrink-0 place-items-center ${listening ? "bg-signal text-white" : "bg-white text-ink hover:bg-concrete"}`}>
          <Pictogram name="mic" size={22} />
        </button>
      )}
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening… (take your time to speak)" : "Ask the building"}
        aria-label="Message" className="h-12 min-w-0 flex-1 border border-ink-3 bg-ink-2 px-3 text-[16px] text-white placeholder:text-ink-4 focus:border-white focus:outline-none" />
      {busy&&<button type="button" className="border border-ink-3 px-3" onClick={onStop}>Stop</button>}
      <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
        className="grid h-12 w-12 shrink-0 place-items-center bg-mark text-ink disabled:opacity-40"><Pictogram name="send" size={20} /></button>
    </form>
  );
}

function RoomCard({ space, building, onClose, onHere, onGo, closed, onToggleClosed,onFocus }: {
  space: Space; building: NonNullable<ReturnType<typeof useNavigator>["geometry"]>; onClose: () => void; onHere: () => void; onGo: () => void;
  closed: Set<string>; onToggleClosed: (id: string) => void;onFocus:()=>void;
}) {
  const items = building.assets.filter((a) => a.space_id === space.id);
  const counts = Object.entries(items.reduce<Record<string, number>>((m, a) => ({ ...m, [a.type]: (m[a.type] ?? 0) + 1 }), {})).slice(0, 6);
  const connector = building.connectors.find((c) => c.space_ids.includes(space.id));
  const floor = building.floors.find((f) => f.id === space.floor_id);
  return (
    <div className="room-inspector absolute inset-x-3 bottom-3 border border-ink bg-white p-4 shadow-[4px_4px_0_var(--color-ink)] sm:left-auto sm:right-16 sm:w-[340px]" role="dialog" aria-label={space.name}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] text-ink-3">{ZONE_LABEL[zoneOf(space)]} · {floor?.name}</p>
          <h3 className="font-sign text-[22px] font-bold leading-tight">{space.name}</h3>
          <p className="text-[14px] text-ink-3">{area(space.polygon).toFixed(0)} m²{space.ref && !space.name.includes(space.ref) ? ` · ${space.ref}` : ""}</p>
        </div>
        <button onClick={onClose} aria-label="Close"><Pictogram name="close" size={20} /></button>
      </div>
      <button className="focus-room" onClick={onFocus}><Pictogram name="fit" size={16}/>Focus room</button>
      {counts.length > 0 && <p className="mt-2 text-[14px] text-ink-2">{counts.map(([t, n]) => `${n} ${t.replace(/_/g, " ")}`).join(" · ")}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button onClick={onGo} className="bg-ink py-2.5 font-sign text-[16px] font-bold text-white hover:bg-ink-2">Go here</button>
        <button onClick={onHere} className="border-2 border-escape py-2 font-sign text-[16px] font-bold text-escape hover:bg-escape hover:text-white">I'm here</button>
      </div>
      {connector && (
        <button onClick={() => onToggleClosed(connector.id)} className={`mt-2 w-full border py-2 font-sign text-[15px] ${closed.has(connector.id) ? "border-escape text-escape" : "border-signal text-signal"}`}>
          {closed.has(connector.id) ? `Reopen ${connector.name}` : `Close ${connector.name} for maintenance`}
        </button>
      )}
    </div>
  );
}

function StepMode({ steps, index, onIndex, onClose }: { steps: GuideStep[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const i = Math.max(1, index);
  const step = steps[i];
  if (!step) return null;
  return (
    <div className="absolute inset-0 flex flex-col bg-ink/95 p-6 text-white" role="dialog" aria-label="Step by step">
      <div className="flex items-center justify-between font-sign text-ink-4">
        <span>Step {i} of {steps.length - 1}</span>
        <button onClick={onClose} className="flex items-center gap-1 hover:text-white">Exit <Pictogram name="close" size={18} /></button>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
        <div className={`grid h-28 w-28 place-items-center ${step.kind === "arrive" ? "bg-mark text-ink" : "bg-white text-ink"}`}><Pictogram name={step.icon} size={64} /></div>
        <p className="max-w-xl font-sign text-[30px] font-semibold leading-tight">{step.text}</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <button disabled={i <= 1} onClick={() => onIndex(i - 1)} className="border border-ink-3 py-4 font-sign text-xl disabled:opacity-30">Back</button>
        <button onClick={() => speak(step.text)} className="border border-ink-3 py-4 font-sign text-xl">Repeat</button>
        <button disabled={i >= steps.length - 1} onClick={() => onIndex(i + 1)} className="bg-mark py-4 font-sign text-xl font-bold text-ink disabled:opacity-30">Next</button>
      </div>
    </div>
  );
}

function StartPicker({ geometry, onPick }: { geometry: NonNullable<ReturnType<typeof useNavigator>["geometry"]>; onPick: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLocaleLowerCase();
  const matches = normalized
    ? geometry.spaces.filter((x) => `${x.name} ${x.ref ?? ""} ${geometry.floors.find(f => f.id === x.floor_id)?.name ?? ""}`.toLocaleLowerCase().includes(normalized))
    : entrances(geometry);
  const options = matches.slice(0, 8);
  return (
    <div className="mt-2 space-y-1.5">
      <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Room name or number"
        aria-label="Search for your room" className="h-10 w-full border border-ink-3 bg-ink-2 px-3 text-white placeholder:text-ink-4 focus:border-white focus:outline-none" />
      <p role="status" className="text-[13px] text-ink-4">{normalized ? `${matches.length} matching rooms` : "Entrances, or tap your room on the plan"}{matches.length > options.length ? ` · Showing ${options.length} of ${matches.length}. Keep typing to narrow the list.` : ""}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((x) => (
          <button key={x.id} onClick={() => onPick(x.id)} className="border border-ink-3 px-2.5 py-1 font-sign text-[14.5px] hover:border-white">
            {x.name}{geometry.floors.length > 1 ? ` (${geometry.floors.find((f) => f.id === x.floor_id)?.name})` : ""}
          </button>
        ))}
        {!options.length && <span className="text-[14px] text-ink-4">No room matches that.</span>}
      </div>
    </div>
  );
}

function Legend() {
  const zones: [string, string][] = [["circulation", "Circulation"], ["hall", "Halls"], ["office", "Rooms"], ["lab", "Labs"], ["service", "Service"]];
  return (
    <div className="flex max-w-[460px] flex-wrap gap-x-3 gap-y-1 border border-ink bg-white px-3 py-2 text-[12.5px]">
      {zones.map(([z, l]) => <span key={z} className="flex items-center gap-1.5"><span className="h-3 w-3 border border-ink" style={{ background: `var(--color-zone-${z})` }} />{l}</span>)}
      <span className="flex items-center gap-1.5"><span className="h-0 w-0 border-x-[6px] border-b-[10px] border-x-transparent border-b-escape" />Entrance</span>
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 border border-ink bg-mark" />Door with steps</span>
    </div>
  );
}

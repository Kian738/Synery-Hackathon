import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { AgentReply } from "../components/AgentReply";
import {TurnResultLinks} from "../components/TurnResultLinks";
import {ComparisonCard} from "../components/ComparisonCard";
import {ExploreTools,rememberPlace} from "../components/ExploreTools";
import {readLocal} from "../lib/share";
import { ToolTrace } from "../components/ToolTrace";
import { CompanionControl } from "./CompanionControl";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { BuildDialog } from "../components/BuildDialog";
import { FloorRail } from "../components/FloorRail";
import { Dock, IconButton, Popover, Segmented } from "../ui/kit";
import { Pictogram } from "../components/Pictogram";
import { BuildingAtlas } from "../components/BuildingAtlas";
import { RoomCard, StartPicker as StartPickerPanel, Welcome } from "./kitPanels";
import { PlanView, type Pin } from "../components/PlanView";
import { api } from "../lib/api";
import type { ScenarioMark } from "../lib/types";
import { area, categories, centroid, label as labelOf, ZONE_LABEL, zoneOf } from "../lib/geometry";
import type { BuildingRow, GuideStep, Space, VisualResult } from "../lib/types";
import { audioStreamQueue, canListen, listen, speak, stopSpeaking } from "../lib/voice";
import { ScenarioPanel } from "./ScenarioPanel";
import { JourneyBanner } from "../journey/JourneyBanner";
import { currentIndoorLeg, nextLeg, setJourneyIndex } from "../journey/journey";
import { entrances, type Message, useNavigator } from "./useNavigator";

const DEFAULT_BUILDING = "proc-campus-dev-000";
const ExteriorView=lazy(()=>import("../components/ExteriorView"));
const Building3D = lazy(() => import("../components/Building3D"));

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const isStairSpace = (s: Space) => /stair|escalier|stairwell|cage/i.test(`${s.type} ${s.room_type} ${s.name}`);

function findSpacesMentionedInText(
  text: string,
  spaces: Space[],
  visualResult?: VisualResult | null,
  highlights?: Set<string>
): Space[] {
  const found: Space[] = [];
  const addedIds = new Set<string>();

  const add = (s: Space) => {
    if (isStairSpace(s)) return;
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
  const sceneHost=useRef<HTMLDivElement>(null);
  const chatWorkspace=useRef<HTMLDivElement>(null);
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
  const [weakOpen,setWeakOpen]=useState(false);
  const [scenarioOpen,setScenarioOpen]=useState(false);
  const [exploreOpen,setExploreOpen]=useState(false);
  const [scenarioMark,setScenarioMark]=useState<ScenarioMark|null>(null);
  const scenarioZones=useMemo(()=>{const z:Record<string,string>={};Object.entries(scenarioMark?.crowd??{}).forEach(([id,n])=>{z[id]=n===2?"crowd2":"crowd1";});scenarioMark?.responder?.spaces.forEach(id=>{z[id]="responder";});return z;},[scenarioMark]);
  useEffect(()=>{if(nav.scenarioIn)setScenarioOpen(true);},[nav.scenarioIn]);
  const [questionOpen,setQuestionOpen]=useState(false);
  const [phoneOpen,setPhoneOpen]=useState(false);
  const [compact,setCompact]=useState(()=>matchMedia("(max-width:1023px)").matches);
  const [toolsOpen,setToolsOpen]=useState(false);
  const toolsRef = useRef<HTMLDetailsElement>(null);
  useEffect(()=>{const q=matchMedia("(max-width:1023px)");const changed=()=>{setCompact(q.matches);setToolsOpen(false);};q.addEventListener("change",changed);return()=>q.removeEventListener("change",changed);},[]);
  const [lookOffset,setLookOffset]=useState({yaw:0,pitch:0});
  const [focusRequest,setFocusRequest]=useState<{id:string;revision:number}|null>(null);
  const selectSpace=useCallback((space:Space)=>{setSelected(space);setPlanExpanded(false);setWeakOpen(false);nav.setFloorId(space.floor_id);},[nav.setFloorId]);
  const [stepMode, setStepMode] = useState(false);
  const [view, setView] = useState<"2d" | "3d" | "guide" | "follow" | "exterior">(params.get("view") === "2d" ? "2d" : "3d");
  const savedScope = (() => { try { const v = sessionStorage.getItem("floorwise.scope"); return v === "current" || v === "route" || v === "building" ? v : null; } catch { return null; } })();
  const [scope, setScope] = useState<"current"|"route"|"building">(savedScope ?? "current");
  const scopeTouched = useRef(savedScope !== null);
  /** The person's own choice always wins and is remembered for the session; until then a multi-floor route opens as "Route floors" with focus on. */
  const chooseScope = (v: "current"|"route"|"building") => { scopeTouched.current = true; try { sessionStorage.setItem("floorwise.scope", v); } catch { /* storage blocked */ } setScope(v); };
  const [exploded,setExploded]=useState(true);
  const [focusOn,setFocusOn]=useState(true),[guideFocus,setGuideFocus]=useState(false),[layersOpen,setLayersOpen]=useState(false);
  const [planExpanded,setPlanExpanded]=useState(false);
  const [stageExpanded,setStageExpanded]=useState(params.get("explore")==="1");
  const [seekRequest,setSeekRequest]=useState(0);
  const [previewPosition,setPreviewPosition]=useState<{x:number;y:number;floor_id:string;heading?:number}|null>(null);
  const following=view==="follow"||view==="guide";
  /** The walked line of the floor the current step is on, for the phone's AR overlay (at most 400 points). */
  const phonePath = useMemo(() => {
    const route = nav.route, floor = route?.guide.steps[nav.activeStep]?.floor_id ?? route?.polyline[0]?.floor_id;
    const pts = (route?.polyline ?? []).filter(p => p.floor_id === floor && !p.gap);
    if (pts.length < 2) return undefined;
    const stride = Math.max(1, Math.ceil(pts.length / 400));
    return pts.filter((_, i) => i % stride === 0 || i === pts.length - 1).map(p => [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100] as [number, number]);
  }, [nav.route, nav.activeStep]);
  useEffect(() => { if (!nav.route || scopeTouched.current) return; setScope(nav.route.floors.length > 1 ? "route" : "current"); }, [nav.route]);
  const [picking, setPicking] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [buildingImport, setBuildingImport] = useState(() => params.get("import") === "1"); // no visible button: building from a plan stays reachable by URL and tests

  useEffect(() => { api.buildings().then(setBuildings).catch(() => {}); }, []);
  useEffect(() => { setSelected(null); setStepMode(false);setView(params.get("view")==="2d"?"2d":"3d");setPreviewPosition(null);setPlanExpanded(false);setStageExpanded(params.get("explore")==="1");setScope("current");setWeakOpen(false);setQuestionOpen(false);setFocusRequest(null);setPhoneOpen(false);setToolsOpen(false);setScenarioOpen(false);setExploreOpen(false);linked.current=false; }, [buildingId]);
  // Deep link (shareable, QR at a door): ?building=…&at=<space id>&to=<place>&step_free=1
  const linked = useRef(false);
  useEffect(()=>{document.documentElement.classList.toggle('high-contrast',readLocal<unknown>('floorwise:contrast',false)===true);document.documentElement.classList.toggle('large-text',readLocal<unknown>('floorwise:large-text',false)===true);},[]);
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setExploreOpen(v=>!v);setToolsOpen(false);setScenarioOpen(false);}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);
  useEffect(()=>{if(selected)rememberPlace(buildingId,selected.id);},[buildingId,selected?.id]);
  useEffect(()=>{if(selected&&selected.floor_id!==nav.floorId)setSelected(null);},[nav.floorId]);
  useEffect(()=>{const node=sceneHost.current;if(!node)return;const wheel=(e:WheelEvent)=>{if(e.ctrlKey)e.preventDefault();};node.addEventListener('wheel',wheel,{passive:false});return()=>node.removeEventListener('wheel',wheel);},[nav.geometry?.building.id]);
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){setSelected(null);setPicking(false);setShowKey(false);setWeakOpen(false);setPhoneOpen(false);setPlanExpanded(false);setQuestionOpen(false);}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);
  const enterInterior=useCallback(()=>setView('3d'),[]);
  useEffect(()=>{if(!nav.geometry)return;const target=nav.geometry.spaces.find(s=>s.id===params.get('room'));if(target){setSelected(target);nav.setFloorId(target.floor_id);setFocusRequest({id:target.id,revision:1});}},[nav.geometry?.building.id]);
  useEffect(() => {
    const to = params.get("to");
    if (linked.current || !to || !nav.geometry || !nav.here || !nav.sessionId) return;
    linked.current = true;
    const stepFree = params.get("step_free") === "1";
    if (stepFree) nav.setStepFree(true);
    let via:string[]=[];try{via=JSON.parse(params.get('via')??'[]');if(!Array.isArray(via)||via.length>12||via.some(id=>typeof id!=='string'||!nav.geometry!.spaces.some(s=>s.id===id)))throw Error();}catch{nav.setNotice('This shared itinerary is invalid. Choose a destination again.');return;}
    if(via.length)void api.route(nav.sessionId,{start:nav.here,destination:to,via,step_free:stepFree}).then(r=>{nav.apply(r.events);if(r.result.error)nav.setNotice(r.result.error);}).catch(e=>nav.setNotice(String(e)));else nav.goTo(to, nav.here, stepFree);
  }, [nav.geometry, nav.here, nav.sessionId]); // eslint-disable-line react-hooks/exhaustive-deps
  // A trip between buildings: once this leg's route is planned, start the step-by-step guide by itself.
  const tripLeg = currentIndoorLeg(buildingId);
  const tripShown = useRef<string | null>(null);
  const navigateTo = useNavigate();
  const startGuide = () => {
    if (nav.route?.preview_available === false) { setStepMode(true); return; }
    setView("guide"); setQuestionOpen(false); setPlanExpanded(false); setWeakOpen(false); setStageExpanded(false); nav.setVisualResult(null); nav.setActiveStep(0); setSelected(null);
  };
  // Reaching the exit door (the last step of the leg) carries the trip on by itself: tunnel, then the next building.
  const atTripExit = !!tripLeg?.active && tripLeg.leg.role === "exit" && !!nav.route
    && (!!tripLeg.leg.trivial || ((nav.route?.guide?.steps.length ?? 0) > 1 && nav.activeStep >= (nav.route?.guide?.steps.length ?? 0) - 1));
  useEffect(() => {
    if (!atTripExit || !tripLeg) return;
    const timer = window.setTimeout(() => { setJourneyIndex(nextLeg(tripLeg.result, tripLeg.index)); navigateTo("/tunnel"); }, tripLeg.leg.trivial ? 3500 : 2000);
    return () => window.clearTimeout(timer);
  }, [atTripExit, tripLeg?.key]); // eslint-disable-line react-hooks/exhaustive-deps
  // Show the planner's own route for this leg (start room to the exit door, or entrance to the destination room).
  useEffect(() => {
    if (!tripLeg || !nav.geometry || tripShown.current === tripLeg.key) return;
    tripShown.current = tripLeg.key;
    nav.applyEvents([{ type: "route", route: tripLeg.leg.route } as never]);
  }, [nav.geometry, tripLeg?.key]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if(following&&previewPosition)out.push({id:"preview",at:[previewPosition.x,previewPosition.y],floor_id:previewPosition.floor_id,label:"Preview avatar (not your location)",tone:"info",heading:previewPosition.heading});
    const at = (id: string) => g.spaces.find((s) => s.id === id);
    const here = nav.here ? at(nav.here) : null;
    if (here) out.push({ id: "here", at: here.anchor??centroid(here.polygon), floor_id: here.floor_id, label: `Starting from ${here.name}`, tone: "start" });
    if (nav.route?.polyline.length) {
      const first = nav.route.polyline[0], last = nav.route.polyline[nav.route.polyline.length - 1];
      if(nav.route.stops[0]!==nav.here)out.push({ id: "start", at: [first.x, first.y], floor_id: first.floor_id, label: "Route start", tone: "start" });
      out.push({ id: "end", at: [last.x, last.y], floor_id: last.floor_id, label: tripLeg ? (tripLeg.leg.role === "exit" ? "Exit door" : "Your destination") : "Destination", tone: "end" });
      const step = steps[nav.activeStep];
      if (!following && step?.point && step.floor_id && nav.activeStep > 0 && step.kind !== "arrive")
        out.push({ id: "step", at: step.point, floor_id: step.floor_id, label: step.text, tone: "info", n: nav.activeStep });
    }
    return out;
  }, [g, nav.here, nav.route, nav.activeStep, steps,following,previewPosition,tripLeg?.key]);

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
    return <div className="recovery" role="status">{nav.notice??"Loading building…"}{nav.notice&&<><button onClick={nav.retryLoad}>Retry loading</button><label>Choose another building<select value={buildingId} onChange={e=>setParams({building:e.target.value})}>{buildings.map(b=><option value={b.building_id} key={b.building_id}>{b.name}</option>)}</select></label></>}</div>;
  }

  return (
    <div className={`navigator-shell flex h-full flex-col lg:flex-row ${!nav.route && nav.messages.length === 0 ? "first-use" : ""} ${stageExpanded?"stage-expanded":""} ${following?"guiding":""} ${questionOpen?"question-open":""} ${planExpanded?"map-open":""} ${weakOpen?"analysis-open":""}`}>
      <JourneyBanner buildingId={buildingId} routeFailed={!!nav.notice && !nav.route} atExit={atTripExit} guiding={following || stepMode} onStartGuide={startGuide} />
      {/* ---------- sign column ---------- */}
      <aside className="order-2 flex min-h-0 flex-1 flex-col navigation-panel bg-ink text-white lg:order-1 lg:w-[370px] lg:flex-none">
        <header className="k-head">
          <BuildingMenu buildings={buildings} value={buildingId} onChange={(b) => setParams({ building: b })} name={g.building.name} />
          <Dock>
            <IconButton label="Step-free" icon="wheelchair" pressed={nav.stepFree} onClick={() => nav.setStepFree(!nav.stepFree)} />
            <IconButton label="Read aloud" icon="speaker" pressed={voiceOut && !voiceMode} onClick={() => { setVoiceOut(!voiceOut); if (voiceOut) stopSpeaking(); }} />
            <IconButton label={voiceMode ? "Voice mode (ON)" : "Voice only"} icon="mic" pressed={voiceMode} onClick={handleToggleVoiceMode} />
          </Dock>
        </header>
        <div className="k-start">
          <button onClick={() => setPicking(!picking)} aria-expanded={picking} className="k-startbtn">
            <Pictogram name="here" size={16} className="shrink-0 text-escape" />
            <span>{nav.here ? <>Starting from <b>{labelOf(g, nav.here)}</b></> : "Where are you? Choose a start"}</span>
            <u>change</u>
          </button>
          {nav.here && <p className="k-hint">{nav.hereSource === "default" ? "Entrance used as start. Change it if you’re elsewhere." : nav.hereSource === "link" ? "Start supplied by link. Change it if you’re elsewhere." : "Start set by you. Location is not tracked."}</p>}
          {picking && (
            <StartPickerPanel geometry={g} entrances={entrances} onPick={(id) => { nav.setHere(id); const room=g.spaces.find(s=>s.id===id);if(room)nav.setFloorId(room.floor_id);setPicking(false); nav.setNotice(`Location set: ${labelOf(g,id)}. Your green marker is set manually.`); }} />
          )}
        </div>

        <div ref={chatWorkspace} className="chat-workspace scroll-thin min-h-0 flex-1 overflow-y-auto">
          {nav.visualResult&&nav.sessionId&&<VisualAnswer result={nav.visualResult} total={nav.visualResult.total_rows} sessionId={nav.sessionId} onClose={()=>{nav.setVisualResult(null);nav.setHighlights(new Set());}} onPick={id=>{const room=g.spaces.find(s=>s.id===id)??g.spaces.find(s=>s.id===g.assets.find(a=>a.id===id)?.space_id);if(room)focusRoom(room);}} onFloor={nav.setFloorId} geometry={g}/> }
          {nav.route && !nav.visualResult && (
            <RouteSign route={nav.route} meta={nav.routeMeta} stepFree={nav.route.constraints.includes("step-free")}
              active={nav.activeStep} onStep={focusStep} onClear={nav.clearRoute} onStepMode={() => { setView("guide");setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setStageExpanded(false); nav.setVisualResult(null); nav.setActiveStep(0); setSelected(null); }} floors={g.floors} />
          )}
          {!nav.route && nav.messages.length === 0 && (
            <Welcome categories={cats} onPick={(q) => nav.goTo(q)} onAsk={nav.ask} hasHere={!!nav.here} buildingName={g.building.name} examples={examples} />
          )}
          <Conversation onResult={result=>{nav.setVisualResult(result);nav.setHighlights(new Set(result.entities.map(e=>e.id)));requestAnimationFrame(()=>chatWorkspace.current?.scrollTo({top:0,behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"}));}} onRerun={q=>nav.ask(q)} suggest={examples} onAsk={q=>nav.ask(q)} understood={[nav.here?`From ${labelOf(g,nav.here)}`:"",nav.route&&nav.routeMeta?.to?`To ${nav.routeMeta.to}`:"",nav.stepFree?"Step-free":"",nav.closed.size?`${nav.closed.size} closed`:""].filter(Boolean)} busyLabel={nav.busyLabel} geometry={g} onRoom={id=>{const room=g.spaces.find(s=>s.id===id);if(room){setView("3d");setQuestionOpen(false);focusRoom(room);}}} messages={nav.messages} busy={nav.busy} currentlySpeakingId={currentlySpeakingId} onSpeakMessage={(id,text)=>{if(currentlySpeakingId===id){stopSpeaking();setCurrentlySpeakingId(null);}else{setCurrentlySpeakingId(id);speak(text,()=>setCurrentlySpeakingId(null));}}} onOption={(id, purpose) => (purpose === "choice" ? nav.ask(id) : nav.goTo(id))} onDecide={nav.decideChange} />
        </div>

        {nav.route && cats.length > 0 && (
          <div className="flex gap-1.5 overflow-x-auto border-t border-ink-2 px-4 py-2 scroll-thin">
            {cats.map((c) => (
              <button key={c.key} onClick={() => nav.goTo(c.query)} className="k-ctl shrink-0">
                <Pictogram name={c.icon} size={15} /> {c.label}
              </button>
            ))}
          </div>
        )}
        {nav.turnUsage&&<details className="turn-usage"><summary aria-label="Response details">{Number(nav.turnUsage.latency_ms)>0?`${(Number(nav.turnUsage.latency_ms)/1000).toFixed(1)} s`:"Response"} · details</summary><div>{nav.turnUsage.dispatch==="deterministic"?"Computed locally · no model tokens":`${nav.turnUsage.dispatch==="parser"?"Language parsed":"Agent response"} · ${Number(nav.turnUsage.input_tokens??0)+Number(nav.turnUsage.output_tokens??0)+Number(nav.turnUsage.cache_read_input_tokens??0)+Number(nav.turnUsage.cache_creation_input_tokens??0)} model tokens`}{typeof nav.turnUsage.estimated_cost_usd==="number"&&nav.turnUsage.dispatch!=="deterministic"?` · est. $${nav.turnUsage.estimated_cost_usd.toFixed(4)}`:""}{typeof nav.turnUsage.latency_ms==="number"?` · ${(nav.turnUsage.latency_ms/1000).toFixed(1)} s`:""}{typeof nav.turnUsage.first_text_ms==="number"?` · first text ${(nav.turnUsage.first_text_ms/1000).toFixed(1)} s`:""}</div></details>}
        <Composer onStop={nav.stop} busy={nav.busy} voiceMode={voiceMode} onToggleVoiceMode={handleToggleVoiceMode} isSpeaking={isAgentSpeaking} onSend={handleSend} />
      </aside>

      <main className="model-panel relative order-1 flex h-[46vh] shrink-0 lg:order-2 lg:h-auto lg:flex-1">
        <div className="k-top">
          <Dock>
            {following ? <IconButton label="Back to building" icon="back" text="Back to building" onClick={()=>{setView("3d");setQuestionOpen(false);}}/> : <>
              <Segmented ariaLabel="View" value={view==="2d"?"2d":"3d"} onChange={v=>setView(v)} options={[
                {value:"3d",label:"3D",ariaLabel:"3D",icon:"cube",tip:"3D building"},
                {value:"2d",label:"Plan",ariaLabel:"Floor plan",icon:"plan",tip:"Floor plan"}]}/>
              <IconButton label="Guide me" icon="walk" text="Guide me" accent disabled={!nav.route || nav.route.preview_available === false} onClick={() => {setView("guide");setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setStageExpanded(false);nav.setVisualResult(null);setSelected(null);}}/>
            </>}
          </Dock>
          <Dock>
            {following&&<IconButton label="Ask" icon="send" text="Ask" pressed={questionOpen} onClick={()=>{setQuestionOpen(!questionOpen);setPlanExpanded(false);}}/>}
            {following&&<IconButton label="Focus on route" icon="focus" pressed={guideFocus} onClick={()=>setGuideFocus(v=>!v)}/>}
            {following&&<IconButton label="Read aloud" icon="speaker" pressed={voiceOut} onClick={()=>{setVoiceOut(!voiceOut);if(voiceOut){stopSpeaking();clearVoiceTour();}}}/>}
            <IconButton label="Show map" icon="map" pressed={planExpanded} onClick={toggleMap}/>
            {view==="3d"&&!following&&<Popover label="Layers" icon="layers" open={layersOpen} onOpenChange={setLayersOpen} badge={nav.closed.size||undefined}>
              <div className="k-pop-title">Show</div>
              <Segmented ariaLabel="Visible floors" value={scope} onChange={chooseScope} options={[
                {value:"current",label:"This floor",ariaLabel:"This floor"},
                {value:"route",label:"Route",ariaLabel:"Route floors",disabled:!nav.route},
                {value:"building",label:"Building",ariaLabel:"Whole building"}]}/>
              {scope!=="current"&&<button aria-pressed={exploded} onClick={()=>setExploded(!exploded)}><Pictogram name="spread" size={18}/>Spread floors apart</button>}
              {!!nav.route&&scope!=="building"&&<button aria-pressed={focusOn} onClick={()=>setFocusOn(v=>!v)}><Pictogram name="focus" size={18}/>Focus on route</button>}
              {nav.closed.size>0&&<><div className="k-pop-title">Closed places</div>{[...nav.closed].map(id=><div className="k-closed" key={id}><span>{g.spaces.find(x=>x.id===id)?.name??g.connectors.find(x=>x.id===id)?.name??"Door"}</span><button onClick={()=>nav.toggleClosed(id)}>Reopen</button></div>)}</>}
            </Popover>}
            <Popover label="Building tools" icon="tools" open={toolsOpen} onOpenChange={setToolsOpen} className="building-tools">
              {g.building.source_ref?.osm&&<button aria-pressed={view==='exterior'} onClick={()=>{setView('exterior');setSelected(null);setPlanExpanded(false);setToolsOpen(false);nav.setNotice(null);}}><Pictogram name="outside" size={18}/>Outside</button>}
              {!following&&<button onClick={()=>{setExploreOpen(true);setToolsOpen(false);setScenarioOpen(false);setPlanExpanded(false);setWeakOpen(false);setPhoneOpen(false);}}><Pictogram name="pin" size={18}/>Find, save &amp; share</button>}
              {!following&&<button aria-pressed={scenarioOpen} onClick={()=>{setScenarioOpen(v=>!v);setToolsOpen(false);setWeakOpen(false);setPlanExpanded(false);setSelected(null);setPhoneOpen(false);}}><Pictogram name="orbit" size={18}/>Scenarios</button>}
              <CompanionControl path={phonePath} buildingId={buildingId} steps={steps} index={nav.activeStep} routeId={companionRouteId} open={phoneOpen} onToggle={()=>{setPhoneOpen(v=>!v);setToolsOpen(false);setQuestionOpen(false);setPlanExpanded(false);setWeakOpen(false);setSelected(null);}}
                onStep={action=>{if(!nav.route)return;if(action==="repeat"){speak(steps[nav.activeStep]?.text??"");return;}if(!following)setView("guide");focusStep(Math.max(0,Math.min(steps.length-1,nav.activeStep+(action==="next"?1:-1))));}}
                onLook={(yaw,pitch)=>{if(view==="2d")setView("3d");setLookOffset(v=>({yaw:((v.yaw+yaw+540)%360)-180,pitch:Math.max(-55,Math.min(55,v.pitch+pitch))}));}}
                onRecenter={()=>setLookOffset({yaw:0,pitch:0})}/>
              {!following&&<><button disabled={nav.busy} onClick={()=>{setWeakOpen(v=>!v);setToolsOpen(false);setPlanExpanded(false);setSelected(null);if(!nav.weakPoints.length)nav.inspectWeakPoints();}}><Pictogram name="aid" size={18}/>Stress test</button><Link to="/lab"><Pictogram name="info" size={18}/>Evidence</Link></>}
            </Popover>
          </Dock>
        </div>
        <div className={`floor-selector-host ${view==='exterior'?'hidden':''}`}><FloorRail floors={g.floors} active={displayFloor} route={nav.route} onPick={id=>{if(following)setView("3d");nav.setFloorId(id);}} here={hereFloor} /></div>
        <div className="model-viewport" ref={sceneHost}>
          <ErrorBoundary key={`${g.building.id}-${view==="2d"?"plan":"scene"}`} label="The building view needs recovery">
            {view==='exterior'?<Suspense fallback={<p role="status">Preparing exterior map…</p>}><ExteriorView buildingId={buildingId} onEnter={enterInterior}/></Suspense>:view === "2d" ? <PlanView geometry={g} floorId={displayFloor} route={nav.visualResult&&!following?null:nav.route} highlights={activeHighlights} closed={nav.closed} visualResult={nav.visualResult}
              pins={pins} previewDoor={nav.previewDoor} selected={voiceFocusSpace?.id ?? selected?.id} scenario={scenarioMark} focus={focusPoint} onSpaceClick={selectSpace} /> :
              <Suspense fallback={<div className="recovery">Preparing the building model...</div>}>
                <Building3D hazard={scenarioMark?.hazard} zones={scenarioZones} focus={following?guideFocus:focusOn} onFocus={following?setGuideFocus:setFocusOn} geometry={g} floorId={nav.floorId} route={nav.visualResult&&!following?null:nav.route} previousRoute={nav.visualResult?null:nav.previousRoute} highlights={activeHighlights}
                  closed={nav.closed} previewDoor={nav.previewDoor} showAll={false} scope={scope} exploded={exploded} follow={following} previewMode={view==="follow"} activeStep={nav.activeStep} seekRequest={seekRequest} here={nav.here} selected={voiceFocusSpace?.id ?? selected?.id} visualResult={nav.visualResult} heading={heading?Number(heading):undefined} onPosition={p=>{setPreviewPosition(old=>old&&old.x===p.x&&old.y===p.y&&old.floor_id===p.floor_id?old:p);}} focusRequest={focusRequest} onRepeat={()=>speak(steps[nav.activeStep]?.short??steps[nav.activeStep]?.text??"")} onFinish={()=>{setView("3d");setQuestionOpen(false);setPlanExpanded(false);}} onPreview={()=>{stopSpeaking();setVoiceOut(false);setView("follow");}}
                  onStep={nav.setActiveStep} onSpaceClick={selectSpace} lookOffset={lookOffset}/>
              </Suspense>}
          </ErrorBoundary>
        </div>
        {view!=="2d"&&view!=="exterior"&&planExpanded&&<section className="map-drawer" aria-label="Linked floor plan">
          <header><span>{g.floors.find(f=>f.id===displayFloor)?.name}</span><button aria-label="Close map" onClick={()=>setPlanExpanded(false)}><Pictogram name="close" size={18}/></button></header>
          <PlanView geometry={g} floorId={displayFloor} route={nav.visualResult&&!following?null:nav.route} highlights={activeHighlights} closed={nav.closed} visualResult={nav.visualResult} pins={pins} selected={voiceFocusSpace?.id ?? selected?.id} scenario={scenarioMark} focus={focusPoint} focusKey={`${nav.route?.stops.join()}-${focusRequest?.revision}-${nav.visualResult?.id}`} followPosition={following} onSpaceClick={selectSpace} compact/>
        </section>}
        {!nav.notice && nav.route?.warnings?.length ? <div className="model-notice" role="status">{nav.route.warnings.join(" ")}</div> : null}
        {exploreOpen&&<ExploreTools geometry={g} selected={selected} here={nav.here} route={nav.route} stepFree={nav.stepFree} onClose={()=>setExploreOpen(false)} onSelect={focusRoom} onHighlight={ids=>{nav.setHighlights(new Set(ids));const entity=g.assets.find(a=>a.id===ids[0]);if(entity)nav.setFloorId(entity.floor_id);}} onCompare={floor=>void nav.compareItems(floor)} onPlan={async stops=>{await nav.planStops(stops);setView('3d');}}/>}
        {nav.closeConfirm && <div role="alertdialog" aria-label="Confirm closing" className="model-notice k-confirm">
          <span><b>Close {nav.closeConfirm.name}?</b> {nav.closeConfirm.count} of {nav.closeConfirm.of} rooms would lose their way out.</span>
          <button className="k-ctl" onClick={() => nav.setCloseConfirm(null)}>Cancel</button>
          <button className="k-ctl accent" onClick={() => { const c = nav.closeConfirm!; nav.setCloseConfirm(null); void nav.toggleClosed(c.id, true); }}>Close anyway</button>
        </div>}
        {!nav.closeConfirm && nav.lastClosure && <div role="status" className="model-notice k-confirm">
          <span>Closed {nav.lastClosure.name}.</span><button className="k-ctl" onClick={() => void nav.toggleClosed(nav.lastClosure!.id)}>Undo</button>
        </div>}
        {nav.notice && !nav.closeConfirm && !nav.lastClosure && <div role="status" className="model-notice"><span>{nav.notice}</span>{/^No route/.test(nav.notice)&&nav.closed.size>0&&<button className="reopen-all" onClick={()=>[...nav.closed].forEach(id=>nav.toggleClosed(id))}>Reopen closed places</button>}<button aria-label="Dismiss" onClick={() => nav.setNotice(null)}>×</button></div>}
        {scenarioOpen&&!following&&nav.sessionId&&<ScenarioPanel onBeat={(say,id)=>{setFocusRequest(r=>({id,revision:(r?.revision??0)+1}));if(voiceOut&&!window.speechSynthesis?.speaking)speak(say);}} incoming={nav.scenarioIn} replayCmd={nav.replayCmd} geometry={g} sessionId={nav.sessionId} selected={selected} onClose={()=>{setScenarioOpen(false);setScenarioMark(null);nav.clearScenarioEvents();nav.setHighlights(new Set());}} onHighlight={nav.setHighlights} onScenario={setScenarioMark} onFloor={nav.setFloorId} apply={nav.applyEvents}/>}
        {weakOpen&&!following&&!scenarioOpen&&<section className="stress-drawer" aria-label="Building stress test">
          <header><div><span>What-if analysis</span><h2>Exit access under closure</h2></div><button aria-label="Close stress test" onClick={()=>setWeakOpen(false)}><Pictogram name="close"/></button></header>
          <p>Each result closes one connector independently and checks step-free routes to mapped exits.</p>
          {nav.busy?<p role="status">Checking connector closures…</p>:nav.weakPoints.length?nav.weakPoints.map((item,i)=><button className="stress-result" key={i} onClick={()=>{nav.setHighlights(new Set(item.room_ids));const room=g.spaces.find(s=>s.id===item.room_ids[0]);if(room)nav.setFloorId(room.floor_id);}}>
            <span><Pictogram name={item.kind==="lift"?"lift":"stairs"}/><b>{item.name}</b></span><strong>{item.rooms_lost}<small> / {item.of_rooms} rooms</small></strong><span>would lose step-free exit access</span><span className="stress-inspect">Show affected rooms</span>
          </button>):<p>No individual connector closure disconnects mapped rooms for this analysis.</p>}
          <details><summary>Evidence and assumptions</summary><p>Computed by removing each connector from the route graph and comparing exit reachability. This is a single-failure sensitivity check, not a fire or crowd-capacity simulation. Occupancy and door throughput are not supplied.</p></details>
          <button className="stress-rerun" disabled={nav.busy} onClick={nav.inspectWeakPoints}>Run again</button>
        </section>}
        {selected && !following && <RoomCard key={selected.id} space={selected} building={g} onClose={() => setSelected(null)} closed={nav.closed}
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
  const [retry,setRetry]=useState(0);
  useEffect(()=>{setOffset(0);setRows([]);setRoom('');},[result.id]);
  useEffect(()=>{if(result.kind==='comparison')return;let current=true;setError('');setRows([]);api.resultPage(sessionId,result.id,offset,grouped?(room?'items':'rooms'):'default',room).then(page=>{if(current){setRows(page.rows);setPageTotal(page.total);}}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[sessionId,result.id,offset,grouped,room,retry]);
  if(result.kind==='comparison')return <ComparisonCard result={result} session={sessionId} onPick={onPick} onClose={onClose}/>;
  return <section className="visual-answer" aria-label="Visual answer">
    <header><span>{grouped?'Equipment by room':result.kind.replaceAll('_',' ')}</span><button aria-label="Close visual answer" onClick={onClose}>Close</button></header>
    <h2>{result.title}</h2><p className="result-provenance">{result.provenance}</p>
    {grouped&&<p className="result-measure"><b>{String(result.measurements.item_count)} items</b><span>in {String(result.measurements.room_count)} rooms</span></p>}
    {room&&<button onClick={()=>{setRoom('');setOffset(0);}}>Back to rooms</button>}
    <div className="result-floors">{result.floor_ids.map(id=><button key={id} onClick={()=>onFloor(id)}>{geometry.floors.find(f=>f.id===id)?.name??id}</button>)}</div>
    {!grouped&&Object.entries(result.measurements).filter(([,v])=>typeof v==='number').map(([key,value])=><p key={key} className="result-measure"><span>{key.replace(/_m2$|_m$/,' ').replaceAll('_',' ')}</span><b>{String(value)}{key.includes('m2')?' m²':key.endsWith('_m')?' m':''}</b></p>)}
    {result.warnings.map((warning,i)=><p key={i}>{warning}</p>)}
    {Array.isArray(result.measurements.assumptions)&&<details><summary>Inputs, method and assumptions</summary><p>{String(result.measurements.method??'')}</p><ul>{result.measurements.assumptions.map((a,i)=><li key={i}>{String(a)}</li>)}</ul></details>}
    {error&&<p role="alert">{error.includes('404')?'This earlier result expired. Use Run again on its chat card.':error}<button onClick={()=>setRetry(n=>n+1)}>Retry results</button></p>}
    {!rows.length&&pageTotal>0&&!error&&<p role="status">Loading results…</p>}
    <ol className="result-list">{rows.map((row,i)=><li key={String(row.id??i)}><button onClick={()=>geometry.floors.some(f=>f.id===row.id)?onFloor(String(row.id)):onPick(String(row.id))} disabled={!geometry.spaces.some(s=>s.id===row.id)&&!geometry.assets.some(a=>a.id===row.id)&&!geometry.floors.some(f=>f.id===row.id)}><span>{String(row.label??row.name??row.id)}</span><b>{row.count!==undefined?String(row.count):row.area_m2!==undefined?`${row.area_m2} m²`:row.overlap_m2!==undefined?`${row.overlap_m2} m² overlap`:row.reachable!==undefined?(row.reachable?'Reachable':'Unavailable'):row.before_m!==undefined?`${row.before_m} → ${row.after_m} m`:'Show'}</b></button>{grouped&&!room&&<button aria-label={`Items in ${row.label}`} onClick={()=>{setRoom(String(row.id));setOffset(0);}}>Items</button>}</li>)}</ol>
    {pageTotal>25&&<nav aria-label="Result pages"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button><span>{offset+1}–{Math.min(offset+25,pageTotal)} of {pageTotal}</span><button disabled={offset+25>=pageTotal} onClick={()=>setOffset(offset+25)}>Next</button></nav>}
    <p className="result-provenance">{result.entities.length} matching entities across {result.floor_ids.length} floors. Lists are paged; map matches are complete.</p>
  </section>;
}

function BuildingMenu({ buildings, value, onChange, name }: { buildings: BuildingRow[]; value: string; onChange: (b: string) => void; name: string }) {
  const [open, setOpen] = useState(false);
  const recent = useMemo(() => { try { return JSON.parse(localStorage.getItem("floorwise.recent-buildings") ?? "[]") as string[]; } catch { return []; } }, [open]);
  const pick = (id: string) => {
    try { localStorage.setItem("floorwise.recent-buildings", JSON.stringify([id, ...recent.filter(r => r !== id)].slice(0, 5))); } catch { /* storage may be blocked */ }
    setOpen(false); if (id !== value) onChange(id);
  };
  return (
    <>
      <button type="button" className="k-ctl k-btrigger" aria-label="Change building" aria-expanded={open} onClick={() => setOpen(true)}>
        <span className="k-btitle" title={name}>{name}</span><Pictogram name="chevron" size={16} /></button>
      {open && <BuildingAtlas buildings={buildings} value={value} recent={recent} onPick={pick} onClose={() => setOpen(false)} />}
    </>
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
      <div className="current-decision k-now">
        <div className="k-now-top">
          <span className="k-now-badge"><Pictogram name={steps[active]?.icon ?? "straight"} size={20} /></span>
          <span className="k-now-count">Step {active + 1} of {steps.length}</span>
          <span className="k-dots" aria-hidden="true">{steps.map((_, i) => <i key={i} data-on={i <= active} />)}</span>
        </div>
        <p className="k-now-text">{steps[active]?.text}</p>
        {steps[active + 1] && <p className="k-next-step"><b>Next</b>{steps[active + 1].short}</p>}
      </div>
      <details className="route-itinerary"><summary>All {steps.length} instructions</summary><ol className="divide-y divide-ink-2">
        {steps.map((s, i) => (
          <StepRow key={i} step={s} index={i} active={i === active} onClick={() => onStep(i)} floorName={floors.find((f) => f.id === s.floor_id)?.name} />
        ))}
      </ol></details>
      <div className="route-start-actions flex gap-2 px-4 py-3">
        <button disabled={route.preview_available === false} onClick={onStepMode} className="k-ctl accent flex-1">{route.preview_available === false ? "Preview unavailable: check geometry" : "Guide me step by step"}</button>
      </div>
    </section>
  );
}

function StepRow({ step, index, active, onClick, floorName }: { step: GuideStep; index: number; active: boolean; onClick: () => void; floorName?: string }) {
  const isFloor = step.kind === "floor";
  return (
    <li>
      <button type="button" onClick={onClick} aria-current={active ? "step" : undefined} className="k-step" data-kind={step.kind} data-active={active}>
        <span className="k-step-icon"><Pictogram name={step.icon} size={18} /></span>
        <span className="k-step-body">
          <span className="k-step-text">{step.text}</span>
          {(step.metres > 0 || isFloor) && (
            <span className="k-step-meta">{index > 0 && step.metres > 0 ? `${Math.round(step.metres)} m` : ""}{isFloor && floorName ? ` · now on ${floorName}` : ""}</span>
          )}
        </span>
      </button>
    </li>
  );
}

function Conversation({ messages, busy, onOption, onDecide,geometry,onRoom,busyLabel,onResult,onRerun,suggest=[],onAsk,understood=[],currentlySpeakingId,onSpeakMessage }: {
  suggest?:string[];onAsk?:(q:string)=>void;understood?:string[];
  busyLabel:string;onResult:(r:VisualResult & {total_rows:number})=>void;onRerun:(q:string)=>void;
  geometry:NonNullable<ReturnType<typeof useNavigator>["geometry"]>;onRoom:(id:string)=>void;
  messages: Message[]; busy: boolean; onOption: (id: string, purpose?: string) => void; onDecide: (m: Extract<Message, { role: "change" }>, ok: boolean) => void;
  currentlySpeakingId?: number | null; onSpeakMessage?: (id: number, text: string) => void;
}) {
  const [history,setHistory]=useState(false);
  const end = useRef<HTMLDivElement>(null);
  const pinned=useRef(true),lastUser=useRef<number|null>(null);
  const [atBottom,setAtBottom]=useState(true);
  useEffect(()=>{const user=messages.filter(m=>m.role==='user').at(-1);if(user?.id!==lastUser.current){lastUser.current=user?.id??null;pinned.current=true;}const panel=end.current?.closest<HTMLElement>(".chat-workspace")??end.current?.parentElement;if(panel&&pinned.current)panel.scrollTop=panel.scrollHeight;},[messages,busy]);
  useEffect(()=>{const panel=end.current?.closest<HTMLElement>(".chat-workspace");if(!panel)return;const update=()=>{pinned.current=panel.scrollHeight-panel.scrollTop-panel.clientHeight<80;setAtBottom(pinned.current);};panel.addEventListener('scroll',update,{passive:true});return()=>panel.removeEventListener('scroll',update);},[messages.length,busy]);
  const turns=useMemo(()=>{
    const turns:Message[][]=[];
    messages.forEach(m=>{if(m.role==="user"||!turns.length)turns.push([]);turns[turns.length-1].push(m);});
    return turns;
  },[messages]);
  const shown=history?turns:turns.slice(-1);
  const visible=shown.flatMap(turn=>[
    ...turn.filter(m=>m.role==="user"),
    {role:"trace" as const,id:-(turn[0]?.id??1),activities:turn.filter((m):m is Extract<Message,{role:"activity"}>=>m.role==="activity"),busy:busy&&turn===turns.at(-1)},
    ...turn.filter(m=>m.role!=="activity"&&m.role!=="user"&&m.role!=="result"&&(m.role!=="agent"||m.text.trim())),
    {role:"results" as const,id:turn[0]?.id??0,results:turn.filter((m):m is Extract<Message,{role:"result"}>=>m.role==="result")}
  ]);
  if (!messages.length && !busy) return null;
  return (
    <section aria-label="Conversation" aria-live="off" className="conversation-scroll space-y-3 px-4 py-4">
      {turns.length>1&&<button className="conversation-history" aria-expanded={history} onClick={()=>setHistory(!history)}>{history?"Collapse history":`Earlier conversation (${turns.length-1} turn${turns.length===2?"":"s"})`}</button>}
      {visible.map((m) => {
        if(m.role==="trace")return <ToolTrace key={m.id} activities={m.activities} busy={m.busy}/>;
        if(m.role==='results')return <TurnResultLinks key={`results-${m.id}`} results={m.results} floors={geometry.floors} onResult={onResult} onRerun={onRerun} busy={busy}/>;
        if (m.role === "user") return <p key={m.id} className="ml-10 border-r-4 border-concrete pr-3 text-right text-[15.5px] text-concrete">{m.text}</p>;
        if (m.role === "error") return <p key={m.id} className="border-l-4 border-signal bg-ink-2 px-3 py-2 text-[14.5px]"><span>{m.text}</span>{m.query&&<button className="retry-answer" disabled={busy} onClick={()=>onRerun(m.query!)}>Try this question again</button>}</p>;
        if (m.role === "options")
          return (
            <div key={m.id}>
              <p className="text-[15.5px]">{m.text}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {m.options.map((o, i) => (
                  <button key={o.id} onClick={() => onOption(o.id, m.purpose)} className="k-ctl">
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
                  <button onClick={() => onDecide(m, true)} className="k-ctl accent">Apply to model</button>
                  <button onClick={() => onDecide(m, false)} className="k-ctl">Discard</button>
                </div>
              ) : <p className="mt-2 text-sm text-ink-4">{m.state === "applied" ? "Applied." : "Discarded."}</p>}
            </div>
          );
        if (m.role === "agent") {
          const isThisPlaying = currentlySpeakingId === m.id;
          return (
            <div key={m.id} className="space-y-1.5 text-[15.5px] leading-relaxed">
              {onSpeakMessage && m.text.trim() && (
                <button type="button" onClick={() => onSpeakMessage(m.id, m.text)} className="k-ctl" aria-pressed={isThisPlaying}
                  aria-label={isThisPlaying ? "Stop reading" : "Read answer aloud"}>
                  <Pictogram name="speaker" size={14} />{isThisPlaying ? "Stop" : "Read aloud"}
                </button>
              )}
              {m.status==='interrupted'&&<p role="status">Answer interrupted. Computed results remain available.</p>}
              <AgentReply text={m.text} spaces={geometry.spaces} onRoom={onRoom}/>
              {(m.streaming || m.status === "streaming") && <span className="inline-block h-4 w-1.5 animate-pulse bg-mark ml-1 align-middle" />}
            </div>
          );
        }
        return null;
      })}
      {busy&&<RequestStatus label={busyLabel}/>}
      {!busy&&understood.length>0&&messages.at(-1)?.role==="agent"&&<p className="k-understood" aria-label="How this was understood"><span>Understood as</span>{understood.map(u=><b key={u}>{u}</b>)}</p>}
      {!busy&&onAsk&&suggest.length>0&&messages.at(-1)?.role==="agent"&&<div className="k-next" aria-label="Ask next">{suggest.filter(q=>q!==(messages.filter(m=>m.role==="user").at(-1) as {text?:string}|undefined)?.text).slice(0,3).map(q=><button key={q} className="k-ctl" onClick={()=>onAsk(q)}>{q}</button>)}</div>}
      <p className="sr-only" aria-live="polite">{!busy&&messages.some(m=>m.role==='agent'&&m.status!=='streaming')?'New answer available in the conversation.':''}</p>
      <div ref={end} />
      {!atBottom&&<button type="button" className="k-jump" onClick={()=>end.current?.scrollIntoView({block:"end"})}><Pictogram name="jump" size={16}/>Jump to latest</button>}
    </section>
  );
}

function RequestStatus({label}:{label:string}) {const [seconds,setSeconds]=useState(0);useEffect(()=>{const start=performance.now();const timer=setInterval(()=>setSeconds(Math.floor((performance.now()-start)/1000)),1000);return()=>clearInterval(timer);},[]);return <p className="request-status" role="status"><span>{label}</span><small aria-hidden="true">{seconds}s{seconds>=20?' · You can stop this request.':''}</small></p>;}

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
    <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="k-composer">
      {voiceError && <p role="status" className="k-voice-error">{voiceError}</p>}
      {canListen() && (
        <button type="button" disabled={busy} aria-label={listening ? "Done speaking" : "Speak"} aria-pressed={listening}
          onClick={() => { if (listening) { stopListeningSession(true); } else { startListeningSession(); } }}
          className="k-ctl icon" data-live={listening}>
          <Pictogram name="mic" size={20} />
        </button>
      )}
      <textarea rows={1} maxLength={12000} value={text} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();submit(text);}}} onChange={(e) => {if(listening)stopListeningSession(false);setText(e.target.value);}} placeholder={listening ? "Listening…" : "Ask the building"}
        aria-label="Message" aria-describedby="composer-help" className="k-input" />
      <span id="composer-help" className="sr-only">Enter sends; Shift Enter adds a line. Maximum 12000 characters.</span>
      {busy&&<button type="button" className="k-ctl" onClick={onStop}>Stop</button>}
      <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
        className="k-ctl icon accent"><Pictogram name="send" size={18} /></button>
    </form>
  );
}

function StepMode({ steps, index, onIndex, onClose }: { steps: GuideStep[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const i = Math.max(0,Math.min(steps.length-1,index));
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

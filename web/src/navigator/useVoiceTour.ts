import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Space, VisualResult, Route } from "../lib/types";
import { audioStreamQueue, speak, stopSpeaking } from "../lib/voice";
import type { Message } from "./useNavigator";

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function findSpacesMentionedInText(
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

const ROUTE_WORDS = /\b(?:route|directions|way to|head to|walk to|take the|path|exit)\b/i;

type Step = { short?: string; text?: string };

export function useVoiceTour(o: {
  spaces: Space[] | undefined;
  messages: Message[];
  busy: boolean;
  visualResult: VisualResult | null;
  highlights: Set<string>;
  route: Route | null;
  setFloorId: (id: string) => void;
  following: boolean;
  steps: Step[];
  activeStep: number;
  focusRoom: (space: Space) => void;
  setFocusRequest: Dispatch<SetStateAction<{ id: string; revision: number } | null>>;
}) {
  const { spaces, messages, busy, visualResult, highlights, route, setFloorId, following, steps, activeStep, setFocusRequest } = o;
  const [voiceOut, setVoiceOut] = useState(true);
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceFocusSpace, setVoiceFocusSpace] = useState<Space | null>(null);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [currentlySpeakingId, setCurrentlySpeakingId] = useState<number | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const focusRef = useRef(o.focusRoom);
  focusRef.current = o.focusRoom;
  const on = voiceOut || voiceMode;

  const clearVoiceTour = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setVoiceFocusSpace(null);
    setFocusRequest(null);
  }, [setFocusRequest]);

  const focusRoom = useCallback((space: Space) => {
    setVoiceFocusSpace(space);
    focusRef.current(space);
  }, []);

  const tourRooms = useCallback((matched: Space[], totalDurationMs?: number) => {
    clearVoiceTour();
    if (!matched.length) return;
    if (matched.length === 1) { focusRoom(matched[0]); return; }
    const duration = totalDurationMs ?? Math.min(9000, Math.max(3000, matched.length * 2500));
    const interval = Math.max(1500, duration / matched.length);
    matched.forEach((space, i) => timers.current.push(setTimeout(() => focusRoom(space), i * interval)));
  }, [clearVoiceTour, focusRoom]);

  useEffect(() => {
    const start = () => setIsAgentSpeaking(true);
    const end = () => setIsAgentSpeaking(false);
    window.addEventListener("floorwise:speech-start", start);
    window.addEventListener("floorwise:speech-end", end);
    return () => { window.removeEventListener("floorwise:speech-start", start); window.removeEventListener("floorwise:speech-end", end); };
  }, []);

  useEffect(() => {
    const onChunk = (e: Event) => {
      if (!on || !spaces) return;
      const detail = (e as CustomEvent<{ text: string; audio?: HTMLAudioElement }>).detail;
      const text = detail?.text;
      if (!text) return;
      const matched = findSpacesMentionedInText(text, spaces, visualResult, highlights);
      if (matched.length) {
        const d = detail.audio?.duration;
        tourRooms(matched, d && isFinite(d) ? d * 1000 : Math.max(2500, text.length * 65));
      } else if (ROUTE_WORDS.test(text) && route?.polyline.length) {
        clearVoiceTour();
        setFloorId(route.polyline[0].floor_id);
      }
    };
    window.addEventListener("floorwise:speech-chunk", onChunk);
    window.addEventListener("floorwise:speech-end", clearVoiceTour);
    return () => {
      window.removeEventListener("floorwise:speech-chunk", onChunk);
      window.removeEventListener("floorwise:speech-end", clearVoiceTour);
      clearVoiceTour();
    };
  }, [on, spaces, visualResult, highlights, route, setFloorId, clearVoiceTour, tourRooms]);

  const lastProcessed = useRef<number | null>(null);
  useEffect(() => {
    if (!spaces) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "agent" || last.id === lastProcessed.current || last.status === "streaming") return;
    lastProcessed.current = last.id;
    const matched = findSpacesMentionedInText(last.text, spaces, visualResult, highlights);
    if (matched.length) tourRooms(matched);
    else if (ROUTE_WORDS.test(last.text) && route?.polyline.length) { clearVoiceTour(); setFloorId(route.polyline[0].floor_id); }
  }, [messages, spaces, visualResult, highlights, route, tourRooms, clearVoiceTour, setFloorId]);

  const lastSpoken = useRef<number | null>(null);
  useEffect(() => {
    if (!on) { lastSpoken.current = null; return; }
    const last = messages[messages.length - 1];
    if (!last || last.role !== "agent" || last.id === lastSpoken.current) return;
    if (last.status === "streaming" || busy) { if (audioStreamQueue.active) setCurrentlySpeakingId(last.id); return; }
    lastSpoken.current = last.id;
    if (audioStreamQueue.hadChunks) {
      if (audioStreamQueue.active) setCurrentlySpeakingId(last.id);
      audioStreamQueue.onEnd(() => setCurrentlySpeakingId(null));
    } else {
      setCurrentlySpeakingId(last.id);
      speak(last.text, () => setCurrentlySpeakingId(null));
    }
  }, [messages, busy, on]);

  const spokenFor = useRef<string | null>(null);
  useEffect(() => {
    if (!on) { spokenFor.current = null; return; }
    if (!route || following) return;
    const key = `${route.length_m}-${route.stops.join()}`;
    if (spokenFor.current === key) return;
    spokenFor.current = key;
    if (busy || audioStreamQueue.hadChunks || audioStreamQueue.active) return;
    speak(route.guide.spoken);
  }, [route, on, following, busy]);

  useEffect(() => {
    if (on && following && steps[activeStep]) speak(steps[activeStep].short ?? steps[activeStep].text ?? "");
    return () => { stopSpeaking(); };
  }, [on, following, activeStep]); // eslint-disable-line react-hooks/exhaustive-deps

  const silence = useCallback(() => { stopSpeaking(); audioStreamQueue.reset(); setCurrentlySpeakingId(null); clearVoiceTour(); }, [clearVoiceTour]);

  const toggleReadAloud = useCallback(() => {
    if (voiceOut) { silence(); setVoiceMode(false); }
    setVoiceOut(!voiceOut);
  }, [voiceOut, silence]);

  const toggleVoiceMode = useCallback(() => {
    if (voiceMode) { setVoiceMode(false); silence(); } else { setVoiceMode(true); setVoiceOut(true); }
  }, [voiceMode, silence]);

  const speakMessage = useCallback((id: number, text: string) => {
    if (currentlySpeakingId === id) { stopSpeaking(); setCurrentlySpeakingId(null); clearVoiceTour(); return; }
    setCurrentlySpeakingId(id);
    speak(text, () => setCurrentlySpeakingId(null));
    if (spaces) tourRooms(findSpacesMentionedInText(text, spaces, visualResult, highlights));
  }, [currentlySpeakingId, spaces, visualResult, highlights, tourRooms, clearVoiceTour]);

  const voiceHighlightId = voiceFocusSpace?.id ?? null;
  const activeHighlights = useMemo(() => {
    const set = new Set(highlights);
    if (voiceHighlightId) set.add(voiceHighlightId);
    return set;
  }, [highlights, voiceHighlightId]);

  return { voiceOut, voiceMode, toggleReadAloud, toggleVoiceMode, voiceFocusSpace, activeHighlights, currentlySpeakingId, speakMessage, isAgentSpeaking, clearVoiceTour };
}

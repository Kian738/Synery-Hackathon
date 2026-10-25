import { useEffect, useRef, useState } from "react";
import { demoLines, tightestDoor } from "../lib/demo";
import { stopSpeaking } from "../lib/voice";
import type { DemoScenario, Geometry, ScenarioReport, Space } from "../lib/types";

export interface DemoRequest { n: number; scenario: DemoScenario; opening?: Promise<void> }
export interface DemoStage { cut: boolean; responders: boolean; fix: boolean }
export interface DemoControls {
  geometry: Geometry;
  run: (space: Space) => Promise<ScenarioReport | undefined>;
  applyFix: () => Promise<ScenarioReport | undefined>;
  focus: (id: string) => void;
  live: () => { report: ScenarioReport | null; playing: boolean; done: boolean };
  narrate?: (text: string) => Promise<void>;
  onActive?: (on: boolean) => void;
  /** Stop and restore (Esc or the Stop button). */
  onStop?: () => void | Promise<void>;
}

const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

/** The scripted five-beat lesson: each beat is one spoken sentence and one visual, one after the other. The panel owns the state it drives. */
export function useDemoRun(demo: DemoRequest | null | undefined, ctl: DemoControls) {
  const [stage, setStage] = useState<DemoStage | null>(null);
  const [running, setRunning] = useState(false);
  const latest = useRef(ctl); latest.current = ctl;
  const [beat, setBeat] = useState(0);
  const [caption, setCaption] = useState("");
  const kill = useRef<() => void>(() => {});
  useEffect(() => {
    if (!demo) return;
    let dead = false;
    const c = () => latest.current;
    const until = async (ok: () => boolean) => { while (!dead && !ok()) await wait(100); };
    // The caption shows every sentence, so the story reads the same with the voice off.
    const say = async (text: string[]) => { for (const t of text) if (!dead) { setCaption(t); await c().narrate?.(t); } };
    kill.current = () => { if (dead) return; dead = true; stopSpeaking("narration"); setRunning(false); setStage(null); setBeat(0); setCaption(""); c().onActive?.(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") void c().onStop?.(); };
    window.addEventListener("keydown", onKey);
    (async () => {
      const g = c().geometry, room = g.spaces.find(s => s.id === demo.scenario.room_id);
      if (!room) return;
      c().onActive?.(true); setRunning(true); setStage({ cut: false, responders: false, fix: false }); setBeat(1); setCaption(`Fire in ${demo.scenario.room}.`);
      try {
        const solved = c().run(room);
        c().focus(room.id);
        if (demo.opening) await demo.opening; else await say([`Fire in ${demo.scenario.room}.`, `${demo.scenario.people} people are inside.`]);
        const report = await solved;
        if (dead || !report?.evacuation) return;
        const lines = demoLines(g, report, demo.scenario.room, demo.scenario.people);
        const line = (id: string) => lines.find(l => l.id === id)?.say;
        setBeat(2); await say(line("flow") ?? []);
        await until(() => c().live().done);
        if (dead) return;
        const door = tightestDoor(g, report);
        const focusOpening = (id?: string) => { const o = g.openings.find(x => x.id === id); const sp = o?.space_ids.find(x => x !== "outside"); if (sp) c().focus(sp); };
        if (door) { setBeat(3); setStage({ cut: true, responders: false, fix: false }); focusOpening(door.id); await say(line("cut") ?? []); }
        if (dead) return;
        if (line("responders")) { setBeat(4); setStage({ cut: true, responders: true, fix: false }); focusOpening(report.responder?.elements[0]); await say(line("responders")!); }
        const fix = report.answer?.fixes?.[0];
        if (dead) return;
        if (fix && line("fix")) {
          setBeat(5); setStage({ cut: true, responders: true, fix: true }); focusOpening(fix.element); await say(line("fix")!);
          // Never edit the model after the demo was stopped or the panel closed.
          if (dead) return;
          const after = await c().applyFix();
          if (!dead && after?.evacuation) await say([`Solved again: ${after.evacuation.T_s} seconds.`]);
        }
      } finally { if (!dead) { setRunning(false); setCaption(""); setBeat(0); c().onActive?.(false); } }
    })();
    return () => { window.removeEventListener("keydown", onKey); dead = true; stopSpeaking("narration"); setRunning(false); latestEnd(c); };
  }, [demo?.n]);
  useEffect(() => { kill.current = () => {}; }, []);
  return { stage, running, beat, beats: 5, caption, stop: () => kill.current(), reset: () => setStage(null) };
}
const latestEnd = (c: () => DemoControls) => c().onActive?.(false);

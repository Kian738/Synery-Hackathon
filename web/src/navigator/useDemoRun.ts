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
}

const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

/** The scripted five-beat lesson: each beat is one spoken sentence and one visual, one after the other. The panel owns the state it drives. */
export function useDemoRun(demo: DemoRequest | null | undefined, ctl: DemoControls) {
  const [stage, setStage] = useState<DemoStage | null>(null);
  const [running, setRunning] = useState(false);
  const latest = useRef(ctl); latest.current = ctl;
  useEffect(() => {
    if (!demo) return;
    let dead = false;
    const c = () => latest.current;
    const until = async (ok: () => boolean) => { while (!dead && !ok()) await wait(100); };
    const say = async (text: string[]) => { for (const t of text) if (!dead) await c().narrate?.(t); };
    (async () => {
      const g = c().geometry, room = g.spaces.find(s => s.id === demo.scenario.room_id);
      if (!room) return;
      c().onActive?.(true); setRunning(true); setStage({ cut: false, responders: false, fix: false });
      try {
        const solved = c().run(room);
        c().focus(room.id);
        if (demo.opening) await demo.opening; else await say([`Fire in ${demo.scenario.room}.`, `${demo.scenario.people} people are inside.`]);
        const report = await solved;
        if (dead || !report?.evacuation) return;
        const lines = demoLines(g, report, demo.scenario.room, demo.scenario.people);
        const line = (id: string) => lines.find(l => l.id === id)?.say;
        await say(line("flow") ?? []);
        await until(() => c().live().done);
        const door = tightestDoor(g, report);
        const focusOpening = (id?: string) => { const o = g.openings.find(x => x.id === id); const sp = o?.space_ids.find(x => x !== "outside"); if (sp) c().focus(sp); };
        if (door) { setStage({ cut: true, responders: false, fix: false }); focusOpening(door.id); await say(line("cut") ?? []); }
        if (line("responders")) { setStage({ cut: true, responders: true, fix: false }); focusOpening(report.responder?.elements[0]); await say(line("responders")!); }
        const fix = report.answer?.fixes?.[0];
        if (fix && line("fix")) {
          setStage({ cut: true, responders: true, fix: true }); focusOpening(fix.element); await say(line("fix")!);
          const after = await c().applyFix();
          if (after?.evacuation) await say([`Solved again: ${after.evacuation.T_s} seconds.`]);
        }
      } finally { if (!dead) { setRunning(false); c().onActive?.(false); } }
    })();
    return () => { dead = true; stopSpeaking(); setRunning(false); latestEnd(c); };
  }, [demo?.n]);
  return { stage, running, reset: () => setStage(null) };
}
const latestEnd = (c: () => DemoControls) => c().onActive?.(false);

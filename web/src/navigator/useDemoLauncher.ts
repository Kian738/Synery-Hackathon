import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { speak } from "../lib/voice";
import type { DemoScenario } from "../lib/types";
import type { DemoRequest } from "./useDemoRun";

const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

/** Run demo: fetch the prepared scenario, switch building through router state, open the panel, and narrate through speak() with Read aloud on. */
export function useDemoLauncher(o: { buildingId: string; geometryBuilding?: string; sessionReady: boolean; auto: boolean; setBuilding: (id: string) => void; openPanel: () => void; voiceOut: boolean; setVoiceOut: (on: boolean) => void }) {
  const [pending, setPending] = useState<DemoScenario | null>(null);
  const [demo, setDemo] = useState<DemoRequest | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(false);
  const latest = useRef(o); latest.current = o;
  const restore = useRef<boolean | null>(null);
  const switched = useRef(false);
  const onActive = useCallback((on: boolean) => {
    setActive(on);
    const c = latest.current;
    if (on) { if (restore.current === null) { restore.current = c.voiceOut; c.setVoiceOut(true); } }
    else if (restore.current !== null) { c.setVoiceOut(restore.current); restore.current = null; }
  }, []);
  /** One sentence at a time: resolves when the voice ends (or a generous cap), never sooner than 1.8 s. */
  const narrate = useCallback(async (text: string) => {
    const spoken = new Promise<void>(done => { speak(text, done); setTimeout(done, 4000 + text.length * 100); });
    await Promise.all([spoken, wait(1800)]);
  }, []);
  const [opener, setOpener] = useState<Promise<void> | undefined>();
  const start = useCallback(async () => {
    setError("");
    try {
      switched.current = false;
      const scenario = await api.demoScenario();
      // The first sentence starts now, while the building switches and the solver warms up.
      onActive(true);
      const opening = (async () => { await narrate(`Fire in ${scenario.room}.`); await narrate(`${scenario.people} people are inside.`); })();
      setPending(scenario); setOpener(opening);
    }
    catch (e) { setError(e instanceof Error ? e.message : "The demo scenario could not be loaded."); }
  }, []);
  useEffect(() => {
    if (!pending) return;
    if (o.buildingId !== pending.building_id) { if (!switched.current) { switched.current = true; o.setBuilding(pending.building_id); } return; }
    if (!o.sessionReady || o.geometryBuilding !== pending.building_id) return;
    o.openPanel(); setDemo(d => ({ n: (d?.n ?? 0) + 1, scenario: pending, opening: opener })); setPending(null);
  }, [pending, o.buildingId, o.sessionReady, o.geometryBuilding]);
  const auto = useRef(false);
  useEffect(() => { if (o.auto && !auto.current) { auto.current = true; void start(); } }, [o.auto]);
  return { start, demo, error, active, narrate, onActive };
}

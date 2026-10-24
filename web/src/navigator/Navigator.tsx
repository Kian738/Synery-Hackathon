import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { BuildDialog } from "../components/BuildDialog";
import { FloorRail } from "../components/FloorRail";
import { Pictogram } from "../components/Pictogram";
import { PlanView, type Pin } from "../components/PlanView";
import { api } from "../lib/api";
import { area, categories, centroid, label as labelOf, ZONE_LABEL, zoneOf } from "../lib/geometry";
import type { BuildingRow, GuideStep, Space } from "../lib/types";
import { canListen, listen, speak, stopSpeaking } from "../lib/voice";
import { entrances, type Message, useNavigator } from "./useNavigator";

const DEFAULT_BUILDING = "proc-campus-dev-000";
const Building3D = lazy(() => import("../components/Building3D"));

export default function Navigator() {
  const [params, setParams] = useSearchParams();
  const buildingId = params.get("building") ?? DEFAULT_BUILDING;
  const nav = useNavigator(buildingId);
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [selected, setSelected] = useState<Space | null>(null);
  const [voiceOut, setVoiceOut] = useState(false);
  const [stepMode, setStepMode] = useState(false);
  const [view, setView] = useState<"2d" | "3d" | "follow">(params.get("view") === "2d" ? "2d" : "3d");
  const [allFloors, setAllFloors] = useState(false);
  const [picking, setPicking] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [buildingImport, setBuildingImport] = useState(false);

  useEffect(() => { api.buildings().then(setBuildings).catch(() => {}); }, []);
  useEffect(() => { setSelected(null); setStepMode(false); }, [buildingId]);
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

  // Speak new agent replies and route overviews when voice output is on.
  const spokenFor = useRef<string | null>(null);
  useEffect(() => {
    if (!voiceOut || !nav.route) return;
    const key = `${nav.route.length_m}-${nav.route.stops.join()}`;
    if (spokenFor.current === key) return;
    spokenFor.current = key;
    speak(nav.route.guide.spoken);
  }, [nav.route, voiceOut]);

  const pins: Pin[] = useMemo(() => {
    if (!g) return [];
    const out: Pin[] = [];
    const at = (id: string) => g.spaces.find((s) => s.id === id);
    const here = nav.here ? at(nav.here) : null;
    if (here && !nav.route) out.push({ id: "here", at: centroid(here.polygon), floor_id: here.floor_id, label: `You are in ${here.name}`, tone: "start" });
    if (nav.route?.polyline.length) {
      const first = nav.route.polyline[0], last = nav.route.polyline[nav.route.polyline.length - 1];
      out.push({ id: "start", at: [first.x, first.y], floor_id: first.floor_id, label: "Start", tone: "start" });
      out.push({ id: "end", at: [last.x, last.y], floor_id: last.floor_id, label: "Destination", tone: "end" });
      const step = steps[nav.activeStep];
      if (step?.point && step.floor_id && nav.activeStep > 0 && step.kind !== "arrive")
        out.push({ id: "step", at: step.point, floor_id: step.floor_id, label: step.text, tone: "info", n: nav.activeStep });
    }
    return out;
  }, [g, nav.here, nav.route, nav.activeStep, steps]);

  const focusStep = (i: number) => {
    nav.setActiveStep(i);
    const s = steps[i];
    if (s?.floor_id) nav.setFloorId(s.floor_id);
  };
  const focusPoint = nav.route && nav.activeStep > 0 ? steps[nav.activeStep]?.point ?? null : null;

  if (!g) {
    return <div className="grid h-full place-items-center bg-ink font-sign text-xl text-concrete">{nav.notice ?? "Loading building…"}</div>;
  }

  return (
    <div className="navigator-shell flex h-full flex-col lg:flex-row">
      {/* ---------- sign column ---------- */}
      <aside className="order-2 flex min-h-0 flex-1 flex-col navigation-panel bg-ink text-white lg:order-1 lg:w-[370px] lg:flex-none">
        <header className="flex items-center gap-2 border-b border-ink-2 px-4 py-3">
          <BuildingPicker buildings={buildings} value={buildingId} onChange={(b) => setParams({ building: b })} name={g.building.name} />
          <button onClick={() => setBuildingImport(true)} className="ml-auto text-sm text-concrete">Import plan</button>
        </header>

        <div className="flex flex-wrap items-center gap-2 border-b border-ink-2 px-4 py-2.5">
          <Toggle on={nav.stepFree} onClick={() => nav.setStepFree(!nav.stepFree)} icon="wheelchair" label="Step-free" tone="escape" />
          <Toggle on={voiceOut} onClick={() => { setVoiceOut(!voiceOut); if (voiceOut) stopSpeaking(); }} icon="speaker" label="Read aloud" tone="mark" />
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
          {picking && (
            <StartPicker geometry={g} onPick={(id) => { nav.setHere(id); setPicking(false); nav.setNotice(null); }} />
          )}
        </div>

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {nav.route && (
            <RouteSign route={nav.route} meta={nav.routeMeta} stepFree={nav.route.constraints.includes("step-free")}
              active={nav.activeStep} onStep={focusStep} onClear={nav.clearRoute} onStepMode={() => { setView("follow"); nav.setActiveStep(0); }} floors={g.floors} />
          )}
          {!nav.route && nav.messages.length === 0 && (
            <Welcome categories={cats} onPick={(q) => nav.goTo(q)} onAsk={nav.ask} hasHere={!!nav.here} buildingName={g.building.name} examples={examples} />
          )}
          <Conversation messages={nav.messages} busy={nav.busy} onOption={(id) => nav.goTo(id)} onDecide={nav.decideChange} />
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
        <Composer busy={nav.busy} onSend={nav.ask} />
      </aside>

      <main className="model-panel relative order-1 flex h-[46vh] shrink-0 lg:order-2 lg:h-auto lg:flex-1">
        <div className="model-toolbar">
          <div className="mode-switch" aria-label="View mode">
            <button aria-pressed={view === "3d"} onClick={() => setView("3d")}>3D</button>
            <button aria-pressed={view === "2d"} onClick={() => setView("2d")}>Floor plan</button>
            <button disabled={!nav.route || nav.route.preview_available === false} aria-pressed={view === "follow"} onClick={() => setView("follow")}>Follow route</button>
          </div>
          <div className="model-actions">
            {view === "3d" && <button aria-pressed={allFloors} onClick={() => setAllFloors(!allFloors)}>All floors</button>}
            <button disabled={nav.busy} onClick={nav.inspectWeakPoints}>Test weak points</button>
            <Link to="/lab">Evidence</Link>
          </div>
        </div>
        <div className="floor-selector"><FloorRail floors={g.floors} active={nav.floorId} route={nav.route} onPick={nav.setFloorId} here={hereFloor} /></div>
        <div className="model-viewport">
          <ErrorBoundary key={`${g.building.id}-${view}`} label="The building view needs recovery">
            {view === "2d" ? <PlanView geometry={g} floorId={nav.floorId} route={nav.route} highlights={nav.highlights} closed={nav.closed}
              pins={pins} previewDoor={nav.previewDoor} selected={selected?.id} focus={focusPoint} onSpaceClick={setSelected} /> :
              <Suspense fallback={<div className="recovery">Preparing the building model...</div>}>
                <Building3D geometry={g} floorId={nav.floorId} route={nav.route} previousRoute={nav.previousRoute} highlights={nav.highlights}
                  closed={nav.closed} previewDoor={nav.previewDoor} showAll={allFloors} follow={view === "follow"} activeStep={nav.activeStep}
                  onStep={focusStep} onSpaceClick={setSelected} />
              </Suspense>}
          </ErrorBoundary>
        </div>
        {!nav.notice && nav.route?.warnings?.length ? <div className="model-notice" role="status">{nav.route.warnings.join(" ")}</div> : null}
        {nav.notice && <div role="status" className="model-notice"><span>{nav.notice}</span><button aria-label="Dismiss" onClick={() => nav.setNotice(null)}>×</button></div>}
        {view === "follow" && nav.route && <div className="follow-instruction"><span>Waypoint {nav.activeStep + 1} / {steps.length}</span><p>{steps[nav.activeStep]?.text}</p></div>}
        {nav.weakPoints.length > 0 && view !== "follow" && <section className="weak-points" aria-label="Weak points">
          <h2>Single closure simulation</h2>
          {nav.weakPoints.map((item, i) => <button key={i} onClick={() => {nav.setHighlights(new Set(item.room_ids));const room=g.spaces.find(s=>s.id===item.room_ids[0]);if(room)nav.setFloorId(room.floor_id);}}>
            <b>{item.name}</b><span>{item.rooms_lost} of {item.of_rooms} rooms would lose step-free exit access</span>
          </button>)}
        </section>}
        {selected && <RoomCard space={selected} building={g} onClose={() => setSelected(null)} closed={nav.closed}
          onHere={() => { nav.setHere(selected.id); setSelected(null); nav.setNotice(null); }}
          onGo={() => { nav.goTo(selected.id); setSelected(null); }} onToggleClosed={nav.toggleClosed} />}
        {stepMode && nav.route && <StepMode steps={steps} index={nav.activeStep} onIndex={focusStep} onClose={() => {setStepMode(false);stopSpeaking();}} />}
      </main>
      {buildingImport && <BuildDialog onClose={() => setBuildingImport(false)} onBuilt={id => {setBuildingImport(false);setParams({building:id});api.buildings().then(setBuildings);}} />}

    </div>
  );
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
      <span className="font-sign text-[22px] font-bold leading-tight tracking-tight">{name}</span>
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
      <p className="mt-6 font-sign text-sm text-ink-4">Things you can say</p>
      <ul className="mt-2 space-y-1.5">
        {examples.map((t) => (
          <li key={t}><button onClick={() => onAsk(t)} className="text-left text-[15px] text-concrete underline decoration-ink-3 underline-offset-4 hover:decoration-mark">“{t}”</button></li>
        ))}
      </ul>
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
          <span className="font-semibold">{Math.round(route.walk_m ?? route.length_m)} m walk</span>
          <span>about {minutes} min</span>
          {floorChanges > 0 && <span>{floorChanges} floor change{floorChanges > 1 ? "s" : ""}</span>}
          {stepFree && <span className="flex items-center gap-1 text-[#7fd4a8]"><Pictogram name="wheelchair" size={15} /> step-free</span>}
          {route.constraints.filter((c) => c !== "step-free").map((c) => <span key={c} className="text-mark">{c}</span>)}
        </p>
        {outside && <p className="mt-1.5 text-sm text-mark">No indoor connection: this route goes outside between two entrances.</p>}
        {meta?.alternatives?.length ? (
          <p className="mt-1.5 text-sm text-ink-4">Nearest match. Also: {meta.alternatives.map((a) => `${a.room} (${a.walk_m} m)`).join(", ")}</p>
        ) : null}
      </div>
      <ol className="divide-y divide-ink-2">
        {steps.map((s, i) => (
          <StepRow key={i} step={s} index={i} active={i === active} onClick={() => onStep(i)} floorName={floors.find((f) => f.id === s.floor_id)?.name} />
        ))}
      </ol>
      <div className="flex gap-2 px-4 py-3">
        <button disabled={route.preview_available === false} onClick={onStepMode} className="flex-1 bg-mark py-2.5 font-sign text-[17px] font-bold text-ink hover:brightness-95">{route.preview_available === false ? "Preview unavailable: check geometry" : "Start step by step"}</button>
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

function Conversation({ messages, busy, onOption, onDecide }: {
  messages: Message[]; busy: boolean; onOption: (id: string) => void; onDecide: (m: Extract<Message, { role: "change" }>, ok: boolean) => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { const panel = end.current?.parentElement; if (panel) panel.scrollTop = panel.scrollHeight; }, [messages, busy]);
  if (!messages.length && !busy) return null;
  return (
    <section aria-label="Conversation" aria-live="polite" style={{maxHeight:320,overflowY:"auto"}} className="space-y-3 px-4 py-4">
      {messages.map((m) => {
        if (m.role === "user") return <p key={m.id} className="ml-10 border-r-4 border-concrete pr-3 text-right text-[15.5px] text-concrete">{m.text}</p>;
        if (m.role === "activity") return <p key={m.id} className="flex items-center gap-2 text-[13px] text-ink-4"><span className="h-1.5 w-1.5 bg-ink-3" />{m.text}</p>;
        if (m.role === "error") return <p key={m.id} className="border-l-4 border-signal bg-ink-2 px-3 py-2 text-[14.5px]">{m.text}</p>;
        if (m.role === "options")
          return (
            <div key={m.id}>
              <p className="text-[15.5px]">{m.text}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {m.options.map((o, i) => (
                  <button key={o.id} onClick={() => onOption(o.id)} className="flex items-center gap-2 border border-white px-3 py-1.5 font-sign text-[15px] hover:bg-white hover:text-ink">
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
        return (
          <div key={m.id} className="space-y-1.5 text-[15.5px] leading-relaxed">
            {m.text.split("\n").filter(Boolean).map((line, i) => <p key={i}>{line.replace(/\*\*/g, "")}</p>)}
          </div>
        );
      })}
      {busy && <p className="flex items-center gap-2 text-[13px] text-ink-4"><span className="h-1.5 w-1.5 animate-pulse bg-mark" />Working…</p>}
      <div ref={end} />
    </section>
  );
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const stopListening = useRef<(() => void) | null>(null);
  useEffect(() => () => {stopListening.current?.();}, []);
  const submit = (value: string) => {
    const t = value.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="relative flex gap-2 border-t border-ink-2 p-3">
      {voiceError && <p role="status" className="absolute bottom-full left-0 right-0 bg-ink-2 p-3 text-sm">{voiceError}</p>}
      {canListen() && (
        <button type="button" disabled={busy} aria-label={listening ? "Stop listening" : "Speak"} aria-pressed={listening}
          onClick={() => { if (listening) {stopListening.current?.();setListening(false);return;} setVoiceError("");setListening(true);stopListening.current=listen(setText, (t) => { setListening(false); submit(t); }, () => setListening(false), setVoiceError); }}
          className={`grid h-12 w-12 shrink-0 place-items-center ${listening ? "bg-signal text-white" : "bg-white text-ink hover:bg-concrete"}`}>
          <Pictogram name="mic" size={22} />
        </button>
      )}
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Ask the building"}
        aria-label="Message" className="h-12 min-w-0 flex-1 border border-ink-3 bg-ink-2 px-3 text-[16px] text-white placeholder:text-ink-4 focus:border-white focus:outline-none" />
      <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
        className="grid h-12 w-12 shrink-0 place-items-center bg-mark text-ink disabled:opacity-40"><Pictogram name="send" size={20} /></button>
    </form>
  );
}

function RoomCard({ space, building, onClose, onHere, onGo, closed, onToggleClosed }: {
  space: Space; building: NonNullable<ReturnType<typeof useNavigator>["geometry"]>; onClose: () => void; onHere: () => void; onGo: () => void;
  closed: Set<string>; onToggleClosed: (id: string) => void;
}) {
  const items = building.assets.filter((a) => a.space_id === space.id);
  const counts = Object.entries(items.reduce<Record<string, number>>((m, a) => ({ ...m, [a.type]: (m[a.type] ?? 0) + 1 }), {})).slice(0, 6);
  const connector = building.connectors.find((c) => c.space_ids.includes(space.id));
  const floor = building.floors.find((f) => f.id === space.floor_id);
  return (
    <div className="absolute inset-x-3 bottom-3 border border-ink bg-white p-4 shadow-[4px_4px_0_var(--color-ink)] sm:left-auto sm:right-16 sm:w-[340px]" role="dialog" aria-label={space.name}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] text-ink-3">{ZONE_LABEL[zoneOf(space)]} · {floor?.name}</p>
          <h3 className="font-sign text-[22px] font-bold leading-tight">{space.name}</h3>
          <p className="text-[14px] text-ink-3">{area(space.polygon).toFixed(0)} m²{space.ref && !space.name.includes(space.ref) ? ` · ${space.ref}` : ""}</p>
        </div>
        <button onClick={onClose} aria-label="Close"><Pictogram name="close" size={20} /></button>
      </div>
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
  useEffect(() => { if (step) speak(step.text); }, [step]);
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
  const options = query.trim()
    ? geometry.spaces.filter((x) => `${x.name} ${x.ref ?? ""}`.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : entrances(geometry).slice(0, 6);
  return (
    <div className="mt-2 space-y-1.5">
      <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Room name or number"
        aria-label="Search for your room" className="h-10 w-full border border-ink-3 bg-ink-2 px-3 text-white placeholder:text-ink-4 focus:border-white focus:outline-none" />
      <p className="text-[13px] text-ink-4">{query ? "Matching rooms" : "Entrances, or tap your room on the plan"}</p>
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

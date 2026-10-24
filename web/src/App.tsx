import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, chatStream } from "./api";
import { BuildDialog } from "./components/BuildDialog";
import { ChatPanel, toolLabel } from "./components/ChatPanel";
import { FloorPlan, StackView } from "./components/FloorPlan";
import type { BuildingRow, ChatItem, Geometry, Opening, Profile, Route, Space, UiEvent } from "./types";

const params = new URLSearchParams(window.location.search);
const DEFAULT_BUILDING = params.get("building") ?? "proc-factory-dev-003";
let nextId = 1;

export default function App() {
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [buildingId, setBuildingId] = useState(DEFAULT_BUILDING);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [floorId, setFloorId] = useState<string>("");
  const [mode, setMode] = useState<"plan" | "stack">(params.get("mode") === "stack" ? "stack" : "plan");
  const [route, setRoute] = useState<Route | null>(null);
  const [highlights, setHighlights] = useState<Set<string>>(new Set());
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string[]>([]);
  const [previewDoor, setPreviewDoor] = useState<Opening | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [stepFree, setStepFree] = useState(false);
  const [showItems, setShowItems] = useState(true);
  const [hover, setHover] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [voiceOut, setVoiceOut] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const routeFloorAuto = useRef(true);

  const add = (item: Omit<ChatItem, "id">) => setItems((all) => [...all, { ...item, id: nextId++ }]);

  useEffect(() => { api.buildings().then(setBuildings).catch((e) => setNotice(String(e))); }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { session_id } = await api.newSession(buildingId);
      const g = await api.geometry(session_id);
      if (cancelled) return;
      setSessionId(session_id);
      setGeometry(g);
      setFloorId([...g.floors].sort((a, b) => Math.abs(a.level) - Math.abs(b.level))[0].id);
      setRoute(null); setHighlights(new Set()); setClosed(new Set()); setSelected([]); setItems([]); setPreviewDoor(null);
      setProfile(null);
      // Deep link: ?from=<room>&to=<room>[&step_free=1] opens with the route drawn (shareable, QR-at-door).
      const from = params.get("from"), to = params.get("to");
      if (from && to && buildingId === DEFAULT_BUILDING) {
        const { events } = await api.route(session_id, { start: from, destination: to, step_free: params.get("step_free") === "1" });
        if (!cancelled) for (const e of events) if (e.type === "route") { setRoute(e.route); setFloorId(e.route.polyline[0].floor_id); }
      }
    })().catch((e) => setNotice(String(e)));
    return () => { cancelled = true; };
  }, [buildingId]);

  const refreshGeometry = useCallback(async () => {
    if (sessionId) setGeometry(await api.geometry(sessionId));
  }, [sessionId]);

  /** Apply UI events from the agent or from direct map actions to the view. */
  const applyEvents = useCallback((events: UiEvent[]) => {
    for (const event of events) {
      if (event.type === "route") {
        setRoute(event.route);
        setPreviewDoor(null);
        if (routeFloorAuto.current && event.route.polyline.length) setFloorId(event.route.polyline[0].floor_id);
      } else if (event.type === "highlight") {
        setHighlights(new Set(event.ids));
        if (geometry && event.ids.length) {
          const first = geometry.spaces.find((s) => s.id === event.ids[0]) ?? geometry.assets.find((a) => a.id === event.ids[0]);
          if (first) setFloorId(first.floor_id);
        }
      } else if (event.type === "closure") {
        setClosed((c) => { const n = new Set(c); event.closed ? n.add(event.id) : n.delete(event.id); return n; });
      } else if (event.type === "preview_door") {
        setPreviewDoor(event.door);
        setFloorId(event.door.floor_id);
      } else if (event.type === "edit") {
        setPreviewDoor(null);
        refreshGeometry();
      } else if (event.type === "profile") {
        setProfile(event.profile);
        if (event.profile.step_free) setStepFree(true);
      }
    }
  }, [geometry, refreshGeometry]);

  const send = async (text: string) => {
    if (!sessionId) return;
    add({ role: "user", text });
    setBusy(true);
    try {
      await chatStream(sessionId, text, (event) => {
        if (event.type === "tool") {
          const { name, input } = event.data;
          if (name === "find_route") {
            const constraints = [
              input.step_free ? "step-free" : null,
              input.min_door_width_m ? `doors ≥ ${input.min_door_width_m} m` : null,
              ...((input.avoid as string[]) ?? []).map((a) => `avoid ${a}`),
              ...((input.prefer_avoid as string[]) ?? []).map((a) => `prefer to avoid ${a}`),
              input.avoid_stairs ? "no stairs" : null,
            ].filter(Boolean);
            const via = (input.via as string[] | undefined)?.length ? ` via ${(input.via as string[]).join(", ")}` : "";
            add({ role: "understood", text: `${input.start} → ${input.destination}${via}`, data: { constraints } });
          } else {
            add({ role: "tool", text: toolLabel(name, input) });
          }
        } else if (event.type === "ui") {
          applyEvents([event.data]);
          if (event.data.type === "preview_door") {
            const impact = event.data.impact;
            add({
              role: "preview",
              text: `New door between ${event.data.door.space_ids.map(nameOf).join(" and ")}. ${impact.shorter_way_out_count} rooms get a shorter way out.`,
              data: { first: event.data.door.space_ids[0], second: event.data.door.space_ids[1], applied: false },
            });
          }
        } else if (event.type === "reply") {
          add({ role: "agent", text: event.data.text });
        } else if (event.type === "error") {
          add({ role: "error", text: event.data.message });
        }
      });
    } catch (e) {
      add({ role: "error", text: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const nameOf = (id: string) => geometry?.spaces.find((s) => s.id === id)?.name ?? id;

  const applyPreview = async (data: any) => {
    setItems((all) => all.map((i) =>
      i.role === "preview" && i.data.first === data.first && i.data.second === data.second
        ? { ...i, data: { ...i.data, applied: true } }
        : i));
    if (data.cancel) { setPreviewDoor(null); add({ role: "tool", text: "Change discarded" }); return; }
    if (!sessionId) return;
    const { result, events } = await api.door(sessionId, data.first, data.second, true);
    applyEvents(events);
    add({ role: "tool", text: `Door added (${result.added})` });
  };

  const onSpaceClick = async (space: Space) => {
    if (!sessionId) return;
    const next = selected.length >= 2 ? [space.id] : [...selected, space.id];
    setSelected(next);
    if (next.length === 2) {
      try {
        const { result, events } = await api.route(sessionId, { start: next[0], destination: next[1], step_free: stepFree });
        if (result.error) setNotice(result.error);
        routeFloorAuto.current = false;
        applyEvents(events);
        routeFloorAuto.current = true;
      } catch (e) {
        setNotice(String(e));
      }
    }
  };

  const toggleConnector = async (id: string) => {
    if (!sessionId) return;
    const { result, events } = await api.close(sessionId, id, !closed.has(id));
    applyEvents(events);
    const impact = result.impact;
    setNotice(
      `${result.element} ${result.closed ? "closed" : "reopened"}: ${impact.cut_off_count} rooms cut off from exits, ` +
      `${impact.longer_way_out_count} with a longer way out.`,
    );
  };

  const floors = useMemo(() => (geometry ? [...geometry.floors].sort((a, b) => b.level - a.level) : []), [geometry]);
  const grouped = useMemo(() => {
    const bySplit: Record<string, BuildingRow[]> = {};
    for (const b of buildings) (bySplit[b.split] ??= []).push(b);
    return bySplit;
  }, [buildings]);

  if (!geometry) return <div className="loading">Loading building…{notice && <p>{notice}</p>}</div>;

  const layerProps = { geometry, route, highlights, closed, selected, previewDoor, showItems, onSpaceClick, onHover: setHover };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo">◆</span> Floorwise</div>
        <select value={buildingId} onChange={(e) => setBuildingId(e.target.value)}>
          {Object.entries(grouped).map(([split, rows]) => (
            <optgroup key={split} label={split}>
              {rows.map((b) => <option key={b.building_id} value={b.building_id}>{b.name} · {b.building_id}</option>)}
            </optgroup>
          ))}
        </select>
        <div className="segmented">
          <button className={mode === "plan" ? "on" : ""} onClick={() => setMode("plan")}>Plan</button>
          <button className={mode === "stack" ? "on" : ""} onClick={() => setMode("stack")}>3D stack</button>
        </div>
        <label className="toggle"><input type="checkbox" checked={stepFree} onChange={(e) => setStepFree(e.target.checked)} /> Step-free</label>
        <label className="toggle"><input type="checkbox" checked={showItems} onChange={(e) => setShowItems(e.target.checked)} /> Items</label>
        {profile?.step_free && <span className="chip accent">Remembered: step-free</span>}
        <button className="ghost" onClick={() => setBuilding(true)}>+ From floor plans</button>
      </header>
      <main className="main">
        <ChatPanel items={items} busy={busy} onSend={send} onApplyPreview={applyPreview} voiceOut={voiceOut} setVoiceOut={setVoiceOut} />
        <section className="map">
          <nav className="floor-tabs">
            {floors.map((f) => (
              <button key={f.id} className={f.id === floorId ? "on" : ""} onClick={() => setFloorId(f.id)}>
                {f.name}{route?.floors.includes(f.id) && <span className="dot" />}
              </button>
            ))}
          </nav>
          {mode === "plan" ? (
            <FloorPlan {...layerProps} floorId={floorId} />
          ) : (
            <StackView {...layerProps} activeFloorId={floorId} onPickFloor={(id) => { setFloorId(id); setMode("plan"); }} />
          )}
          <div className="hint">{hover ?? (selected.length === 1 ? "Now click the destination" : "Click two rooms to route between them · scroll to zoom · drag to pan")}</div>
          {notice && <div className="notice" onClick={() => setNotice(null)}>{notice}</div>}
          <div className="side-cards">
            {route && (
              <div className="card route-card">
                <div className="card-head">
                  <strong>{route.length_m.toFixed(1)} m</strong>
                  <button className="link" onClick={() => { setRoute(null); setSelected([]); }}>Clear</button>
                </div>
                {route.constraints.length > 0 && <div className="chips">{route.constraints.map((c) => <span key={c} className="chip">{c}</span>)}</div>}
                <ol>{route.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </div>
            )}
            {geometry.connectors.length > 0 && (
              <div className="card">
                <strong>Lifts & stairs</strong>
                <div className="connector-list">
                  {geometry.connectors.map((c) => (
                    <button key={c.id} className={`connector${closed.has(c.id) ? " closed" : ""}`} onClick={() => toggleConnector(c.id)} title={closed.has(c.id) ? "Reopen" : "Close for maintenance"}>
                      <span>{c.kind === "lift" ? "⇅" : "▤"}</span>{c.name}{closed.has(c.id) && <em>closed</em>}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
      {building && (
        <BuildDialog
          onClose={() => setBuilding(false)}
          onBuilt={async (id, report) => {
            setBuilding(false);
            setBuildings(await api.buildings());
            setBuildingId(id);
            setNotice(`Built ${report.floors} floors: ${report.rooms} rooms, ${report.doors} doors, ${report.stairs_and_lifts} stairs/lifts` +
              (report.unreachable_from_entrances.length ? ` · unreachable: ${report.unreachable_from_entrances.slice(0, 3).join(", ")}` : " · every space reachable"));
          }}
        />
      )}
    </div>
  );
}

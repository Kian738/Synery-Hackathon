import { useState } from "react";
import { Pictogram } from "../components/Pictogram";
import { IconButton } from "../ui/kit";
import { floorColor } from "../lib/floorColors";
import { area } from "../lib/geometry";
import { kindOf, ROOM_KIND } from "../lib/roomKinds";
import type { Geometry, Space } from "../lib/types";

/** Panels of the left column and the room popup, on the control kit (kit.css): same height, radius and gap as every other control. */

const levelOf = (g: Geometry, floorId: string) => g.floors.find(f => f.id === floorId);

export function RoomCard({ space, building, onClose, onHere, onGo, closed, onToggleClosed, onFocus }: {
  space: Space; building: Geometry; onClose: () => void; onHere: () => void; onGo: () => void;
  closed: Set<string>; onToggleClosed: (id: string) => void; onFocus: () => void;
}) {
  const items = building.assets.filter(a => a.space_id === space.id);
  const counts = Object.entries(items.reduce<Record<string, number>>((m, a) => ({ ...m, [a.type]: (m[a.type] ?? 0) + 1 }), {}));
  const connector = building.connectors.find(c => c.space_ids.includes(space.id));
  const floor = levelOf(building, space.floor_id);
  const kind = ROOM_KIND[kindOf(space)];
  const isClosed = !!connector && closed.has(connector.id);
  return (
    <div className="room-inspector k-room" role="dialog" aria-label={space.name}>
      <div className="k-room-head">
        <span className="k-room-chip" style={{ background: kind.scene }} title={kind.label} aria-hidden="true" />
        <div className="k-room-title">
          <h3>{space.name}</h3>
          <p><i style={{ background: floorColor(floor?.level ?? 0) }} aria-hidden="true" />{floor?.name} · {kind.label} · {area(space.polygon).toFixed(1)} m²</p>
        </div>
        <button type="button" className="k-ctl icon" aria-label="Close" onClick={onClose}><Pictogram name="close" size={18} /></button>
      </div>
      <div className="k-room-actions">
        <button type="button" className="k-ctl accent" onClick={onGo}><Pictogram name="arrive" size={18} />Go here</button>
        <button type="button" className="k-ctl" onClick={onHere}><Pictogram name="here" size={18} />I'm here</button>
        <button type="button" className="k-ctl icon" aria-label="Focus room" title="Focus room" onClick={onFocus}><Pictogram name="fit" size={18} /></button>
      </div>
      <details className="room-card-details k-room-more"><summary>Room details</summary>
        {counts.length > 0
          ? <p>{counts.slice(0, 6).map(([t, n]) => `${n} ${t.replace(/_/g, " ")}`).join(" · ")}</p>
          : <p>No equipment recorded here.</p>}
        {counts.length > 6 && <details><summary>All {counts.length} item types</summary>{counts.map(([t, n]) => <p key={t}>{n} {t.replaceAll("_", " ")}</p>)}</details>}
      </details>
      {connector && (
        <button type="button" className="k-ctl k-room-close" aria-pressed={isClosed} onClick={() => onToggleClosed(connector.id)}>
          {isClosed ? `Reopen ${connector.name}` : `Close ${connector.name} for maintenance`}
        </button>
      )}
    </div>
  );
}

export function StartPicker({ geometry, entrances, onPick }: { geometry: Geometry; entrances: (g: Geometry) => Space[]; onPick: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLocaleLowerCase();
  const matches = normalized
    ? geometry.spaces.filter(x => `${x.name} ${x.ref ?? ""} ${levelOf(geometry, x.floor_id)?.name ?? ""}`.toLocaleLowerCase().includes(normalized))
    : entrances(geometry);
  const options = matches.slice(0, 8);
  return (
    <div className="k-picker">
      <label className="k-search"><Pictogram name="search" size={16} />
        <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Room name or number" aria-label="Search for your room" /></label>
      <p role="status" className="k-hint">{normalized ? `${matches.length} matching rooms` : "Entrances, or tap your room on the plan"}{matches.length > options.length ? ` · Showing ${options.length} of ${matches.length}. Keep typing to narrow the list.` : ""}</p>
      <div className="k-picker-list">
        {options.map(x => (
          <button key={x.id} type="button" className="k-brow" onClick={() => onPick(x.id)}>
            <span className="k-brow-name"><i style={{ background: floorColor(levelOf(geometry, x.floor_id)?.level ?? 0) }} aria-hidden="true" />{x.name}</span>
            {geometry.floors.length > 1 && <span className="k-brow-meta">{levelOf(geometry, x.floor_id)?.name}</span>}
          </button>
        ))}
        {!options.length && <p className="k-hint">No room matches that.</p>}
      </div>
    </div>
  );
}

export function Welcome({ categories: cats, onPick, onAsk, hasHere, buildingName, examples, onDemo }: {
  onDemo?: () => void;
  categories: { key: string; label: string; query: string; icon: string }[];
  onPick: (q: string) => void; onAsk: (t: string) => void; hasHere: boolean; buildingName: string; examples: string[];
}) {
  return (
    <section className="welcome-panel k-welcome">
      <h1>Know your building.<br />Find your way.</h1>
      <p>{hasHere ? "Pick a place, or just ask." : `Explore ${buildingName}, or describe where you want to go.`}</p>
      {onDemo && <IconButton accent label="Run demo" text="Run demo" icon="focus" onClick={onDemo} />}
      {cats.length > 0 && (
        <div className="destination-shortcuts k-chips">
          {cats.slice(0, 6).map(c => (
            <button key={c.key} type="button" className="k-ctl" onClick={() => onPick(c.query)}><Pictogram name={c.icon} size={18} />{c.label}</button>
          ))}
        </div>
      )}
      <details className="example-requests k-examples"><summary>Things you can say</summary>
        <ul>{examples.map(t => <li key={t}><button type="button" onClick={() => onAsk(t)}>“{t}”</button></li>)}</ul>
      </details>
    </section>
  );
}

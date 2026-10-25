import { useEffect, useMemo, useRef, useState } from "react";
import { Pictogram } from "./Pictogram";
import type { BuildingRow } from "../lib/types";

/** The Building Atlas: every building as a card with a generated isometric floor stack. Search, kind chips, recents, keyboard.
 *  Kinds come from the dataset source (campus / hall / residential); thumbnails load lazily from /api/buildings/{id}/thumb.svg. */
const KINDS: { key: string; label: string; icon: string; test: (b: BuildingRow) => boolean }[] = [
  { key: "campus", label: "Campus", icon: "meeting", test: b => /campus|osm|institut|lehr|labor|forsch|hörsaal/i.test(`${b.building_id} ${b.name} ${b.source}`) },
  { key: "factory", label: "Halls", icon: "machine", test: b => /factory|fertig|werk|halle|produkt/i.test(`${b.building_id} ${b.name}`) },
  { key: "home", label: "Residential", icon: "bed", test: b => /swiss|resplan|resid|wohn/i.test(`${b.building_id} ${b.name} ${b.source}`) },
];
const kindOf = (b: BuildingRow) => KINDS.find(k => k.test(b))?.key ?? "other";

export function BuildingAtlas({ buildings, value, recent, onPick, onClose }: {
  buildings: BuildingRow[]; value: string; recent: string[]; onPick: (id: string) => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = buildings.filter(b => (!kind || kindOf(b) === kind) && (!q || `${b.name} ${b.building_id} ${b.source}`.toLowerCase().includes(q)));
    const rank = (b: BuildingRow) => (b.building_id === value ? -2 : recent.includes(b.building_id) ? -1 : 0);
    return [...rows].sort((a, b) => rank(a) - rank(b));
  }, [buildings, query, kind, recent, value]);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => setCursor(0), [query, kind]);
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); setCursor(c => Math.min(list.length - 1, c + (e.key === "ArrowDown" ? 2 : 1))); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); setCursor(c => Math.max(0, c - (e.key === "ArrowUp" ? 2 : 1))); }
    if (e.key === "Enter" && list[cursor]) { e.preventDefault(); onPick(list[cursor].building_id); }
  };
  useEffect(() => { document.querySelector<HTMLElement>(`[data-atlas-index="${cursor}"]`)?.scrollIntoView({ block: "nearest" }); }, [cursor]);
  const surprise = () => { const pool = buildings.filter(b => b.building_id !== value); if (pool.length) onPick(pool[Math.floor(Math.random() * pool.length)].building_id); };
  return (
    <div className="k-atlas" role="dialog" aria-label="Building atlas" onKeyDown={key}>
      <div className="k-atlas-bar">
        <label className="k-search"><Pictogram name="search" size={16} />
          <input ref={input} placeholder="Search buildings" aria-label="Search buildings" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <button type="button" className="k-ctl icon" aria-label="Close atlas" onClick={onClose}><Pictogram name="close" size={18} /></button>
      </div>
      <div className="k-atlas-chips" role="group" aria-label="Kind of building">
        {KINDS.map(k => <button key={k.key} type="button" className="k-ctl" aria-pressed={kind === k.key} onClick={() => setKind(kind === k.key ? null : k.key)}><Pictogram name={k.icon} size={16} />{k.label}</button>)}
        <button type="button" className="k-ctl" onClick={surprise}><Pictogram name="orbit" size={16} />Surprise me</button>
      </div>
      <div className="k-atlas-grid" role="listbox" aria-label="Buildings">
        {list.map((b, i) => (
          <button key={b.building_id} type="button" role="option" aria-selected={i === cursor} data-atlas-index={i} className="k-card" data-current={b.building_id === value} data-cursor={i === cursor}
            onClick={() => onPick(b.building_id)} onMouseEnter={() => setCursor(i)}>
            <img src={`/api/buildings/${b.building_id}/thumb.svg`} alt="" loading="lazy" width={240} height={150} />
            <span className="k-card-name">{b.name}</span>
            <span className="k-card-meta">{b.floors} floors{b.rooms ? ` · ${b.rooms} rooms` : ""}{b.building_id === value ? " · open now" : recent.includes(b.building_id) ? " · recent" : ""}</span>
          </button>
        ))}
        {!list.length && <p className="k-hint">No building matches.</p>}
      </div>
    </div>
  );
}

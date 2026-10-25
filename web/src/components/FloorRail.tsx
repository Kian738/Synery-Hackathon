import type { Floor, Route } from "../lib/types";
import { floorColor } from "../lib/floorColors";

const levelLabel = (level: number) => (level === 0 ? "G" : level > 0 ? String(level) : `B${-level}`);

/** Floors as a compact strip of coloured dots. Hover or focus expands it to names; floors on the route keep their names
 *  (the route is "focused") and wear an amber ring. Floor colour comes from lib/floorColors. */
export function FloorRail({ floors, active, route, onPick, here }: {
  floors: Floor[];
  active: string;
  route?: Route | null;
  onPick: (id: string) => void;
  here?: string | null;
}) {
  const ordered = [...floors].sort((a, b) => b.level - a.level);
  const onRoute = new Set(route?.floors ?? []);
  return (
    <nav aria-label="Floors" className="k-rail" data-route={onRoute.size > 0 ? "true" : "false"}>
      {ordered.map(f => (
        <button key={f.id} type="button" className="k-floor" onClick={() => onPick(f.id)} aria-current={f.id === active ? "true" : undefined}
          data-current={f.id === active} data-route={onRoute.has(f.id)} style={{ ["--fc" as string]: floorColor(f.level) }} title={f.name}>
          <i />
          <b>{levelLabel(f.level)}</b>
          <span className="name">{f.name}</span>
          {here === f.id && <em>Start</em>}
        </button>
      ))}
    </nav>
  );
}

import type { Floor, Route } from "../lib/types";

/** Floors as stops on a vertical transit line; the route's floors are joined by the marking colour. */
export function FloorRail({ floors, active, route, onPick, here }: {
  floors: Floor[];
  active: string;
  route?: Route | null;
  onPick: (id: string) => void;
  here?: string | null;
}) {
  const ordered = [...floors].sort((a, b) => b.level - a.level);
  const onRoute = new Set(route?.floors ?? []);
  const levels = ordered.filter((f) => onRoute.has(f.id)).map((f) => ordered.indexOf(f));
  const top = levels.length ? Math.min(...levels) : -1;
  const bottom = levels.length ? Math.max(...levels) : -1;
  return (
    <nav aria-label="Floors" className="relative flex flex-col bg-white/95 border border-ink">
      {ordered.map((f, i) => {
        const inSpan = i >= top && i <= bottom && top !== bottom;
        return (
          <button key={f.id} type="button" onClick={() => onPick(f.id)} aria-current={f.id === active ? "true" : undefined}
            className={`group relative flex h-11 items-center gap-3 pl-3 pr-4 text-left font-sign text-[15px] leading-none
              ${f.id === active ? "bg-ink text-white" : "hover:bg-concrete"}`}>
            <span className="relative grid w-4 place-items-center self-stretch">
              <span className={`absolute inset-y-0 w-[3px] ${i === 0 ? "top-1/2" : ""} ${i === ordered.length - 1 ? "bottom-1/2" : ""}
                ${inSpan ? "bg-mark" : f.id === active ? "bg-ink-3" : "bg-concrete-3"}`} />
              <span className={`relative h-3 w-3 rounded-full border-2 ${onRoute.has(f.id) ? "border-ink bg-mark" : f.id === active ? "border-white bg-ink" : "border-ink bg-white"}`} />
            </span>
            <span className="font-semibold">{f.level === 0 ? "G" : f.level > 0 ? f.level : `B${-f.level}`}</span>
            <span className={`hidden sm:inline text-[13px] ${f.id === active ? "text-concrete" : "text-ink-3"}`}>{f.name}</span>
            {here === f.id && <span className="ml-auto text-[11px] font-semibold text-escape">YOU</span>}
          </button>
        );
      })}
    </nav>
  );
}

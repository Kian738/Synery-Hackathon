import { useEffect, useMemo, useRef, useState } from "react";
import { area, bounds, centroid, zoneOf } from "../lib/geometry";
import type { Geometry, Opening, Route, Space, XY } from "../lib/types";
import { Pictogram } from "./Pictogram";

/** Architect's-drawing plan of one floor: ink outlines, quiet zone tints, the route as floor-marking tape.
 *  Zoom/pan by wheel, drag, keyboard arrows or the buttons (WCAG 2.5.7: dragging is never required). */

export interface Pin {
  id: string;
  at: XY;
  floor_id: string;
  label: string;
  tone: "start" | "end" | "match" | "info";
  n?: number;
}

interface Props {
  geometry: Geometry;
  floorId: string;
  route?: Route | null;
  highlights?: Set<string>;
  closed?: Set<string>;
  pins?: Pin[];
  previewDoor?: Opening | null;
  selected?: string | null;
  focus?: XY | null;
  showItems?: boolean;
  onSpaceClick?: (space: Space) => void;
  compact?: boolean;
}

const ZONE_FILL: Record<string, string> = {
  circulation: "var(--color-zone-circulation)",
  hall: "var(--color-zone-hall)",
  office: "var(--color-zone-office)",
  lab: "var(--color-zone-lab)",
  service: "var(--color-zone-service)",
  core: "var(--color-zone-core)",
};

const flip = ([x, y]: XY): XY => [x, -y];
const pts = (polygon: XY[]) => polygon.map((p) => flip(p).join(",")).join(" ");

export function PlanView({ geometry, floorId, route, highlights, closed, pins = [], previewDoor, selected, focus,
  showItems = true, onSpaceClick, compact }: Props) {
  const spaces = useMemo(() => geometry.spaces.filter((s) => s.floor_id === floorId), [geometry, floorId]);
  const openings = useMemo(() => geometry.openings.filter((o) => o.floor_id === floorId), [geometry, floorId]);
  const assets = useMemo(() => geometry.assets.filter((a) => a.floor_id === floorId), [geometry, floorId]);
  const box = useMemo(() => bounds(spaces.flatMap((s) => s.polygon)), [spaces]);
  const size = Math.max(box.maxX - box.minX, box.maxY - box.minY, 1);
  const fit = useMemo(() => {
    const pad = size * 0.05;
    return { x: box.minX - pad, y: -box.maxY - pad, w: box.maxX - box.minX + 2 * pad, h: box.maxY - box.minY + 2 * pad };
  }, [box, size]);
  const [view, setView] = useState(fit);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: typeof view; moved: boolean } | null>(null);

  useEffect(() => setView(fit), [fit]);
  useEffect(() => {
    if (!focus) return;
    const w = Math.min(fit.w, Math.max(size * 0.35, 18));
    const h = (w * fit.h) / fit.w;
    setView({ x: focus[0] - w / 2, y: -focus[1] - h / 2, w, h });
  }, [focus, fit, size]);

  const scale = view.w / 100; // metres per 1 % of width: drives stroke and type sizes
  const font = Math.max(0.35, Math.min(2.2, scale * 1.6));
  const closedSpaces = useMemo(() => {
    const ids = new Set<string>(closed ?? []);
    geometry.connectors.filter((c) => closed?.has(c.id)).forEach((c) => c.space_ids.forEach((s) => ids.add(s)));
    return ids;
  }, [closed, geometry]);
  const coreIcon = (s: Space) => (/lift/.test(s.type + s.room_type) ? "lift" : "stairs");

  const zoom = (factor: number, cx = view.x + view.w / 2, cy = view.y + view.h / 2) =>
    setView((v) => ({ x: cx - (cx - v.x) * factor, y: cy - (cy - v.y) * factor, w: v.w * factor, h: v.h * factor }));
  const pan = (dx: number, dy: number) => setView((v) => ({ ...v, x: v.x + dx * v.w, y: v.y + dy * v.h }));

  const runs = useMemo(() => {
    if (!route) return [] as XY[][];
    const out: XY[][] = [];
    let current: XY[] = [];
    for (const p of route.polyline as (typeof route.polyline[number] & { gap?: boolean })[]) {
      if (p.gap && current.length) {
        out.push(current);
        current = [];
      }
      if (p.floor_id === floorId) current.push([p.x, p.y]);
      else if (current.length) {
        out.push(current);
        current = [];
      }
    }
    if (current.length) out.push(current);
    return out.filter((r) => r.length > 1);
  }, [route, floorId]);

  const length = (run: XY[]) => run.reduce((sum, p, i) => (i ? sum + Math.hypot(p[0] - run[i - 1][0], p[1] - run[i - 1][1]) : 0), 0);

  return (
    <div className="relative h-full w-full select-none overflow-hidden" onKeyDown={(e) => {
      const map: Record<string, [number, number]> = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, -0.15], ArrowDown: [0, 0.15] };
      if (map[e.key]) { e.preventDefault(); pan(...map[e.key]); }
      if (e.key === "+" || e.key === "=") zoom(0.8);
      if (e.key === "-") zoom(1.25);
    }} tabIndex={0} aria-label={`Floor plan, ${geometry.floors.find((f) => f.id === floorId)?.name}`}>
      <svg
        ref={svg}
        className="h-full w-full touch-none cursor-grab active:cursor-grabbing"
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onWheel={(e) => {
          const r = svg.current!.getBoundingClientRect();
          const k = Math.max(view.w / r.width, view.h / r.height);
          const cx = view.x + (e.clientX - r.left - (r.width - view.w / k) / 2) * k;
          const cy = view.y + (e.clientY - r.top - (r.height - view.h / k) / 2) * k;
          zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, cx, cy);
        }}
        onPointerDown={(e) => (drag.current = { x: e.clientX, y: e.clientY, view, moved: false })}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const r = svg.current!.getBoundingClientRect();
          const k = Math.max(view.w / r.width, view.h / r.height);
          const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
          if (Math.abs(dx) + Math.abs(dy) > 4) drag.current.moved = true;
          setView({ ...drag.current.view, x: drag.current.view.x - dx * k, y: drag.current.view.y - dy * k });
        }}
        onPointerUp={() => setTimeout(() => (drag.current = null), 0)}
        onPointerLeave={() => (drag.current = null)}
      >
        <g>
          {spaces.map((s) => {
            const zone = zoneOf(s);
            const isClosed = closedSpaces.has(s.id);
            const isHi = highlights?.has(s.id);
            return (
              <polygon
                key={s.id}
                points={pts(s.polygon)}
                fill={isClosed ? "#f3d9dd" : ZONE_FILL[zone]}
                stroke="var(--color-ink)"
                strokeWidth={scale * 0.14}
                className="cursor-pointer transition-[fill] duration-150 hover:fill-white"
                onClick={() => !drag.current?.moved && onSpaceClick?.(s)}
              >
                <title>{`${s.name} — ${s.room_type.replace(/_/g, " ")}, ${area(s.polygon).toFixed(1)} m²`}</title>
              </polygon>
            );
          })}
          {/* highlight and selection outlines on top so they are never hidden by neighbours */}
          {spaces.filter((s) => highlights?.has(s.id) || selected === s.id).map((s) => (
            <polygon key={`h-${s.id}`} points={pts(s.polygon)} fill="none"
              stroke={selected === s.id ? "var(--color-mandatory)" : "var(--color-ink)"}
              strokeWidth={scale * (selected === s.id ? 0.55 : 0.4)} pointerEvents="none"
              strokeDasharray={highlights?.has(s.id) && selected !== s.id ? `${scale * 1.2} ${scale * 0.7}` : undefined} />
          ))}
          {spaces.filter((s) => closedSpaces.has(s.id)).map((s) => {
            const [x, y] = flip(centroid(s.polygon));
            return <text key={`c-${s.id}`} x={x} y={y} fontSize={font * 0.9} textAnchor="middle" dominantBaseline="middle"
              fill="var(--color-signal)" fontWeight={700} fontFamily="var(--font-sign)" pointerEvents="none">CLOSED</text>;
          })}
          {openings.map((o) => {
            const [x, y] = flip(o.position);
            if (o.kind === "entrance") {
              const r = font * 0.75;
              return <path key={o.id} d={`M${x} ${y - r}L${x + r} ${y + r * 0.7}L${x - r} ${y + r * 0.7}Z`} fill="var(--color-escape)"><title>Entrance</title></path>;
            }
            const r = scale * 0.32;
            return <rect key={o.id} x={x - r} y={y - r} width={2 * r} height={2 * r}
              fill={closed?.has(o.id) ? "var(--color-signal)" : o.step_free ? "white" : "var(--color-mark)"}
              stroke="var(--color-ink)" strokeWidth={scale * 0.1}><title>{`${o.kind}, ${o.width_m} m${o.step_free ? "" : ", has steps"}`}</title></rect>;
          })}
          {showItems && assets.filter((a) => a.category === "machine" || a.category === "equipment").map((a) => {
            const [x, y] = flip(a.position);
            const w = a.footprint?.width_m ?? 0.6, d = a.footprint?.depth_m ?? 0.6;
            return <rect key={a.id} x={x - w / 2} y={y - d / 2} width={w} height={d}
              transform={`rotate(${-(a.footprint?.rotation_deg ?? 0)} ${x} ${y})`}
              fill={highlights?.has(a.id) ? "var(--color-mark)" : "none"} stroke="var(--color-ink-3)" strokeWidth={scale * 0.08}>
              <title>{a.name}</title></rect>;
          })}
          {spaces.map((s) => {
            const a = area(s.polygon);
            const minArea = (view.w * view.w) / 2200;
            const zone = zoneOf(s);
            const [x, y] = flip(centroid(s.polygon));
            if (zone === "core") return <g key={`l-${s.id}`} transform={`translate(${x - font} ${y - font}) scale(${font / 12})`} color="var(--color-ink)" pointerEvents="none"><Pictogram name={coreIcon(s)} size={24} /></g>;
            if (a < minArea && !highlights?.has(s.id) && selected !== s.id) return null;
            return <text key={`l-${s.id}`} x={x} y={y} fontSize={font} textAnchor="middle" dominantBaseline="middle"
              fill="var(--color-ink)" fontFamily="var(--font-sign)" fontWeight={600} pointerEvents="none">{s.ref || s.name}</text>;
          })}
          {previewDoor && previewDoor.floor_id === floorId && (() => {
            const [x, y] = flip(previewDoor.position);
            return <circle cx={x} cy={y} r={font * 1.1} fill="none" stroke="var(--color-mandatory)" strokeWidth={scale * 0.35} strokeDasharray={`${scale} ${scale * 0.6}`} className="pin-pulse" />;
          })()}
          {runs.map((run, i) => {
            const d = run.map((p) => flip(p).join(",")).join(" ");
            const len = length(run) + 1;
            return (
              <g key={`${route?.length_m}-${i}`} pointerEvents="none">
                <polyline points={d} fill="none" stroke="var(--color-ink)" strokeWidth={font * 0.95} strokeLinecap="round" strokeLinejoin="round" />
                <polyline points={d} fill="none" stroke="var(--color-mark)" strokeWidth={font * 0.6} strokeLinecap="round" strokeLinejoin="round"
                  className="route-draw" style={{ ["--len" as string]: len }} />
              </g>
            );
          })}
          {pins.filter((p) => p.floor_id === floorId).map((p) => {
            const [x, y] = flip(p.at);
            const r = font * 1.05;
            const fill = p.tone === "start" ? "var(--color-escape)" : p.tone === "end" ? "var(--color-ink)" : p.tone === "match" ? "var(--color-mandatory)" : "var(--color-ink-3)";
            return (
              <g key={p.id} pointerEvents="none">
                {p.tone === "end" ? (
                  <rect x={x - r} y={y - r} width={2 * r} height={2 * r} fill={fill} stroke="var(--color-mark)" strokeWidth={scale * 0.35} />
                ) : (
                  <circle cx={x} cy={y} r={r} fill={fill} stroke="white" strokeWidth={scale * 0.25} />
                )}
                <text x={x} y={y} fontSize={font * 1.05} textAnchor="middle" dominantBaseline="central"
                  fill={p.tone === "end" ? "var(--color-mark)" : "white"} fontWeight={700} fontFamily="var(--font-sign)">
                  {p.n ?? (p.tone === "start" ? "●" : p.tone === "end" ? "▸" : "")}
                </text>
                <title>{p.label}</title>
              </g>
            );
          })}
        </g>
      </svg>
      <div className={`absolute ${compact ? "bottom-2 right-2" : "bottom-4 right-4"} flex flex-col border border-ink bg-white`}>
        {[["plus", () => zoom(0.75), "Zoom in"], ["minus", () => zoom(1.33), "Zoom out"], ["fit", () => setView(fit), "Fit floor"]].map(([icon, fn, label]) => (
          <button key={icon as string} type="button" onClick={fn as () => void} aria-label={label as string} title={label as string}
            className="grid h-9 w-9 place-items-center border-b border-concrete-3 last:border-b-0 hover:bg-concrete">
            <Pictogram name={icon as string} size={18} />
          </button>
        ))}
      </div>
    </div>
  );
}

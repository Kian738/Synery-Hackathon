import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, Floor, Geometry, Opening, Route, Space, XY } from "../types";

const GROUPS: [RegExp, string][] = [
  [/corridor|lobby|hall_access/, "var(--c-circulation)"],
  [/stair|lift/, "var(--c-core)"],
  [/production|assembly|additive|warehouse|logistics/, "var(--c-production)"],
  [/lab|quality|makerspace|server|technical/, "var(--c-lab)"],
  [/office|meeting|seminar|lecture|library|print/, "var(--c-office)"],
  [/toilet|bathroom|kitchen|canteen|locker/, "var(--c-service)"],
  [/bedroom|living|balcony|storage/, "var(--c-home)"],
];

export function fillFor(space: Space): string {
  const key = `${space.room_type} ${space.type}`;
  for (const [pattern, color] of GROUPS) if (pattern.test(key)) return color;
  return "var(--c-room)";
}

const toPoints = (polygon: XY[]) => polygon.map(([x, y]) => `${x},${-y}`).join(" ");

function centroid(polygon: XY[]): XY {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x0, y0] = polygon[i];
    const [x1, y1] = polygon[(i + 1) % polygon.length];
    const f = x0 * y1 - x1 * y0;
    a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f;
  }
  if (Math.abs(a) < 1e-9) return polygon[0];
  return [cx / (3 * a), cy / (3 * a)];
}

function area(polygon: XY[]): number {
  let a = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x0, y0] = polygon[i];
    const [x1, y1] = polygon[(i + 1) % polygon.length];
    a += x0 * y1 - x1 * y0;
  }
  return Math.abs(a / 2);
}

export function bounds(spaces: Space[]) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const s of spaces) for (const [x, y] of s.polygon) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  if (!isFinite(minX)) return { minX: 0, minY: 0, maxX: 10, maxY: 10 };
  return { minX, minY, maxX, maxY };
}

const LANDMARK = new Set(["machine", "equipment"]);

interface LayerProps {
  geometry: Geometry;
  floor: Floor;
  route: Route | null;
  highlights: Set<string>;
  closed: Set<string>;
  selected: string[];
  previewDoor: Opening | null;
  showItems: boolean;
  onSpaceClick?: (space: Space, event: React.MouseEvent) => void;
  onHover?: (text: string | null) => void;
  labels?: boolean;
}

/** One floor drawn in metres (y up), shared by the plan view and the stacked 3D view. */
export function FloorLayer({ geometry, floor, route, highlights, closed, selected, previewDoor, showItems,
  onSpaceClick, onHover, labels = true }: LayerProps) {
  const spaces = useMemo(() => geometry.spaces.filter((s) => s.floor_id === floor.id), [geometry, floor]);
  const openings = useMemo(() => geometry.openings.filter((o) => o.floor_id === floor.id), [geometry, floor]);
  const assets = useMemo(() => geometry.assets.filter((a) => a.floor_id === floor.id), [geometry, floor]);
  const box = useMemo(() => bounds(spaces), [spaces]);
  const size = Math.max(box.maxX - box.minX, box.maxY - box.minY);
  const font = Math.max(0.6, Math.min(1.6, size / 70));
  const closedSpaces = new Set(
    geometry.connectors.filter((c) => closed.has(c.id)).flatMap((c) => c.space_ids).concat([...closed]),
  );

  const segments = useMemo(() => {
    if (!route) return [] as XY[][];
    const runs: XY[][] = [];
    let current: XY[] = [];
    for (const p of route.polyline) {
      if (p.floor_id === floor.id) current.push([p.x, p.y]);
      else if (current.length) { runs.push(current); current = []; }
    }
    if (current.length) runs.push(current);
    return runs.filter((r) => r.length > 1);
  }, [route, floor]);

  const routeEnds = useMemo(() => {
    if (!route || !route.polyline.length) return [];
    const first = route.polyline[0], last = route.polyline[route.polyline.length - 1];
    return [
      first.floor_id === floor.id ? { p: first, kind: "start" } : null,
      last.floor_id === floor.id ? { p: last, kind: "end" } : null,
    ].filter(Boolean) as { p: { x: number; y: number }; kind: string }[];
  }, [route, floor]);

  const minLabelArea = (size * size) / 900;

  return (
    <g>
      {spaces.map((s) => {
        const isHighlighted = highlights.has(s.id);
        const isSelected = selected.includes(s.id);
        const isClosed = closedSpaces.has(s.id);
        return (
          <polygon
            key={s.id}
            points={toPoints(s.polygon)}
            className={`space${isHighlighted ? " highlighted" : ""}${isSelected ? " selected" : ""}${isClosed ? " closed" : ""}`}
            style={{ fill: fillFor(s) }}
            onClick={(e) => onSpaceClick?.(s, e)}
            onMouseEnter={() => onHover?.(`${s.name} · ${s.room_type.replace(/_/g, " ")} · ${area(s.polygon).toFixed(1)} m²`)}
            onMouseLeave={() => onHover?.(null)}
          />
        );
      })}
      {openings.map((o) => (
        <circle
          key={o.id}
          cx={o.position[0]}
          cy={-o.position[1]}
          r={o.kind === "entrance" ? font * 0.55 : font * 0.28}
          className={`opening ${o.kind}${closed.has(o.id) ? " closed" : ""}${o.step_free ? "" : " steps"}`}
          onMouseEnter={() => onHover?.(`${o.kind} · ${o.width_m} m wide${o.step_free ? "" : " · has steps"}`)}
          onMouseLeave={() => onHover?.(null)}
        />
      ))}
      {showItems &&
        assets.map((a: Asset) => (
          <rect
            key={a.id}
            x={a.position[0] - (LANDMARK.has(a.category) ? 0.5 : 0.22)}
            y={-a.position[1] - (LANDMARK.has(a.category) ? 0.5 : 0.22)}
            width={LANDMARK.has(a.category) ? 1 : 0.44}
            height={LANDMARK.has(a.category) ? 1 : 0.44}
            className={`asset ${a.category}${highlights.has(a.id) ? " highlighted" : ""}`}
            onMouseEnter={() => onHover?.(`${a.name} · ${a.type.replace(/_/g, " ")}`)}
            onMouseLeave={() => onHover?.(null)}
          />
        ))}
      {labels &&
        spaces
          .filter((s) => area(s.polygon) > minLabelArea || highlights.has(s.id) || selected.includes(s.id))
          .map((s) => {
            const [x, y] = centroid(s.polygon);
            return (
              <text key={`l-${s.id}`} x={x} y={-y} className="label" style={{ fontSize: font }}>
                {s.ref || s.name}
              </text>
            );
          })}
      {previewDoor && previewDoor.floor_id === floor.id && (
        <circle cx={previewDoor.position[0]} cy={-previewDoor.position[1]} r={font * 0.9} className="preview-door" />
      )}
      {segments.map((run, i) => (
        <g key={`r-${i}`}>
          <polyline points={run.map(([x, y]) => `${x},${-y}`).join(" ")} className="route-casing" style={{ strokeWidth: font * 0.9 }} />
          <polyline points={run.map(([x, y]) => `${x},${-y}`).join(" ")} className="route" style={{ strokeWidth: font * 0.45 }} />
        </g>
      ))}
      {routeEnds.map(({ p, kind }) => (
        <circle key={kind} cx={p.x} cy={-p.y} r={font * 0.8} className={`route-${kind}`} />
      ))}
    </g>
  );
}

interface PlanProps extends Omit<LayerProps, "floor"> {
  floorId: string;
}

/** Interactive 2D plan: wheel to zoom, drag to pan. */
export function FloorPlan(props: PlanProps) {
  const floor = props.geometry.floors.find((f) => f.id === props.floorId)!;
  const spaces = props.geometry.spaces.filter((s) => s.floor_id === props.floorId);
  const box = bounds(spaces);
  const pad = Math.max(box.maxX - box.minX, box.maxY - box.minY) * 0.04;
  const initial = { x: box.minX - pad, y: -box.maxY - pad, w: box.maxX - box.minX + 2 * pad, h: box.maxY - box.minY + 2 * pad };
  const [view, setView] = useState(initial);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: typeof view } | null>(null);

  useEffect(() => setView(initial), [props.floorId, props.geometry.building.id]); // eslint-disable-line

  const onWheel = (e: React.WheelEvent) => {
    const rect = svg.current!.getBoundingClientRect();
    const scale = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const mx = view.x + ((e.clientX - rect.left) / rect.width) * view.w;
    const my = view.y + ((e.clientY - rect.top) / rect.height) * view.h;
    setView({ x: mx - (mx - view.x) * scale, y: my - (my - view.y) * scale, w: view.w * scale, h: view.h * scale });
  };
  const onDown = (e: React.MouseEvent) => (drag.current = { x: e.clientX, y: e.clientY, view });
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    const rect = svg.current!.getBoundingClientRect();
    const k = Math.max(view.w / rect.width, view.h / rect.height);
    setView({ ...drag.current.view, x: drag.current.view.x - (e.clientX - drag.current.x) * k, y: drag.current.view.y - (e.clientY - drag.current.y) * k });
  };

  return (
    <svg
      ref={svg}
      className="plan"
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      preserveAspectRatio="xMidYMid meet"
      onWheel={onWheel}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={() => (drag.current = null)}
      onMouseLeave={() => (drag.current = null)}
    >
      <FloorLayer {...props} floor={floor} />
    </svg>
  );
}

/** Isometric stack of every floor at its elevation, with the route drawn on each layer. */
export function StackView(props: Omit<PlanProps, "floorId"> & { activeFloorId: string; onPickFloor: (id: string) => void }) {
  const box = bounds(props.geometry.spaces);
  const w = box.maxX - box.minX, h = box.maxY - box.minY;
  const floors = [...props.geometry.floors].sort((a, b) => a.level - b.level);
  const gap = 150;
  return (
    <div className="stack-scene">
      <div className="stack" style={{ height: `${floors.length * 40 + 380}px` }}>
        {floors.map((f, i) => (
          <div
            key={f.id}
            className={`stack-layer${f.id === props.activeFloorId ? " active" : ""}${props.route?.floors.includes(f.id) ? " on-route" : ""}`}
            style={{ transform: `translateZ(${(i - (floors.length - 1) / 2) * gap}px)` }}
            onClick={() => props.onPickFloor(f.id)}
          >
            <span className="stack-name">{f.name}</span>
            <svg viewBox={`${box.minX - 2} ${-box.maxY - 2} ${w + 4} ${h + 4}`} preserveAspectRatio="xMidYMid meet">
              <FloorLayer {...props} floor={f} labels={false} showItems={false} />
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}

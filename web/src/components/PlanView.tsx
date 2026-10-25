import { useEffect, useMemo, useRef, useState } from "react";
import { placeMapLabels } from "../lib/mapLabels";
import { routeRuns } from "../lib/playback";
import { area, bounds, centroid, zoneOf } from "../lib/geometry";
import { kindOf, kindPlan, ROOM_KIND } from "../lib/roomKinds";
import { floorColor } from "../lib/floorColors";
import type { Geometry, Opening, Route, ScenarioMark, Space, XY, VisualResult } from "../lib/types";
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
  heading?: number;
}

interface Props {
  geometry: Geometry;
  visualResult?:VisualResult|null;
  floorId: string;
  route?: Route | null;
  highlights?: Set<string>;
  closed?: Set<string>;
  pins?: Pin[];
  previewDoor?: Opening | null;
  selected?: string | null;
  scenario?: ScenarioMark | null;
  focus?: XY | null;
  showItems?: boolean;
  onSpaceClick?: (space: Space) => void;
  compact?: boolean;
  followPosition?:boolean;
  focusKey?:string;
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

export function PlanView({ geometry, floorId, route, highlights, closed, pins = [], previewDoor, selected, focus, scenario,
  showItems = true, onSpaceClick, compact,visualResult,followPosition=false,focusKey }: Props) {
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
  const drag = useRef<{ x: number; y: number; view: typeof view; moved: boolean;spaceId:string|null } | null>(null);

  const [tracking,setTracking]=useState(true);
  useEffect(() => {setView(fit);setTracking(true);}, [fit]);
  useEffect(()=>setTracking(true),[focusKey]);


  // Sizes are set in screen pixels, then converted to metres, so labels stay readable in any building.
  const [screen, setScreen] = useState({ w: 800, h: 600 });
  const box_ = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box_.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setScreen({ w: entry.contentRect.width, h: entry.contentRect.height }));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const runs = useMemo(() => (route ? routeRuns(route, new Set([floorId])).map((run) => run.map((p) => [p.x, p.y] as XY)) : []), [route, floorId]);
  const routeBox = useMemo(() => {
    const pts = runs.flat();
    if (!pts.length) return null;
    return bounds(pts);
  }, [runs]);

  const prevFocus = useRef<XY | null>(null);

  useEffect(() => {
    if (focus) {
      if (followPosition && !tracking) return;
      const focusedSpace = selected ? spaces.find((s) => s.id === selected) : null;
      if (focusedSpace && focusedSpace.polygon.length) {
        const b = bounds(focusedSpace.polygon);
        const rw = b.maxX - b.minX;
        const rh = b.maxY - b.minY;
        const pad = Math.max(3.5, Math.max(rw, rh) * 0.4);
        const w = Math.max(rw + 2 * pad, ((rh + 2 * pad) * screen.w) / Math.max(1, screen.h));
        const h = (w * screen.h) / Math.max(1, screen.w);
        const cx = (b.minX + b.maxX) / 2;
        const cy = (b.minY + b.maxY) / 2;
        setView({ x: cx - w / 2, y: -cy - h / 2, w, h });
      } else {
        const w = Math.max(10, Math.min(22, size * 0.22)), h = (w * screen.h) / Math.max(1, screen.w);
        setView({ x: focus[0] - w / 2, y: -focus[1] - h / 2, w, h });
      }
      prevFocus.current = focus;
    } else if (prevFocus.current !== null) {
      prevFocus.current = null;
      if (route && routeBox) {
        const rw = Math.max(routeBox.maxX - routeBox.minX, 8);
        const rh = Math.max(routeBox.maxY - routeBox.minY, 8);
        const rSize = Math.max(rw, rh);
        const pad = rSize * 0.25;
        const w = Math.max(rw + 2 * pad, ((rh + 2 * pad) * screen.w) / Math.max(1, screen.h));
        const h = (w * screen.h) / Math.max(1, screen.w);
        const cx = (routeBox.minX + routeBox.maxX) / 2;
        const cy = (routeBox.minY + routeBox.maxY) / 2;
        setView({ x: cx - w / 2, y: -cy - h / 2, w, h });
      } else {
        setView(fit);
      }
    }
  }, [focus, selected, spaces, followPosition, tracking, route, routeBox, fit, screen.w, screen.h, size]);
  const pxPerM = Math.max(0.01, Math.min(screen.w / view.w, screen.h / view.h));
  const scale = 8 / pxPerM; // 8 screen px, in metres: base unit for strokes and markers
  const font = 12.5 / pxPerM; // labels are 12.5 px on screen
  const closedSpaces = useMemo(() => {
    const ids = new Set<string>(closed ?? []);
    geometry.connectors.filter((c) => closed?.has(c.id)).forEach((c) => c.space_ids.forEach((s) => ids.add(s)));
    return ids;
  }, [closed, geometry]);
  const labelIds=useMemo(()=>placeMapLabels(spaces.flatMap(s=>{
    const [x,y]=flip(s.anchor??centroid(s.polygon)),core=zoneOf(s)==="core",text=s.ref||s.name;
    if(x<view.x||x>view.x+view.w||y<view.y||y>view.y+view.h)return [];
    const pixels=area(s.polygon)*pxPerM*pxPerM;
    if(s.id!==selected&&pixels<(core?500:1500))return [];
    return [{id:s.id,x:(x-view.x)*pxPerM,y:(y-view.y)*pxPerM,width:core?22:Math.min(150,text.length*6.5),height:core?22:17,
             priority:s.id===selected?1e9:(highlights?.has(s.id)?1e6:0)+pixels}];
  }),compact?12:32),[spaces,view,pxPerM,selected,highlights,compact]);
  const coreIcon = (s: Space) => (/lift/.test(s.type + s.room_type) ? "lift" : "stairs");

  const zoom = (factor: number, cx = view.x + view.w / 2, cy = view.y + view.h / 2) =>
    setView((v) => ({ x: cx - (cx - v.x) * factor, y: cy - (cy - v.y) * factor, w: v.w * factor, h: v.h * factor }));
  const pan = (dx: number, dy: number) => setView((v) => ({ ...v, x: v.x + dx * v.w, y: v.y + dy * v.h }));


  return (
    <div ref={box_} className="relative h-full w-full select-none overflow-hidden" onKeyDown={(e) => {
      const map: Record<string, [number, number]> = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, -0.15], ArrowDown: [0, 0.15] };
      if (map[e.key]) { e.preventDefault(); pan(...map[e.key]); }
      if (e.key === "+" || e.key === "=") zoom(0.8);
      if (e.key === "-") zoom(1.25);
    }} tabIndex={0} aria-label={`Floor plan, ${geometry.floors.find((f) => f.id === floorId)?.name}`}>
      <svg aria-label="Floor plan" role="img"
        ref={svg}
        className="h-full w-full touch-none cursor-grab active:cursor-grabbing"
        style={{ boxShadow: `inset 0 0 0 3px ${floorColor(geometry.floors.find(f => f.id === floorId)?.level ?? 0)}` }}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onWheel={(e) => {
          if(followPosition)setTracking(false);
          const r = svg.current!.getBoundingClientRect();
          const k = Math.max(view.w / r.width, view.h / r.height);
          const cx = view.x + (e.clientX - r.left - (r.width - view.w / k) / 2) * k;
          const cy = view.y + (e.clientY - r.top - (r.height - view.h / k) / 2) * k;
          zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, cx, cy);
        }}
        onPointerDown={e=>{
          if(e.button!==0)return;
          const spaceId=(e.target as Element).closest('[data-space-id]')?.getAttribute('data-space-id')??null;
          drag.current={x:e.clientX,y:e.clientY,view,moved:false,spaceId};
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const r = svg.current!.getBoundingClientRect();
          const k = Math.max(view.w / r.width, view.h / r.height);
          const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
          if (Math.hypot(dx,dy)>5) {drag.current.moved=true;if(followPosition)setTracking(false);}
          if(!drag.current.moved)return;
          setView({ ...drag.current.view, x: drag.current.view.x - dx * k, y: drag.current.view.y - dy * k });
        }}
        onPointerUp={e=>{
          const gesture=drag.current;drag.current=null;
          if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
          if(gesture&&!gesture.moved&&gesture.spaceId){const room=spaces.find(s=>s.id===gesture.spaceId);if(room)onSpaceClick?.(room);}
        }}
        onPointerCancel={()=>{drag.current=null;}}
        onPointerLeave={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))drag.current=null;}}
      >
        <g>
          {spaces.map((s) => {
            const zone = zoneOf(s);
            const isClosed = closedSpaces.has(s.id);
            const isHi = highlights?.has(s.id);
            const crowd = scenario?.crowd?.[s.id];
            return (
              <g key={s.id}>
              <polygon
                data-space-id={s.id}
                points={pts(s.polygon)}
                fill={isClosed ? "#f3d9dd" : kindPlan(s)}
                stroke="var(--color-ink)"
                strokeWidth={scale * 0.14}
                className="cursor-pointer transition-[fill] duration-150 hover:fill-white"
              >
                <title>{`${s.name} — ${ROOM_KIND[kindOf(s)].label}, ${area(s.polygon).toFixed(1)} m²`}</title>
              </polygon>
              {crowd && <polygon points={pts(s.polygon)} fill="var(--color-mark)" fillOpacity={crowd === 2 ? 0.8 : 0.4} pointerEvents="none" />}
              </g>
            );
          })}
          {/* highlight and selection outlines on top so they are never hidden by neighbours */}
          {spaces.filter((s) => highlights?.has(s.id) || selected === s.id).map((s) => (
            <polygon key={`h-${s.id}`} points={pts(s.polygon)} fill="none"
              stroke={selected === s.id ? "var(--color-mandatory)" : "var(--color-ink)"}
              strokeWidth={scale * (selected === s.id ? 0.55 : 0.4)} pointerEvents="none"
              strokeDasharray={highlights?.has(s.id) && selected !== s.id ? `${scale * 1.2} ${scale * 0.7}` : undefined} />
          ))}
          {scenario && <defs><pattern id="hazard-hatch" width={scale * 1.2} height={scale * 1.2} patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width={scale * 1.2} height={scale * 1.2} fill="#182329" fillOpacity="0.35" /><line x1="0" y1="0" x2="0" y2={scale * 1.2} stroke="#ff8a8f" strokeWidth={scale * 0.35} /></pattern></defs>}
          {scenario && spaces.filter((s) => s.id === scenario.hazard).map((s) => { const [x, y] = flip(centroid(s.polygon)); return <g key="hz" pointerEvents="none"><polygon points={pts(s.polygon)} fill="url(#hazard-hatch)" stroke="#ff8a8f" strokeWidth={scale * 0.4} /><text x={x} y={y} fontSize={font} textAnchor="middle" fontWeight="700" fill="#edf3f5" stroke="#182329" strokeWidth={font * 0.3} paintOrder="stroke">Fire: {s.name}</text></g>; })}
          {scenario && openings.filter((o) => scenario.doors.includes(o.id)).map((o) => { const [x, y] = flip(o.position); return <g key={`bd-${o.id}`} pointerEvents="none"><circle cx={x} cy={y} r={scale * 0.9} fill="#ffd45c" stroke="#182329" strokeWidth={scale * 0.2} /><text x={x} y={y - scale * 1.2} fontSize={font * 0.85} textAnchor="middle" fontWeight="700" fill="#10171c" stroke="#ffd45c" strokeWidth={font * 0.3} paintOrder="stroke">Slow door</text></g>; })}
          {scenario?.responder && (() => {
            const pos = scenario.responder.elements.map((id) => openings.find((o) => o.id === id)).filter((o): o is Opening => !!o).map((o) => flip(o.position));
            if (!pos.length) return null;
            const d = pos.map((p) => p.join(",")).join(" ");
            return <g key="responders" pointerEvents="none">
              {pos.length > 1 && <polyline points={d} fill="none" stroke="var(--color-mandatory)" strokeWidth={scale * 0.5} strokeLinecap="round" strokeLinejoin="round" />}
              <circle cx={pos[0][0]} cy={pos[0][1]} r={scale * 0.6} fill="var(--color-mandatory)" />
              <text x={pos[0][0]} y={pos[0][1] - scale * 1.2} fontSize={font} textAnchor="middle" fill="var(--color-mandatory)" stroke="white" strokeWidth={scale * 0.25} paintOrder="stroke" fontWeight={700} fontFamily="var(--font-sign)">{`Responders, in at ${Math.round(scenario.responder.arrival_s)} s`}</text>
            </g>;
          })()}
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
          {showItems && assets.filter((a) => highlights?.has(a.id)||a.category === "machine" || a.category === "equipment").map((a) => {
            const [x, y] = flip(a.position);
            const w = a.footprint?.width_m ?? 0.6, d = a.footprint?.depth_m ?? 0.6;
            if(!highlights?.has(a.id)&&Math.max(w,d)*pxPerM<4)return null;
            return <rect key={a.id} x={x - w / 2} y={y - d / 2} width={w} height={d}
              transform={`rotate(${-(a.footprint?.rotation_deg ?? 0)} ${x} ${y})`}
              fill={highlights?.has(a.id) ? "var(--color-mark)" : "none"} stroke="var(--color-ink-3)" strokeWidth={scale * 0.08}>
              <title>{a.name}</title></rect>;
          })}
          {spaces.map((s) => {
            if(!labelIds.has(s.id))return null;
            const zone = zoneOf(s);
            const [x, y] = flip(centroid(s.polygon));
            if (zone === "core") return <g key={`l-${s.id}`} transform={`translate(${x - font} ${y - font}) scale(${font / 12})`} color="var(--color-ink)" pointerEvents="none"><Pictogram name={coreIcon(s)} size={24} /></g>;
            return <text key={`l-${s.id}`} x={x} y={y} fontSize={font} textAnchor="middle" dominantBaseline="middle"
              fill="var(--color-ink)" fontFamily="var(--font-sign)" fontWeight={600} pointerEvents="none">{s.ref || s.name}</text>;
          })}
          {previewDoor && previewDoor.floor_id === floorId && (() => {
            const [x, y] = flip(previewDoor.position);
            return <circle cx={x} cy={y} r={font * 1.1} fill="none" stroke="var(--color-mandatory)" strokeWidth={scale * 0.35} strokeDasharray={`${scale} ${scale * 0.6}`} className="pin-pulse" />;
          })()}
          {runs.map((run, i) => {
            const d = run.map((p) => flip(p).join(",")).join(" ");
            return (
              <g key={`${route?.length_m}-${i}`} pointerEvents="none">
                <polyline points={d} fill="none" stroke="var(--color-ink)" strokeWidth={font * 0.95} strokeLinecap="round" strokeLinejoin="round" />
                <polyline points={d} fill="none" stroke="var(--color-mark)" strokeWidth={font * 0.6} strokeLinecap="round" strokeLinejoin="round"
                  />
              </g>
            );
          })}
          {visualResult?.kind==="intervention"&&(()=>{const o=visualResult.measurements.proposed_opening as Opening|undefined;return o?.floor_id===floorId?<circle cx={o.position[0]} cy={-o.position[1]} r={font} fill="none" stroke="var(--color-mandatory)" strokeWidth={scale*.4} strokeDasharray={`${scale} ${scale*.4}`}><title>Proposed opening, not applied</title></circle>:null;})()}
          {visualResult?.lines?.map((line,i)=>{
            const floor=geometry.floors.find(f=>Math.abs(f.elevation_m-line.a[2])<.01);
            if(floor&&floor.id!==floorId)return null;
            return <line key={`measurement-${i}`} x1={line.a[0]} y1={-line.a[1]} x2={line.b[0]} y2={-line.b[1]} stroke="var(--color-mandatory)" strokeWidth={scale*.4} strokeDasharray={`${scale} ${scale*.4}`}><title>{visualResult.title}</title></line>;
          })}
          {pins.filter((p) => p.floor_id === floorId).map((p) => {
            const [x, y] = flip(p.at);
            const r = font * 1.05;
            const fill = p.tone === "start" ? "var(--color-escape)" : p.tone === "end" ? "var(--color-ink)" : p.tone === "match" ? "var(--color-mandatory)" : "var(--color-ink-3)";
            return (
              <g key={p.id} pointerEvents="none">
                {p.id === "preview" ? (
                  <path d={`M${x} ${y-r}L${x-r*.8} ${y+r*.75}L${x} ${y+r*.3}L${x+r*.8} ${y+r*.75}Z`} fill="var(--color-mark)" stroke="var(--color-ink)" strokeWidth={scale*.25}/>
                ) : p.tone === "end" ? (
                  <rect x={x - r} y={y - r} width={2 * r} height={2 * r} fill={fill} stroke="var(--color-mark)" strokeWidth={scale * 0.35} />
                ) : (
                  <circle cx={x} cy={y} r={r} fill={fill} stroke="white" strokeWidth={scale * 0.25} />
                )}
                <text x={x} y={y} fontSize={font * 1.05} textAnchor="middle" dominantBaseline="central"
                  fill={p.tone === "end" ? "var(--color-mark)" : "white"} fontWeight={700} fontFamily="var(--font-sign)">
                  {p.n ?? (p.tone === "end" ? "▸" : "")}
                </text>
                {p.heading!==undefined&&<path d={`M${x} ${y-r*2.2}L${x-r*.55} ${y-r*1.1}L${x+r*.55} ${y-r*1.1}Z`} fill={fill} transform={`rotate(${p.heading} ${x} ${y})`}/>}
                <title>{p.label}</title>
              </g>
            );
          })}
        </g>
      </svg>
      <div className={`absolute ${compact ? "bottom-2 right-2" : "bottom-4 right-4"} flex flex-col border border-ink bg-white`}>
        {[["plus", () => zoom(0.75), "Zoom in"], ["minus", () => zoom(1.33), "Zoom out"], ["fit", () => {if(followPosition)setTracking(true);else setView(fit);}, followPosition?"Follow preview":"Fit floor"]].map(([icon, fn, label]) => (
          <button key={icon as string} type="button" onClick={fn as () => void} aria-label={label as string} title={label as string}
            className="grid h-9 w-9 place-items-center border-b border-concrete-3 last:border-b-0 hover:bg-concrete">
            <Pictogram name={icon as string} size={18} />
          </button>
        ))}
      </div>
    </div>
  );
}

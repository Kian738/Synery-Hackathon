import type { DoorLabel, Geometry, ScenarioMark, ScenarioReport } from "./types";

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const fixed = (n: number, d: number) => String(Number(n.toFixed(d)));

/** People per second through a door of this width: specific flow times the clear width (a boundary layer is lost on each side). */
export function doorRate(widthM: number, params?: { specific_flow?: number; boundary_m?: number }) {
  const flow = params?.specific_flow ?? 1.316, edge = params?.boundary_m ?? 0.15;
  return { flow, edge, clear: widthM - 2 * edge, rate: flow * (widthM - 2 * edge) };
}

/** The tightest door of the minimum cut: the one that sets the pace. */
export function tightestDoor(g: Geometry, r: ScenarioReport) {
  const ids = r.evacuation?.bottleneck ?? [];
  return g.openings.filter(o => ids.includes(o.id)).sort((a, b) => a.width_m - b.width_m)[0];
}

export interface DemoLine { id: "setup" | "flow" | "cut" | "responders" | "fix"; say: string[] }

/** The five spoken beats, each a few short sentences. Every number comes from the report (or the measured scenario for the opening). */
export function demoLines(g: Geometry, r: ScenarioReport, room: string, people: number): DemoLine[] {
  const e = r.evacuation, out: DemoLine[] = [];
  if (!e) return out;
  out.push({ id: "setup", say: [`Fire in ${room}.`, `${people} people are inside.`] });
  out.push({ id: "flow", say: ["We solve it as a flow over time.", `The fastest way out is ${e.T_s} seconds.`] });
  const door = tightestDoor(g, r), n = (e.bottleneck ?? []).length;
  if (door) out.push({ id: "cut", say: [`${WORDS[n] ?? n} doors form the minimum cut and set the time.`, `This one passes ${fixed(doorRate(door.width_m, e.params).rate, 2)} people a second.`] });
  if (r.responder) {
    const d = Math.round(r.responder.delay_s);
    out.push({ id: "responders", say: ["Firefighters go first.", `Evacuees are solved around them: ${d > 0 ? `${d} seconds slower` : "no slower"}.`] });
  }
  const fix = r.answer?.fixes?.[0];
  if (fix) out.push({ id: "fix", say: ["A new door must cross that cut.", `Widening this one saves ${fix.T_before_s - fix.T_after_s} seconds.`] });
  return out;
}

/** Floating labels: capacity on every limiting door (full arithmetic on the tightest), the responder entrance, the proposed fix. */
export function demoLabels(g: Geometry, r: ScenarioReport, show: { cut: boolean; responders: boolean; fix: boolean }): Record<string, DoorLabel> {
  const e = r.evacuation, labels: Record<string, DoorLabel> = {};
  if (!e) return labels;
  const tight = tightestDoor(g, r);
  if (show.cut) for (const o of g.openings.filter(x => (e.bottleneck ?? []).includes(x.id))) {
    const c = doorRate(o.width_m, e.params);
    labels[o.id] = { tone: "amber", text: o.id === tight?.id
      ? `${fixed(c.flow, 3)} x (${fixed(o.width_m, 1)} - ${(2 * c.edge).toFixed(2)}) = ${c.rate.toFixed(2)} people per second`
      : `${c.rate.toFixed(2)} people per second` };
  }
  if (show.responders && r.responder?.elements[0]) labels[r.responder.elements[0]] = { tone: "responder", text: `Responders, in at ${Math.round(r.responder.arrival_s)} s` };
  const fix = r.answer?.fixes?.[0];
  if (show.fix && fix) labels[fix.element] = { tone: "accent", text: `Widen to ${fixed(fix.width_m, 1)} m: ${fix.T_before_s} s to ${fix.T_after_s} s` };
  return labels;
}

/** The three plans compared, longest first scale. Classic heuristic is omitted when the report has none. */
export function compareBars(r: ScenarioReport): { label: string; seconds: number; planned?: boolean }[] {
  const e = r.evacuation;
  if (!e) return [];
  const bars = [{ label: "Planned together (exact)", seconds: e.T_s, planned: true }];
  if (e.ccrp) bars.push({ label: "Classic heuristic", seconds: e.ccrp.T_s, planned: false });
  if (e.nearest_exit) bars.push({ label: "Everyone to the nearest exit", seconds: e.nearest_exit.T_s, planned: false });
  return bars;
}

export interface DoorMark { id: string; floor_id: string; x: number; y: number; text: string; tone: DoorLabel["tone"] }
/** Where the 3D scene floats the door labels. */
export function doorMarks(g: Geometry, mark: ScenarioMark | null): DoorMark[] {
  if (!mark?.labels) return [];
  return g.openings.filter(o => mark.labels![o.id]).map(o => ({ id: o.id, floor_id: o.floor_id, x: o.position[0], y: o.position[1], ...mark.labels![o.id] }));
}

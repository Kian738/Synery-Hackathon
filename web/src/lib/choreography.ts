import type { UiEvent } from "./types";

/** Stage directions for one answer: what the camera frames, what is tinted, numbered, hatched and said on the card.
 *  Pure: chat, voice tour and scenarios can share it. Every UiEvent type maps to one Stage (tests/choreography.test.mjs). */
export interface Lookup { name: (id: string) => string; floorOf: (id: string) => string | null }
export interface Stage {
  kind: UiEvent["type"];
  camera: string[];             // ids to frame (empty: leave the camera alone)
  floor: string | null;
  highlights: string[];         // tinted + outlined
  numbered: { id: string; n: number }[]; // badges 1..n matching numbered chat rows (max 9)
  danger: string[];             // red hatch (closed)
  affected: string[];           // rooms that lose their way out
  line: "draw" | "keep" | "none";
  door: { id: string; tone: "preview" | "added" | "removed" } | null;
  card: { headline: string; proof: string; followUps: string[] };
}

const PROOF = "Computed from the building data";
const base = (kind: UiEvent["type"]): Stage => ({ kind, camera: [], floor: null, highlights: [], numbered: [], danger: [], affected: [], line: "keep", door: null, card: { headline: "", proof: PROOF, followUps: [] } });
const number = (ids: string[]) => ids.slice(0, 9).map((id, i) => ({ id, n: i + 1 }));

export function stageFor(e: UiEvent, look: Lookup): Stage {
  const s = base(e.type);
  switch (e.type) {
    case "route": {
      const r = e.route, to = r.stops.at(-1) ?? "";
      const m = Math.round(r.walk_m ?? r.length_m), min = Math.max(1, Math.round(m / 1.2 / 60));
      return { ...s, camera: [...r.stops], floor: r.polyline[0]?.floor_id ?? null, line: "draw",
        card: { headline: `${look.name(to)}: ${m} m, about ${min} min`, proof: `Shortest walking route${r.constraints.length ? ` · ${r.constraints.join(", ")}` : ""}`,
          followUps: r.constraints.includes("step-free") ? ["Guide me there"] : ["Make it step-free", "Guide me there"] } };
    }
    case "visual_result": {
      const ids = e.result.entities.map(x => x.id);
      return { ...s, camera: ids.slice(0, 9), floor: e.result.entities[0]?.floor_id ?? e.result.floor_ids[0] ?? null, highlights: ids, numbered: number(ids), line: "none",
        card: { headline: e.result.title, proof: e.result.provenance || PROOF, followUps: ids.length ? [`Route to ${look.name(ids[0])}`, `Show all ${ids.length} on the map`] : [] } };
    }
    case "highlight":
      return { ...s, camera: e.ids.slice(0, 9), floor: e.ids[0] ? look.floorOf(e.ids[0]) : null, highlights: e.ids, numbered: number(e.ids), card: { ...s.card, headline: `${e.ids.length} places marked` } };
    case "closure": {
      const cut = e.impact.step_free?.cut_off_ids ?? e.impact.cut_off_ids ?? [];
      return { ...s, camera: [e.id, ...cut.slice(0, 8)], floor: look.floorOf(e.id), danger: e.closed ? [e.id] : [], affected: cut, numbered: number(cut), line: "none",
        card: { headline: e.closed ? `${look.name(e.id)} is closed${cut.length ? `: ${cut.length} rooms lose their way out` : ""}` : `${look.name(e.id)} is open again`,
          proof: "Re-solved every room's way out", followUps: e.closed ? [`Reopen ${look.name(e.id)}`, "Route around it"] : [] } };
    }
    case "preview_door":
      return { ...s, camera: e.door.space_ids.filter(x => x !== "outside"), floor: e.door.floor_id, highlights: e.door.space_ids.filter(x => x !== "outside"), door: { id: e.door.id, tone: "preview" },
        card: { headline: `New door between ${e.door.space_ids.map(look.name).join(" and ")}?`, proof: `${e.impact.shorter_way_out_count} rooms get a shorter way out`, followUps: ["Apply to model"] } };
    case "fix_preview":
      return { ...s, camera: e.opening.space_ids, floor: e.opening.floor_id, highlights: e.opening.space_ids, door: { id: e.opening.id, tone: "preview" },
        card: { headline: `Widen the door to ${e.opening.width_m} m?`, proof: e.fix.verified ? "Checked by re-solving" : PROOF, followUps: ["Apply to model"] } };
    case "edit": {
      const door = e.door as { id?: string; space_ids?: string[] } | undefined;
      const ids = (door?.space_ids ?? []).filter(x => x !== "outside");
      const tone = e.op === "remove_door" ? "removed" : "added";
      return { ...s, camera: ids, floor: ids[0] ? look.floorOf(ids[0]) : null, highlights: ids, door: door?.id && e.op !== "undo" ? { id: door.id, tone } : null,
        card: { headline: e.op === "undo" ? "Undid the last change" : `Model changed: ${e.op.replaceAll("_", " ")}`, proof: "Session edit; routes re-solved", followUps: e.op === "undo" ? [] : ["Undo"] } };
    }
    case "weak_points": {
      const rooms = [...new Set(e.items.flatMap(i => i.room_ids))];
      return { ...s, highlights: rooms, affected: rooms, camera: rooms.slice(0, 9), card: { headline: `${e.items.length} weak points`, proof: `Closed each connector once (${e.profile})`, followUps: [] } };
    }
    case "scenario_result": return { ...s, danger: [e.hazard], camera: [e.hazard], floor: look.floorOf(e.hazard), card: { ...s.card, headline: "Scenario computed" } };
    case "scenario_replay": return { ...s, card: { ...s.card, headline: `Replay: ${e.action}` } };
    case "profile": return { ...s, card: { ...s.card, headline: e.profile.step_free ? "Step-free routes on" : "Profile updated" } };
    case "choice": return { ...s, card: { ...s.card, headline: e.question, followUps: e.options.slice(0, 3) } };
  }
}

import type { FixProposal, Impact } from "./types";

export function impactText(impact: Impact): string {
  const i = impact.your_needs ?? impact.step_free ?? impact;
  const needs = impact.your_needs ? " under your requirements" : impact.step_free ? " step-free" : "";
  if (i.cut_off_count) return `${i.cut_off_count} of ${i.of_rooms ?? "the"} rooms lose their${needs} way out.`;
  if (i.reconnected_ids?.length) return `${i.reconnected_ids.length} rooms regain their${needs} way out.`;
  return i.longer_way_out_count ? `${i.longer_way_out_count} rooms have a longer${needs} way out.` : `No rooms lose their${needs} way out.`;
}

/** The proposal card text. Every figure is the backend's own re-solve; this only words it. */
export function fixCardText(fix: FixProposal): string {
  const doors = fix.widen.map((w) => `${w.between.join(" and ")} from ${w.from_m} m to ${w.to_m} m`).join("; ");
  const reach = fix.rooms_reachable_before != null && fix.rooms_reachable_after != null && fix.of_rooms
    ? ` Rooms reachable from here: ${fix.rooms_reachable_before} of ${fix.of_rooms} now, ${fix.rooms_reachable_after} of ${fix.of_rooms} after.`
    : "";
  return `${fix.reason.replace(/\.$/, "")}. Widen ${doors}. Checked by re-solving.${reach}`;
}

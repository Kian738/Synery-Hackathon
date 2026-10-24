import type { Impact } from "./types";

export function impactText(impact: Impact): string {
  const i = impact.your_needs ?? impact.step_free ?? impact;
  const needs = impact.your_needs ? " under your requirements" : impact.step_free ? " step-free" : "";
  if (i.cut_off_count) return `${i.cut_off_count} of ${i.of_rooms ?? "the"} rooms lose their${needs} way out.`;
  if (i.reconnected_ids?.length) return `${i.reconnected_ids.length} rooms regain their${needs} way out.`;
  return i.longer_way_out_count ? `${i.longer_way_out_count} rooms have a longer${needs} way out.` : `No rooms lose their${needs} way out.`;
}

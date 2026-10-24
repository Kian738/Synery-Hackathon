import type { Icon } from "./protocol";

// Small signage pictograms, drawn with stroke so they stay legible at any size. Always paired with text by the caller.
const PATHS: Record<Icon, string> = {
  start: "M12 4a5 5 0 1 1 0 10a5 5 0 0 1 0-10zM12 14v6",
  straight: "M12 20V5M6 11l6-6 6 6",
  left: "M18 20v-6a4 4 0 0 0-4-4H6M10 5l-5 5 5 5",
  right: "M6 20v-6a4 4 0 0 1 4-4h8M14 5l5 5-5 5",
  back: "M6 4v6a4 4 0 0 0 4 4h8M14 9l5 5-5 5",
  lift: "M5 3h14v18H5zM12 7l-3 3h6zM12 17l3-3H9z",
  stairs: "M4 20h4v-4h4v-4h4V8h4M4 20V10",
  outside: "M5 20V6l7-3 7 3v14M10 20v-6h4v6",
  arrive: "M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11zM12 7.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 0 0 0-5z",
};

export function Glyph({ icon, label }: { icon: Icon; label?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <path d={PATHS[icon] ?? PATHS.straight} />
    </svg>
  );
}

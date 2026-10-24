import type React from "react";

// Signage-style pictograms (ISO 7001/7010-inspired), drawn as simple strokes so they read at 20 px.

const PATHS: Record<string, React.ReactNode> = {
  start: <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />,
  straight: <path d="M12 20V5M6 11l6-6 6 6" />,
  left: <path d="M17 20v-7a4 4 0 0 0-4-4H5M10 4L5 9l5 5" />,
  right: <path d="M7 20v-7a4 4 0 0 1 4-4h8M14 4l5 5-5 5" />,
  back: <path d="M7 20V9a5 5 0 0 1 10 0v4M13 9l4 4 4-4" />,
  lift: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="1" />
      <path d="M9 10l3-3 3 3M9 14l3 3 3-3" />
    </>
  ),
  stairs: <path d="M3 20h5v-5h5v-5h5V5h3" />,
  outside: <path d="M14 4h6v16h-6M3 12h11M9 7l5 5-5 5" />,
  arrive: (
    <>
      <path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" />
      <circle cx="12" cy="9.5" r="2.5" />
    </>
  ),
  wc: <path d="M7 4.5a1.5 1.5 0 1 0 0 .1M17 4.5a1.5 1.5 0 1 0 0 .1M5 21v-7H4l1-6h4l1 6H9v7M15 21v-6h-2l2-7h4l2 7h-2v6M12 3v18" />,
  coffee: <path d="M4 9h12v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM16 11h2a2 2 0 0 1 0 4h-2M8 3c0 1.5 1 1.5 1 3M12 3c0 1.5 1 1.5 1 3" />,
  kitchen: <path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M16 3c-2 0-3 3-3 7h3v11" />,
  meeting: <path d="M3 18h18M6 18v-6h12v6M9 8a3 3 0 1 0 6 0 3 3 0 0 0-6 0" />,
  exit: <path d="M13 4h7v16h-7M4 12h10M10 8l4 4-4 4" />,
  aid: <path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z" />,
  printer: <path d="M7 8V3h10v5M5 8h14a2 2 0 0 1 2 2v6h-4M3 16v-6a2 2 0 0 1 2-2M7 14h10v7H7z" />,
  lab: <path d="M9 3h6M10 3v6l-5 10a1 1 0 0 0 1 2h12a1 1 0 0 0 1-2l-5-10V3M7.5 15h9" />,
  mic: <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3" />,
  speaker: <path d="M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12" />,
  wheelchair: <path d="M11 4a1.5 1.5 0 1 0 0 .1M11 7v6h5l2 5M11 10h5M8.5 11.5A5 5 0 1 0 15 18" />,
  pin: <path d="M12 21s6-5.5 6-10.5a6 6 0 0 0-12 0C6 15.5 12 21 12 21zM12 8v4" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  fit: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  up: <path d="M12 5v14M6 11l6-6 6 6" />,
  down: <path d="M12 19V5M6 13l6 6 6-6" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  send: <path d="M4 12l16-8-6 16-2-6z" />,
  here: (
    <>
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="8" />
    </>
  ),
};

export function Pictogram({ name, size = 20, className = "", title }: { name: string; size?: number; className?: string; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="square"
      strokeLinejoin="miter"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {PATHS[name] ?? PATHS.pin}
    </svg>
  );
}

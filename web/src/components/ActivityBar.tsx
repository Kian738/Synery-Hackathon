import { useActivity } from "../lib/activity";

/** Always-visible sign that the app is working: a thin sliding bar after 200 ms, then a named status with a stopwatch, then an honest note
 *  when it takes long. Silent (nothing drawn) for fast requests, so quick answers do not flicker. */
export function ActivityBar() {
  const { busy, label, elapsed } = useActivity();
  if (!busy || elapsed < 0.2) return null;
  const seconds = Math.floor(elapsed);
  return (
    <div className="k-activity" aria-live="polite" data-slow={elapsed > 8}>
      <span className="k-activity-bar" aria-hidden="true" />
      {elapsed >= 1.2 && (
        <span className="k-activity-pill">
          <i aria-hidden="true" />
          {label}…{seconds >= 2 ? ` ${seconds} s` : ""}
          {elapsed > 8 && <em>Large buildings take a moment</em>}
        </span>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { floorColor } from "../lib/floorColors";

const PHRASES = ["Raising the floors", "Setting the walls", "Placing the furniture", "Finding the stairs and lifts"];

/** The loading screen: four floors of an isometric building stack up one after the other in the app's floor colours, with a phrase that
 *  follows the work. Pure SVG and CSS; with reduced motion the stack is simply drawn. */
export function Loader({ label, phrases = PHRASES }: { label?: string; phrases?: string[] }) {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI(v => (v + 1) % phrases.length), 1800); return () => clearInterval(t); }, [phrases.length]);
  return (
    <div className="k-loader" role="status" aria-live="polite">
      <svg viewBox="0 0 120 110" width="132" aria-hidden="true">
        {[0, 1, 2, 3].map(level => {
          const y = 78 - level * 17;
          return (
            <g key={level} className="k-loader-floor" style={{ animationDelay: `${level * 0.28}s`, ["--fc" as string]: floorColor(level) }}>
              <path d={`M60 ${y + 14} L104 ${y - 8} L60 ${y - 30} L16 ${y - 8} Z`} fill="var(--fc)" fillOpacity=".92" stroke="#0c1317" strokeWidth="1.2" strokeLinejoin="round" />
              <path d={`M16 ${y - 8} L16 ${y - 3} L60 ${y + 19} L60 ${y + 14} Z`} fill="#0c1317" fillOpacity=".35" />
              <path d={`M104 ${y - 8} L104 ${y - 3} L60 ${y + 19} L60 ${y + 14} Z`} fill="#0c1317" fillOpacity=".55" />
            </g>
          );
        })}
      </svg>
      {label && <strong>{label}</strong>}
      <span>{phrases[i]}…</span>
    </div>
  );
}

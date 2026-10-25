import { useEffect, useRef, type ReactNode } from "react";
import { Pictogram } from "../components/Pictogram";

/** Control kit primitives. Sizes, radii and gaps come from kit.css only. */
export function Dock({ children, col, className = "" }: { children: ReactNode; col?: boolean; className?: string }) {
  return <div className={`k-dock${col ? " col" : ""} ${className}`}>{children}</div>;
}

export function IconButton({ label, icon, text, pressed, disabled, onClick, accent, badge, ariaLabel, tip = true, className = "" }: {
  label: string; icon?: string; text?: string; pressed?: boolean; disabled?: boolean; onClick?: () => void; accent?: boolean; badge?: number; ariaLabel?: string; tip?: boolean; className?: string;
}) {
  return (
    <button type="button" className={`k-ctl${text ? "" : " icon"}${accent ? " accent" : ""} ${className}`} aria-label={ariaLabel ?? label} data-tip={tip && !text ? label : undefined}
      aria-pressed={pressed} disabled={disabled} onClick={onClick}>
      {icon && <Pictogram name={icon} size={18} />}{text && <span>{text}</span>}
      {!!badge && <span className="k-badge">{badge}</span>}
    </button>
  );
}

export interface SegOption<T extends string> { value: T; label: string; ariaLabel?: string; icon?: string; disabled?: boolean; tip?: string }
export function Segmented<T extends string>({ value, options, onChange, ariaLabel }: { value: T; options: SegOption<T>[]; onChange: (v: T) => void; ariaLabel: string }) {
  return (
    <div className="k-seg" role="group" aria-label={ariaLabel}>
      {options.map(o => (
        <button key={o.value} type="button" aria-pressed={value === o.value} aria-label={o.ariaLabel ?? o.label} disabled={o.disabled} data-tip={o.tip}
          onClick={() => onChange(o.value)}>{o.icon && <Pictogram name={o.icon} size={16} />}<span>{o.label}</span></button>
      ))}
    </div>
  );
}

export function Popover({ label, icon, open, onOpenChange, badge, children, left, className = "", trigger }: {
  trigger?: ReactNode; label: string; icon: string; open: boolean; onOpenChange: (v: boolean) => void; badge?: number; children: ReactNode; left?: boolean; className?: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (root.current && !root.current.contains(e.target as Node)) onOpenChange(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onOpenChange(false); };
    addEventListener("pointerdown", outside); addEventListener("keydown", key);
    return () => { removeEventListener("pointerdown", outside); removeEventListener("keydown", key); };
  }, [open, onOpenChange]);
  return (
    <div className={`k-pop ${className}`} ref={root}>
      {trigger ?? <IconButton label={label} icon={icon} pressed={open} badge={badge} onClick={() => onOpenChange(!open)} />}
      {/* kept mounted so panels owned by menu items (the phone pairing card) survive closing the menu */}
      <div className={`k-pop-panel${left ? " left" : ""}`} role="menu" hidden={!open}>{children}</div>
    </div>
  );
}

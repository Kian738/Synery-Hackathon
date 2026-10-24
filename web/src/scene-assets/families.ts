// Procedural silhouettes. Each builder writes metre-based parts into a PartBuilder; the builder clips ground
// geometry to the supplied footprint. `b.interior` adds detail that only matters at eye level.
// Convention: origin footprint centre on the floor, forward / operator side is -Z, back is +Z.
// Elongated vehicles (forklift, pallet jack) point toward -X along their long axis.
import { PALETTE as P, type PartBuilder } from "./parts";

export type Build = (b: PartBuilder) => void;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
/** Positions of n items spread evenly over length L, centred on 0. */
const spread = (n: number, L: number) => Array.from({ length: n }, (_, i) => -L / 2 + (i + 0.5) * (L / n));

// ---------- seating ----------

export function chair(o: { seat?: number; back?: number; color?: string; leg?: string; arms?: boolean } = {}): Build {
  const seat = o.seat ?? 0.45, back = o.back ?? 0.88, color = o.color ?? P.fabric, leg = o.leg ?? P.metalDark;
  return b => {
    const sw = b.w * 0.92, sd = b.d * 0.92, bt = Math.min(0.06, sd * 0.2);
    b.box(0, seat - 0.06, 0, sw, 0.06, sd, color);
    b.box(0, seat, b.hd - sd * 0.04 - bt / 2, sw, back - seat, bt, color);
    if (!b.interior) { b.box(0, 0, 0, sw * 0.45, seat - 0.06, sd * 0.45, leg); return; }
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (sw / 2 - 0.03), 0, z * (sd / 2 - 0.03), 0.04, seat - 0.06, 0.04, leg);
    if (o.arms) for (const x of [-1, 1]) b.box(x * (sw / 2 - 0.02), seat, 0, 0.04, 0.2, sd * 0.7, leg);
  };
}

export function officeChair(): Build {
  return b => {
    const dm = Math.min(b.w, b.d) * 0.88;
    b.cyl(0, 0.04, 0, dm, 0.04, P.metalDark);
    b.cyl(0, 0.08, 0, 0.06, 0.34, P.steel);
    b.box(0, 0.42, 0, b.w * 0.8, 0.08, b.d * 0.8, P.charcoal);
    b.box(0, 0.5, b.d * 0.33, b.w * 0.76, 0.46, 0.07, P.charcoal);
    if (!b.interior) return;
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.sph(x * dm * 0.36, 0.025, z * dm * 0.36, 0.05, P.black);
    for (const x of [-1, 1]) { b.box(x * b.w * 0.4, 0.5, -b.d * 0.02, 0.04, 0.03, b.d * 0.4, P.black); b.box(x * b.w * 0.4, 0.42, 0, 0.03, 0.08, 0.05, P.black); }
  };
}

export function sofa(): Build {
  return b => {
    const arm = clamp(b.w * 0.12, 0.08, 0.2), backT = Math.min(0.2, b.d * 0.28);
    b.box(0, 0.05, 0, b.w, 0.33, b.d, P.fabric);
    b.box(0, 0.38, b.hd - backT / 2, b.w, 0.42, backT, P.fabric);
    for (const x of [-1, 1]) b.box(x * (b.hw - arm / 2), 0.38, 0, arm, 0.22, b.d - backT, "#4a6173");
    if (!b.interior) return;
    const n = clamp(Math.round((b.w - 2 * arm) / 0.65), 1, 4), cw = (b.w - 2 * arm) / n;
    spread(n, b.w - 2 * arm).forEach(x => {
      b.box(x, 0.38, -backT / 2, cw - 0.02, 0.12, b.d - backT - 0.02, "#617c90");
      b.box(x, 0.5, b.hd - backT - 0.06, cw - 0.04, 0.3, 0.12, "#617c90");
    });
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.05), 0, b.hd - 0.05, 0.05, 0.05, 0.05, P.black);
  };
}

export function armchair(): Build {
  return b => {
    const arm = clamp(b.w * 0.14, 0.08, 0.14), backT = Math.min(0.2, b.d * 0.26);
    b.box(0, 0.05, 0, b.w, 0.33, b.d, P.fabricWarm);
    b.box(0, 0.38, b.hd - backT / 2, b.w, 0.45, backT, P.fabricWarm);
    for (const x of [-1, 1]) b.box(x * (b.hw - arm / 2), 0.38, 0, arm, 0.24, b.d - backT, "#7b5d4e");
    if (b.interior) b.box(0, 0.38, -backT / 2, b.w - 2 * arm - 0.02, 0.12, b.d - backT - 0.02, "#9a7767");
  };
}

export function bed(single: boolean): Build {
  return b => {
    b.box(0, 0.1, 0, b.w, 0.22, b.d, P.woodDark);
    b.box(0, 0.32, -b.d * 0.03, b.w * 0.94, 0.2, b.d * 0.9, P.bed);
    b.box(0, 0.1, b.hd - 0.04, b.w, 0.8, 0.08, P.woodDark);
    const n = single || b.w < 1.2 ? 1 : 2, pw = Math.min(0.6, b.w / n * 0.8);
    if (!b.interior) { b.box(0, 0.52, b.hd - 0.3, b.w * 0.8, 0.1, 0.38, P.pillow); return; }
    spread(n, b.w).forEach(x => b.box(x, 0.52, b.hd - 0.3, pw, 0.1, 0.38, P.pillow));
    b.box(0, 0.52, -b.d * 0.14, b.w * 0.92, 0.04, b.d * 0.5, P.blanket);
    b.box(0, 0.1, -b.hd + 0.03, b.w, 0.4, 0.06, P.woodDark);
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - 0.04), 0, z * (b.hd - 0.04), 0.06, 0.1, 0.06, P.black);
  };
}

export function lectureSeatingRow(): Build {
  return b => {
    const n = clamp(Math.round(b.w / 0.55), 2, 10);
    b.box(0, 0.72, -b.hd + 0.15, b.w, 0.04, 0.3, P.wood);
    b.box(0, 0.4, b.d * 0.12, b.w, 0.06, Math.min(0.45, b.d * 0.5), P.fabric);
    b.box(0, 0.46, b.hd - 0.05, b.w, 0.45, 0.06, P.fabric);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.03), 0, 0, 0.06, 0.74, b.d, P.metalDark);
    if (!b.interior) return;
    for (let i = 1; i < n; i++) b.box(-b.hw + i * (b.w / n), 0.4, b.d * 0.12, 0.02, 0.5, Math.min(0.45, b.d * 0.5), P.black);
    spread(n, b.w).forEach(x => { b.box(x, 0.46, b.hd - 0.12, b.w / n - 0.06, 0.4, 0.05, "#617c90"); });
  };
}

// ---------- tables, desks, counters ----------

export function table(o: { h: number; top?: string; leg?: string; topT?: number; style?: "legs" | "panels" | "pedestal"; inset?: number } = { h: 0.75 }): Build {
  const h = o.h, topT = o.topT ?? 0.04, top = o.top ?? P.wood, leg = o.leg ?? P.metalDark, style = o.style ?? "legs";
  return b => {
    b.box(0, h - topT, 0, b.w, topT, b.d, top);
    if (style === "pedestal") {
      b.cyl(0, 0, 0, Math.min(b.w, b.d) * 0.55, 0.04, leg);
      b.cyl(0, 0.04, 0, 0.08, h - topT - 0.04, leg);
      return;
    }
    const inset = o.inset ?? 0.04;
    if (!b.interior) { for (const x of [-1, 1]) b.box(x * (b.hw - inset - 0.03), 0, 0, 0.06, h - topT, b.d * 0.8, leg); return; }
    if (style === "panels") {
      for (const x of [-1, 1]) b.box(x * (b.hw - inset - 0.025), 0, 0, 0.05, h - topT, b.d * 0.8, leg);
      b.box(0, h - topT - 0.2, b.hd - inset - 0.05, b.w - 2 * inset - 0.1, 0.2, 0.02, leg);
      return;
    }
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - inset - 0.025), 0, z * (b.hd - inset - 0.025), 0.05, h - topT, 0.05, leg);
    b.box(0, h - topT - 0.08, 0, b.w - 2 * inset, 0.05, 0.03, leg);
  };
}

export function desk(): Build {
  return b => {
    const ped = Math.min(0.45, b.w * 0.3);
    b.box(0, 0.72, 0, b.w, 0.04, b.d, P.wood);
    b.box(-(b.hw - 0.03), 0, 0, 0.05, 0.72, b.d * 0.92, P.woodDark);
    b.box(b.hw - ped / 2, 0, 0, ped, 0.72, b.d * 0.94, P.woodDark);
    if (!b.interior) return;
    b.box(-(b.w - ped) / 2 + 0.02, 0.28, b.hd - 0.04, b.w - ped - 0.05, 0.4, 0.02, P.woodDark);
    [0.5, 0.32, 0.14].forEach(y => { b.box(b.hw - ped / 2, y, -b.hd + 0.02, ped - 0.04, 0.17, 0.02, P.wood); b.box(b.hw - ped / 2, y + 0.12, -b.hd + 0.045, 0.12, 0.02, 0.03, P.steel); });
  };
}

export function labBench(): Build {
  return b => {
    b.box(0, 0.86, 0, b.w, 0.04, b.d, P.black);
    b.box(0, 0.08, 0, b.w * 0.97, 0.78, b.d * 0.9, P.offWhite);
    b.box(0, 0, 0, b.w * 0.95, 0.08, b.d * 0.85, P.black);
    const riser = b.w > 1.6;
    if (riser) {
      b.box(0, 0.9, b.d * 0.05, b.w * 0.96, 0.03, 0.1, P.steel);
      b.box(0, 1.35, b.d * 0.05, b.w * 0.96, 0.03, 0.2, P.steel);
      for (const x of [-1, 1]) b.box(x * (b.hw - 0.05), 0.9, b.d * 0.05, 0.04, 0.46, 0.06, P.steel);
    }
    if (!b.interior) return;
    const n = clamp(Math.round(b.w / 0.6), 1, 6);
    spread(n, b.w * 0.97).slice(1).forEach(x => b.box(x - b.w * 0.97 / n / 2, 0.1, -b.hd * 0.9 - 0.0, 0.015, 0.72, 0.02, P.black));
    if (riser) { for (const x of spread(3, b.w * 0.7)) b.cyl(x, 0.9, b.d * 0.05, 0.06, 0.18, P.glass); b.cyl(0, 0.9, -b.d * 0.15, 0.025, 0.14, P.steel); }
  };
}

export function workbench(o: { assembly?: boolean; packing?: boolean; steel?: boolean } = {}): Build {
  return b => {
    const top = o.steel ? P.steelLight : P.wood;
    b.box(0, 0.86, 0, b.w, 0.05, b.d, top);
    if (!b.interior) {
      for (const x of [-1, 1]) b.box(x * (b.hw - 0.05), 0, 0, 0.06, 0.86, b.d * 0.9, P.metalDark);
      if (o.assembly || o.packing) b.box(0, 1.35, b.hd - 0.04, b.w, 0.06, 0.08, P.steel);
      return;
    }
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - 0.05), 0, z * (b.hd - 0.05), 0.06, 0.86, 0.06, P.metalDark);
    b.box(0, 0.2, 0, b.w - 0.1, 0.04, b.d - 0.1, P.metal);
    if (o.assembly) {
      for (const x of [-1, 1]) b.box(x * (b.hw - 0.04), 0.9, b.hd - 0.04, 0.05, 0.6, 0.05, P.metalDark);
      b.box(0, 1.5, b.hd - 0.04, b.w, 0.05, 0.12, P.steel);
      spread(clamp(Math.round(b.w / 0.5), 2, 5), b.w - 0.2).forEach(x => b.box(x, 0.91, b.hd - 0.12, 0.25, 0.1, 0.16, P.blue));
    }
    if (o.packing) {
      for (const x of [-1, 1]) b.box(x * (b.hw - 0.04), 0.9, b.hd - 0.04, 0.05, 0.6, 0.05, P.metalDark);
      b.cylX(0, 1.5, b.hd - 0.06, b.w - 0.1, 0.1, P.wood);
      b.box(-b.w * 0.25, 0.91, -b.d * 0.1, 0.5, 0.08, 0.4, "#b99363");
      b.box(b.w * 0.2, 0.91, 0, 0.3, 0.06, 0.3, P.steelLight);
    }
  };
}

export function receptionDesk(): Build {
  return b => {
    const frontD = Math.min(0.3, b.d * 0.4);
    b.box(0, 0, -b.hd + frontD / 2, b.w, 1.05, frontD, P.woodDark);
    b.box(0, 1.05, -b.hd + (frontD + 0.1) / 2, b.w, 0.05, frontD + 0.1, P.white);
    b.box(0, 0.7, b.d * 0.15, b.w - 0.1, 0.05, b.d * 0.6, P.wood);
    if (!b.interior) { b.box(0, 0, b.hd - 0.04, b.w - 0.1, 0.7, 0.05, P.woodDark); return; }
    b.box(0, 0, b.hd - 0.04, b.w - 0.1, 0.7, 0.05, P.woodDark);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.05), 0, b.d * 0.15, 0.05, 0.7, b.d * 0.6, P.woodDark);
    b.box(0, 0.45, -b.hd + frontD + 0.02, b.w * 0.6, 0.02, 0.01, P.steel);
  };
}

export function counter(o: { h?: number; kitchen?: boolean; serving?: boolean } = {}): Build {
  const h = o.h ?? 0.86;
  return b => {
    const cols = clamp(Math.round(b.w / 0.6), 1, 8);
    b.box(0, 0.08, 0, b.w, h - 0.08, b.d, o.serving ? P.steelLight : P.offWhite);
    b.box(0, h, 0, b.w, 0.04, b.d, o.serving ? P.steel : P.charcoal);
    if (!b.interior) { b.box(0, 0, 0, b.w * 0.98, 0.08, b.d * 0.9, P.black); if (o.kitchen) b.box(0, h + 0.04, b.hd - 0.01, b.w, 0.3, 0.02, P.offWhite); return; }
    b.box(0, 0, 0, b.w * 0.98, 0.08, b.d * 0.9, P.black);
    spread(cols, b.w).forEach(x => { b.box(x, 0.12, -b.hd + 0.01, b.w / cols - 0.03, h - 0.16, 0.02, o.serving ? P.steel : P.wood); b.box(x, h - 0.1, -b.hd + 0.03, Math.min(0.12, b.w / cols * 0.5), 0.02, 0.03, P.steel); });
    if (o.kitchen) b.box(0, h + 0.04, b.hd - 0.01, b.w, 0.3, 0.02, P.offWhite);
    if (o.serving) {
      b.cylX(0, h - 0.08, -b.hd + 0.03, b.w, 0.03, P.steel);
      spread(clamp(Math.round(b.w / 0.8), 2, 5), b.w - 0.2).forEach(x => b.box(x, h + 0.04, 0, 0.5, 0.02, b.d - 0.2, P.metalDark));
    }
  };
}

export function lectern(): Build {
  return b => {
    b.box(0, 0, b.d * 0.05, b.w * 0.8, 0.12, b.d * 0.8, P.metalDark);
    b.box(0, 0.12, b.d * 0.08, b.w * 0.7, 0.8, b.d * 0.6, P.woodDark);
    b.tilt(0, 1.0, -b.d * 0.02, b.w * 0.88, 0.04, b.d * 0.64, -0.3, P.wood);
    if (b.interior) b.box(0, 0.98, -b.hd + 0.05, b.w * 0.8, 0.03, 0.04, P.steel);
  };
}

// ---------- cabinets and storage ----------

interface CabinetOpts { h: number; body: string; front: string; rows?: number; cols?: number; handle?: string; plinth?: boolean; top?: string; vents?: boolean; wheels?: boolean; band?: string }
export function cabinet(o: CabinetOpts): Build {
  return b => {
    const y0 = o.plinth && b.interior ? 0.08 : 0;
    const rows = o.rows ?? 1;
    let cols = o.cols ?? 1;
    if (!b.interior && rows * cols > 5) cols = rows > 1 ? 1 : Math.min(cols, 6);
    if (b.interior && rows * cols > 12) cols = clamp(Math.floor(12 / rows), 1, cols);
    if (o.plinth && b.interior) b.box(0, 0, 0, b.w - 0.04, 0.08, b.d - 0.04, P.black);
    b.box(0, y0, 0, b.w, o.h - y0, b.d, o.body);
    if (o.top) b.box(0, o.h - 0.03, 0, b.w, 0.03, b.d, o.top);
    const usable = o.h - y0 - (o.top ? 0.03 : 0) - 0.05, rh = usable / rows, cw = b.w / cols;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const x = -b.hw + (c + 0.5) * cw, y = y0 + 0.03 + r * rh;
      b.box(x, y + 0.01, -b.hd + 0.01, cw - 0.03, rh - 0.03, 0.02, o.front);
      if (b.interior) {
        const hw = Math.min(0.14, cw * 0.4);
        if (o.handle) (rows > 1 ? b.box(x, y + rh * 0.62, -b.hd + 0.03, hw, 0.02, 0.03, o.handle) : b.box(x + (cols > 1 ? (c % 2 ? -1 : 1) * cw * 0.35 : cw * 0.38), y + rh * 0.5, -b.hd + 0.03, 0.02, Math.min(0.2, rh * 0.25), 0.03, o.handle));
        if (o.vents) { b.box(x, y + rh * 0.82, -b.hd + 0.02, cw * 0.5, 0.02, 0.02, P.black); b.box(x, y + rh * 0.76, -b.hd + 0.02, cw * 0.5, 0.02, 0.02, P.black); }
      }
    }
    if (o.band) b.box(0, o.h * 0.5, -b.hd + 0.02, b.w, 0.05, 0.02, o.band);
    if (o.wheels && b.interior) for (const x of [-1, 1]) b.sph(x * (b.hw - 0.06), 0.04, b.hd - 0.08, 0.08, P.black);
  };
}

export function bookshelf(o: { h: number; levels: number; color: string; fills: string[]; closedBack?: boolean; posts?: boolean }): Build {
  return b => {
    const t = 0.03, inner = o.h - t;
    if (o.posts) {
      for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - 0.025), 0, z * (b.hd - 0.025), 0.05, o.h, 0.05, P.metalDark);
    } else {
      for (const x of [-1, 1]) b.box(x * (b.hw - t / 2), 0, 0, t, o.h, b.d, o.color);
      b.box(0, 0, b.hd - 0.01, b.w, o.h, 0.02, P.charcoal);
    }
    const levels = b.interior ? o.levels : Math.min(o.levels, o.posts ? 3 : 4);
    const step = (inner - 0.05) / levels;
    for (let i = 0; i <= levels; i++) b.box(0, i === levels ? o.h - t : 0.05 + i * step - (i ? 0 : 0.05), 0, b.w - (o.posts ? 0 : 2 * t), t, b.d, o.posts ? P.steel : o.color);
    if (!b.interior) return;
    for (let i = 0; i < levels; i++) {
      const y = 0.05 + i * step + t, ch = step - t - 0.04;
      const widths = [0.28, 0.22, 0.3].map(f => f * (b.w - 0.1));
      let x = -b.hw + 0.06 + (b.w - 0.1 - widths.reduce((s, v) => s + v, 0)) / 2;
      widths.forEach((cw, k) => { b.box(x + cw / 2, y, 0, cw - 0.015, ch * (k % 2 ? 0.8 : 0.95), b.d * 0.7, o.fills[(i + k) % o.fills.length]); x += cw; });
    }
  };
}

export function palletRack(): Build {
  return b => {
    const H = 2.6;
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - 0.04), 0, z * (b.hd - 0.04), 0.08, H, 0.08, P.blue);
    const ys = [0.3, 1.3, 2.3];
    if (!b.interior) { ys.forEach(y => b.box(0, y, 0, b.w, 0.1, b.d, P.orange)); return; }
    ys.forEach(y => { for (const z of [-1, 1]) b.box(0, y, z * (b.hd - 0.04), b.w - 0.1, 0.1, 0.05, P.orange); });
    ys.forEach(y => b.box(0, y + 0.1, 0, b.w - 0.2, 0.14, b.d - 0.2, P.wood));
    for (const z of [-1, 1]) b.box(0, 0.15, z * (b.hd - 0.04), b.w - 0.1, 0.05, 0.04, P.blue);
  };
}

export function coatRack(): Build {
  return b => {
    b.cyl(0, 0, 0, Math.min(0.3, b.w), 0.03, P.metalDark);
    b.cyl(0, 0.03, 0, 0.035, 1.72, P.metalDark);
    b.box(0, 1.68, 0, Math.min(0.5, b.w), 0.025, 0.03, P.steel);
    if (b.interior) { b.box(0, 1.56, 0, 0.03, 0.025, Math.min(0.5, b.d), P.steel); b.box(0, 1.72, 0, Math.min(0.4, b.w), 0.02, 0.02, P.steel); }
  };
}

export function wasteBasket(): Build {
  return b => {
    const dm = Math.min(b.w, b.d) * 0.82;
    b.cyl(0, 0, 0, dm, 0.7, P.metal);
    b.cyl(0, 0.7, 0, dm * 1.0, 0.04, P.metalDark);
    if (b.interior) b.cyl(0, 0.74, 0, dm * 0.8, 0.01, P.black);
  };
}

export function plant(): Build {
  return b => {
    const dm = Math.min(b.w, b.d), pot = dm * 0.7;
    b.cyl(0, 0, 0, pot, 0.32, P.pot);
    b.cyl(0, 0.32, 0, 0.03, 0.2, P.woodDark);
    b.sph(0, 0.75, 0, dm * 0.9, P.leaf, 0.7);
    if (!b.interior) return;
    b.cyl(0, 0.32, 0, pot * 0.9, 0.02, P.soil);
    b.sph(-dm * 0.18, 0.95, dm * 0.1, dm * 0.5, P.leafLight, 0.45);
    b.sph(dm * 0.18, 0.62, -dm * 0.12, dm * 0.5, P.leafLight, 0.4);
    b.sph(dm * 0.05, 1.12, 0, dm * 0.45, P.leaf, 0.4);
  };
}

// ---------- kitchen and office appliances ----------

export function fridge(): Build {
  return b => {
    b.box(0, 0.04, 0, b.w, 1.76, b.d, P.white);
    b.box(0, 0, 0, b.w * 0.9, 0.04, b.d * 0.9, P.black);
    b.box(0, 1.2, -b.hd + 0.01, b.w - 0.02, 0.02, 0.02, P.metalDark);
    for (const y of [1.3, 0.8]) b.box(b.hw - 0.06, y, -b.hd + 0.03, 0.025, 0.28, 0.03, P.steel);
    if (b.interior) b.box(0, 0.5, -b.hd + 0.01, b.w - 0.04, 0.01, 0.01, P.offWhite);
  };
}

export function dishwasher(): Build {
  return b => {
    b.box(0, 0.06, 0, b.w, 0.8, b.d, P.steel);
    b.box(0, 0, 0, b.w * 0.92, 0.06, b.d * 0.9, P.black);
    b.box(0, 0.76, -b.hd + 0.01, b.w - 0.04, 0.08, 0.02, P.charcoal);
    b.cylX(0, 0.68, -b.hd + 0.04, b.w * 0.7, 0.025, P.steelLight);
    if (b.interior) { b.box(-b.w * 0.2, 0.78, -b.hd + 0.025, 0.06, 0.03, 0.01, P.ledGreen); b.box(0, 0.62, -b.hd + 0.01, b.w - 0.04, 0.012, 0.01, P.black); }
  };
}

export function stove(): Build {
  return b => {
    b.box(0, 0.06, 0, b.w, 0.82, b.d, P.white);
    b.box(0, 0, 0, b.w * 0.92, 0.06, b.d * 0.9, P.black);
    b.box(0, 0.88, 0, b.w, 0.03, b.d, P.black);
    spread(2, b.w * 0.6).forEach(x => spread(2, b.d * 0.6).forEach(z => b.cyl(x, 0.91, z, Math.min(b.w, b.d) * 0.3, 0.015, P.charcoal)));
    if (!b.interior) return;
    b.box(0, 0.2, -b.hd + 0.01, b.w * 0.8, 0.45, 0.02, P.glassDark);
    b.cylX(0, 0.7, -b.hd + 0.04, b.w * 0.7, 0.025, P.steelLight);
    spread(4, b.w * 0.7).forEach(x => b.cyl(x, 0.82, -b.hd + 0.02, 0.035, 0.03, P.black));
    b.box(0, 0.91, b.hd - 0.015, b.w, 0.12, 0.03, P.white);
  };
}

export function microwave(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.9, 0.82, b.d * 0.9, P.offWhite);
    b.box(0, 0.82, 0, b.w, 0.24, b.d, P.steel);
    b.box(-b.w * 0.12, 0.86, -b.hd + 0.01, b.w * 0.6, 0.16, 0.02, P.glassDark);
    if (b.interior) { b.box(b.w * 0.34, 0.86, -b.hd + 0.01, b.w * 0.18, 0.16, 0.02, P.charcoal); b.box(b.w * 0.34, 0.97, -b.hd + 0.015, 0.05, 0.02, 0.01, P.ledGreen); }
  };
}

export function coffeeMachine(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.92, 0.85, b.d * 0.92, P.offWhite);
    b.box(0, 0.85, b.d * 0.08, b.w, 0.5, b.d * 0.84, P.charcoal);
    b.box(0, 0.78, -b.hd + 0.06, b.w * 0.7, 0.04, 0.12, P.steel);
    if (!b.interior) return;
    b.box(0, 1.38, b.d * 0.05, b.w * 0.6, 0.1, b.d * 0.5, P.black);
    b.cyl(0, 1.0, -b.hd + 0.1, 0.03, 0.12, P.steelLight);
    b.box(0, 1.2, -b.hd + 0.07, b.w * 0.5, 0.1, 0.02, P.screen);
    b.box(0, 0.86, -b.hd + 0.07, b.w * 0.6, 0.02, 0.12, P.black);
  };
}

export function waterDispenser(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.92, 0.95, b.d * 0.92, P.offWhite);
    b.cyl(0, 0.95, 0, Math.min(b.w, b.d) * 0.75, 0.45, P.blue);
    if (!b.interior) return;
    b.box(-b.w * 0.15, 0.62, -b.hd + 0.03, 0.05, 0.06, 0.05, P.red);
    b.box(b.w * 0.15, 0.62, -b.hd + 0.03, 0.05, 0.06, 0.05, P.blue);
    b.box(0, 0.45, -b.hd + 0.05, b.w * 0.7, 0.03, 0.1, P.steel);
  };
}

export function vendingMachine(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 1.85, b.d, P.red);
    b.box(-b.w * 0.12, 0.45, -b.hd + 0.01, b.w * 0.62, 1.25, 0.02, P.glassDark);
    b.box(b.w * 0.34, 0.9, -b.hd + 0.01, b.w * 0.2, 0.7, 0.02, P.charcoal);
    b.box(-b.w * 0.12, 0.15, -b.hd + 0.01, b.w * 0.62, 0.15, 0.02, P.black);
    if (!b.interior) return;
    const cols = ["#d9a43c", "#4f8f6e", "#3f7fb0", "#c0463e", "#e4e9e8"];
    [0.55, 0.78, 1.01, 1.24, 1.47].forEach((y, i) => b.box(-b.w * 0.12, y, -b.hd + 0.03, b.w * 0.55, 0.14, 0.02, cols[i % cols.length]));
    b.box(b.w * 0.34, 1.0, -b.hd + 0.03, b.w * 0.12, 0.05, 0.02, P.led);
  };
}

export function atm(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.9, 1.5, b.d * 0.9, P.charcoal);
    b.box(0, 1.5, 0, b.w * 0.9, 0.2, b.d * 0.9, P.blue);
    b.box(0, 1.05, -b.hd + 0.02, b.w * 0.6, 0.3, 0.02, P.screen);
    if (b.interior) { b.tilt(0, 0.9, -b.hd + 0.07, b.w * 0.6, 0.12, 0.03, -0.35, P.steel); b.box(b.w * 0.25, 0.72, -b.hd + 0.03, 0.12, 0.02, 0.02, P.black); }
  };
}

// ---------- office and lab equipment ----------

/** Small instrument on a slim bench-height stand: used when the footprint is a tabletop item. */
function standTop(b: PartBuilder, h: number) {
  if (b.interior) b.cyl(0, 0, 0, Math.min(b.w, b.d) * 0.55, 0.03, P.metalDark);
  b.cyl(0, b.interior ? 0.03 : 0, 0, 0.06, h - (b.interior ? 0.07 : 0.04), P.steel);
  b.box(0, h - 0.04, 0, b.w, 0.04, b.d, P.laminate);
}

export function washingMachine(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 0.85, b.d, P.white);
    b.cylZ(0, 0.4, -b.hd + 0.02, 0.04, Math.min(b.w, 0.6) * 0.65, P.steel);
    b.cylZ(0, 0.4, -b.hd + 0.035, 0.03, Math.min(b.w, 0.6) * 0.5, P.glassDark);
    b.box(0, 0.76, -b.hd + 0.01, b.w - 0.04, 0.08, 0.02, P.offWhite);
    if (b.interior) { b.cyl(b.w * 0.3, 0.8, -b.hd + 0.03, 0.05, 0.03, P.steel); b.box(-b.w * 0.25, 0.78, -b.hd + 0.025, 0.1, 0.03, 0.01, P.screen); b.box(0, 0, 0, b.w * 0.9, 0.03, b.d * 0.9, P.black); }
  };
}

export function printer(): Build {
  return b => {
    standTop(b, 0.72);
    b.box(0, 0.72, 0, b.w * 0.9, 0.2, b.d * 0.85, P.offWhite);
    b.box(0, 0.92, b.d * 0.1, b.w * 0.7, 0.05, b.d * 0.5, P.white);
    if (b.interior) { b.box(0, 0.74, -b.hd + 0.02, b.w * 0.7, 0.03, 0.04, P.black); b.box(b.w * 0.3, 0.88, -b.hd + 0.05, 0.05, 0.02, 0.02, P.ledGreen); }
  };
}

export function multifunctionPrinter(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.95, 0.85, b.d * 0.95, P.offWhite);
    b.box(0, 0.85, 0, b.w, 0.18, b.d, P.white);
    b.box(0, 1.03, b.d * 0.08, b.w * 0.95, 0.05, b.d * 0.8, P.charcoal);
    b.tilt(b.w * 0.2, 1.1, -b.hd + 0.12, b.w * 0.25, 0.015, 0.14, -0.4, P.screen);
    if (!b.interior) return;
    [0.15, 0.4, 0.62].forEach(y => b.box(0, y, -b.hd + 0.01, b.w * 0.85, 0.2, 0.02, P.steel));
    b.box(-b.w * 0.25, 0.9, -b.hd + 0.015, b.w * 0.3, 0.02, 0.02, P.black);
  };
}

export function printer3d(): Build {
  return b => {
    standTop(b, 0.75);
    const H = 0.45;
    b.box(0, 0.75, 0, b.w * 0.92, 0.05, b.d * 0.92, P.charcoal);
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw * 0.88), 0.8, z * (b.hd * 0.88), 0.03, H, 0.03, P.black);
    b.box(0, 0.8 + H, 0, b.w * 0.92, 0.03, b.d * 0.92, P.black);
    if (!b.interior) return;
    b.box(0, 0.86, 0, b.w * 0.55, 0.012, b.d * 0.55, P.steelLight);
    b.box(0, 1.05, 0, b.w * 0.85, 0.025, 0.025, P.steel);
    b.box(0, 1.0, 0, 0.06, 0.07, 0.06, P.orange);
    b.box(0, 0.8 + H - 0.1, -b.hd * 0.88, b.w * 0.8, 0.1, 0.01, P.glassDark);
  };
}

export function industrialPrinter3d(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.96, 0.7, b.d * 0.94, P.charcoal);
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw * 0.93), 0.7, z * (b.hd * 0.9), 0.06, 1.2, 0.06, P.steel);
    b.box(0, 1.9, 0, b.w * 0.98, 0.06, b.d * 0.95, P.charcoal);
    b.box(0, 0.76, -b.hd * 0.9, b.w * 0.9, 1.1, 0.02, P.glassDark);
    if (!b.interior) return;
    b.box(0, 0.85, 0, b.w * 0.6, 0.03, b.d * 0.6, P.steelLight);
    b.box(0, 1.4, 0, b.w * 0.85, 0.04, 0.04, P.steel);
    b.box(b.w * 0.3, 0.4, -b.hd + 0.02, 0.28, 0.2, 0.02, P.screen);
    b.box(-b.w * 0.2, 1.0, 0, 0.12, 0.2, 0.1, P.orange);
  };
}

export function oscilloscopeStation(): Build {
  return b => {
    b.box(0, 0.72, 0, b.w, 0.04, b.d, P.laminate);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.04), 0, 0, 0.05, 0.72, b.d * 0.9, P.metalDark);
    const sw = Math.min(0.42, b.w * 0.45), sd = Math.min(0.4, b.d * 0.7);
    b.box(-b.w * 0.12, 0.76, 0, sw, 0.22, sd, P.offWhite);
    b.box(-b.w * 0.12, 0.8, -sd / 2 + 0.01, sw * 0.6, 0.13, 0.02, P.screen);
    if (!b.interior) return;
    [-1, 1].forEach(s => { b.cyl(-b.w * 0.12 + s * sw * 0.38, 0.8, -sd / 2 + 0.02, 0.03, 0.03, P.black); });
    b.box(-b.w * 0.12, 0.74, -sd / 2 + 0.01, sw * 0.9, 0.025, 0.02, P.black);
    b.box(b.w * 0.28, 0.76, 0, 0.22, 0.12, 0.24, P.steelLight);
    b.box(b.w * 0.28, 0.82, -0.12, 0.2, 0.02, 0.01, P.led);
    b.box(0, 0.76, -b.hd + 0.1, 0.4, 0.02, 0.14, P.black);
  };
}

export function microscope(): Build {
  return b => {
    standTop(b, 0.78);
    const s = Math.min(b.w, b.d);
    b.box(0, 0.78, 0, s * 0.8, 0.04, s * 0.8, P.charcoal);
    b.box(0, 0.82, b.d * 0.22, 0.07, 0.34, 0.08, P.white);
    b.box(0, 0.98, -b.d * 0.05, s * 0.5, 0.03, s * 0.5, P.steel);
    b.tilt(0, 1.2, b.d * 0.1, 0.06, 0.26, 0.06, -0.45, P.white);
    if (!b.interior) return;
    b.cyl(0, 1.08, -b.d * 0.08, 0.05, 0.1, P.steel);
    b.cyl(-s * 0.1, 1.04, -b.d * 0.05, 0.025, 0.07, P.black);
    b.cyl(s * 0.1, 1.04, -b.d * 0.05, 0.025, 0.07, P.black);
    b.box(0, 0.82, -b.d * 0.15, s * 0.3, 0.1, 0.12, P.charcoal);
  };
}

export function fumeHood(): Build {
  return b => {
    const t = 0.05;
    b.box(0, 0, 0, b.w, 0.82, b.d, P.offWhite);
    b.box(0, 0.82, 0, b.w, 0.04, b.d, P.black);
    for (const x of [-1, 1]) b.box(x * (b.hw - t / 2), 0.86, 0, t, 1.52, b.d, P.steelLight);
    b.box(0, 0.86, b.hd - 0.015, b.w, 1.52, 0.03, P.steelLight);
    b.box(0, 2.0, 0, b.w, 0.38, b.d, P.steelLight);
    b.box(0, 1.55, -b.hd + 0.02, b.w - 2 * t, 0.7, 0.012, P.glass);
    if (!b.interior) { b.cyl(0, 2.38, b.d * 0.15, Math.min(0.3, b.w * 0.25), 0.25, P.metal); return; }
    b.box(0, 1.2, -b.hd + 0.02, b.w - 2 * t, 0.06, 0.04, P.steel);
    b.box(0, 1.9, -b.hd + 0.02, b.w - 2 * t, 0.12, 0.012, P.glassDark);
    b.cyl(0, 2.38, b.d * 0.15, Math.min(0.3, b.w * 0.25), 0.25, P.metal);
    b.box(b.w * 0.3, 0.9, -b.hd + 0.12, 0.2, 0.02, 0.1, P.led);
    spread(3, b.w * 0.6).forEach(x => b.cyl(x, 0.9, -b.hd * 0.4, 0.04, 0.12, P.glass));
  };
}

export function solderingStation(): Build {
  return b => {
    b.box(0, 0.8, 0, b.w, 0.04, b.d, P.black);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.04), 0, 0, 0.05, 0.8, b.d * 0.9, P.metalDark);
    b.box(-b.w * 0.3, 0.84, 0, 0.2, 0.1, 0.18, P.charcoal);
    b.box(-b.w * 0.3, 0.9, -0.1, 0.1, 0.02, 0.01, P.led);
    b.cyl(-b.w * 0.15, 0.84, 0.05, 0.06, 0.07, P.steel);
    if (!b.interior) { b.cylZ(b.w * 0.25, 1.05, b.hd * 0.2, b.d * 0.6, 0.05, P.metal); return; }
    b.cyl(b.w * 0.3, 0.84, b.hd - 0.1, 0.04, 0.4, P.metal);
    b.cylZ(b.w * 0.3, 1.2, b.hd * 0.25, b.d * 0.6, 0.06, P.metal);
    b.box(b.w * 0.1, 0.84, -0.05, 0.2, 0.015, 0.2, P.steelLight);
  };
}

// ---------- safety and wall equipment ----------

export function fireExtinguisher(): Build {
  return b => {
    const dm = Math.min(0.2, Math.min(b.w, b.d) * 0.8);
    b.cyl(0, 0, 0, dm, 0.45, P.red);
    b.cyl(0, 0.45, 0, dm * 0.4, 0.05, P.metalDark);
    b.box(0, 0.5, 0, dm * 0.8, 0.04, 0.03, P.black);
    if (b.interior) {
      b.box(0, 0.53, -0.015, 0.03, 0.03, dm * 0.5, P.black);
      b.box(0, 0.3, -dm / 2 + 0.005, dm * 0.9, 0.08, 0.01, P.white);
    }
  };
}

export function defibrillator(): Build {
  return b => {
    b.box(0, 1.0, b.hd - 0.02, b.w, 0.55, 0.03, P.white);
    b.box(0, 1.1, 0, b.w * 0.9, 0.3, b.d * 0.7, P.ledGreen);
    if (!b.interior) return;
    b.box(0, 1.45, b.hd - 0.04, b.w * 0.8, 0.2, 0.02, P.green);
    b.box(0, 1.45, b.hd - 0.055, b.w * 0.45, 0.05, 0.01, P.white);
    b.box(0, 1.45, b.hd - 0.055, 0.05, 0.14, 0.01, P.white);
    b.box(0, 1.2, -b.hd * 0.5, b.w * 0.5, 0.02, 0.01, P.white);
  };
}

export function eyewashStation(): Build {
  return b => {
    b.cyl(0, 0, 0, Math.min(b.w, b.d) * 0.7, 0.04, P.metalDark);
    b.cyl(0, 0.04, 0, 0.07, 0.96, P.green);
    b.cyl(0, 1.0, 0, Math.min(b.w, b.d) * 0.9, 0.1, P.ledGreen);
    if (!b.interior) return;
    for (const x of [-1, 1]) b.sph(x * 0.07, 1.14, 0, 0.05, P.white);
    b.box(0, 1.5, b.hd - 0.02, b.w * 0.6, 0.25, 0.02, P.green);
    b.box(0, 1.55, b.hd - 0.035, b.w * 0.3, 0.12, 0.01, P.white);
  };
}

export function handDryer(): Build {
  return b => {
    b.box(0, 1.0, b.hd - 0.075, b.w, 0.3, 0.15, P.steelLight);
    b.cyl(0, 0.9, b.hd - 0.075, Math.min(0.1, b.w * 0.6), 0.1, P.metal);
    if (b.interior) b.box(0, 1.15, -b.hd * 0.1, b.w * 0.5, 0.02, 0.02, P.led);
  };
}

export function electricalPanel(): Build {
  return b => {
    const cols = clamp(Math.round(b.w / 0.5), 1, 4);
    b.box(0, 0.4, 0, b.w, 1.5, b.d, P.concrete);
    spread(cols, b.w).forEach(x => b.box(x, 0.43, -b.hd + 0.01, b.w / cols - 0.03, 1.44, 0.02, P.metal));
    b.box(0, 1.6, -b.hd + 0.025, b.w * 0.8, 0.1, 0.01, P.hazard);
    if (b.interior) spread(cols, b.w).forEach(x => b.box(x + b.w / cols * 0.35, 1.1, -b.hd + 0.03, 0.03, 0.12, 0.02, P.black));
  };
}

export function upsUnit(): Build {
  return b => {
    b.box(0, 0.04, 0, b.w, 1.16, b.d, P.charcoal);
    b.box(0, 0, 0, b.w * 0.9, 0.04, b.d * 0.9, P.black);
    b.box(0, 0.9, -b.hd + 0.01, b.w * 0.5, 0.14, 0.02, P.screen);
    if (!b.interior) return;
    for (let i = 0; i < 4; i++) b.box(0, 0.25 + i * 0.1, -b.hd + 0.01, b.w * 0.7, 0.03, 0.02, P.black);
    b.box(b.w * 0.3, 0.97, -b.hd + 0.02, 0.03, 0.03, 0.01, P.ledGreen);
  };
}

export function serverRack(): Build {
  return b => {
    b.box(0, 0.05, 0, b.w, 1.95, b.d, P.black);
    b.box(0, 0.06, -b.hd + 0.01, b.w - 0.08, 1.9, 0.02, P.charcoal);
    if (!b.interior) { b.box(0, 0.4, -b.hd + 0.02, b.w * 0.7, 0.8, 0.01, P.glassDark); return; }
    for (let i = 0; i < 9; i++) b.box(0, 0.2 + i * 0.19, -b.hd + 0.025, b.w - 0.14, 0.04, 0.012, i % 3 ? P.metalDark : P.steel);
    for (let i = 0; i < 9; i += 2) b.box(b.w * 0.3, 0.23 + i * 0.19, -b.hd + 0.03, 0.02, 0.02, 0.01, P.ledGreen);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.03), 0, 0, 0.05, 0.05, b.d, P.metalDark);
  };
}

// ---------- display and projection ----------

export function projector(): Build {
  return b => {
    b.cyl(0, 2.35, 0, 0.04, 0.3, P.metal);
    b.box(0, 2.15, 0, b.w * 0.95, 0.2, b.d * 0.9, P.offWhite);
    if (!b.interior) return;
    b.box(0, 2.62, 0, 0.14, 0.03, 0.14, P.metal);
    b.cyl(0, 2.2, -b.hd + 0.03, Math.min(0.1, b.d * 0.4), 0.06, P.black);
    b.box(b.w * 0.3, 2.3, 0, 0.04, 0.02, b.d * 0.5, P.black);
  };
}

export function projectorScreen(): Build {
  return b => {
    b.box(0, 2.28, 0, b.w, 0.1, b.d, P.metal);
    b.box(0, 1.0, b.hd - 0.01, b.w * 0.97, 1.28, 0.012, P.white);
    b.box(0, 0.94, b.hd - 0.015, b.w * 0.97, 0.06, 0.03, P.charcoal);
    if (b.interior) for (const x of [-1, 1]) b.box(x * (b.hw * 0.98), 0.95, b.hd - 0.01, 0.01, 1.34, 0.012, P.black);
  };
}

export function displayScreen(): Build {
  return b => {
    b.box(0, 0, 0, Math.min(0.6, b.w * 0.7), 0.04, b.d, P.metalDark);
    b.box(0, 0.04, b.hd - 0.04, 0.1, 1.0, 0.05, P.metalDark);
    b.box(0, 0.55, b.hd - 0.07, b.w, 0.95, 0.06, P.black);
    b.box(0, 0.6, b.hd - 0.1, b.w - 0.08, 0.85, 0.01, P.glassDark);
    if (b.interior) b.box(0, 0.68, b.hd - 0.11, b.w * 0.6, 0.3, 0.005, P.screen);
  };
}

export function whiteboard(): Build {
  return b => {
    b.box(0, 0.95, b.hd - 0.02, b.w, 1.2, 0.04, P.steelLight);
    b.box(0, 0.99, b.hd - 0.045, b.w - 0.08, 1.12, 0.012, P.white);
    b.box(0, 0.9, b.hd - 0.06, b.w * 0.9, 0.05, 0.05, P.steel);
    if (b.interior) spread(3, b.w * 0.4).forEach((x, i) => b.box(x, 0.955, b.hd - 0.08, 0.1, 0.02, 0.025, [P.black, P.red, P.blue][i]));
  };
}

// ---------- sanitary fixtures ----------

export function toilet(): Build {
  return b => {
    const bw = Math.min(b.w, 0.4) * 0.9, bd = Math.min(b.d * 0.62, 0.45);
    b.box(0, 0, b.hd - 0.1, bw * 0.75, 0.4, 0.2, P.white);
    b.cyl(0, 0, -b.hd + bd / 2 + 0.02, bw, 0.4, P.white, bd);
    b.cyl(0, 0.4, -b.hd + bd / 2 + 0.02, bw, 0.03, P.pillow, bd);
    if (!b.interior) return;
    b.box(0, 0.4, b.hd - 0.06, bw * 0.8, 0.4, 0.12, P.white);
    b.cyl(0, 0.43, -b.hd + bd / 2 + 0.02, bw * 0.75, 0.01, "#bfd3da", bd * 0.75);
    b.cyl(bw * 0.25, 0.81, b.hd - 0.06, 0.04, 0.02, P.steel);
  };
}

export function sink(): Build {
  return b => {
    const n = clamp(Math.round(b.w / 0.7), 1, 5), cw = Math.min(0.45, b.w / n * 0.8), bd = Math.min(0.4, b.d * 0.75);
    b.box(0, 0.78, 0, b.w, 0.06, b.d, P.white);
    b.box(0, 0.1, b.hd - 0.04, b.w * 0.5, 0.68, 0.06, P.offWhite);
    spread(n, b.w).forEach(x => { b.box(x, 0.84, -b.hd * 0.1, cw, 0.03, bd, P.glassDark); });
    if (!b.interior) return;
    spread(n, b.w).forEach(x => { b.cyl(x, 0.84, b.hd - 0.08, 0.03, 0.15, P.steelLight); b.box(x, 0.97, b.hd - 0.14, 0.025, 0.025, 0.1, P.steelLight); });
    b.cyl(0, 0.1, b.hd - 0.12, 0.05, 0.65, P.offWhite);
  };
}

export function bathtub(): Build {
  return b => {
    b.box(0, 0.05, 0, b.w, 0.5, b.d, P.white);
    b.box(0, 0.5, -b.d * 0.03, b.w - 0.1, 0.06, b.d - 0.1, "#c6dae0");
    b.box(0, 0, 0, b.w * 0.9, 0.05, b.d * 0.85, P.black);
    if (!b.interior) return;
    b.box(0, 0.55, 0, b.w - 0.16, 0.02, b.d - 0.16, "#8db4c2");
    b.cyl(-b.hw + 0.08, 0.56, 0, 0.03, 0.18, P.steelLight);
    b.cylX(-b.hw + 0.08, 0.76, 0, Math.min(0.2, b.d - 0.05), 0.025, P.steelLight);
  };
}

export function shower(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 0.06, b.d, P.white);
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - 0.02), 0.06, z * (b.hd - 0.02), 0.03, 1.94, 0.03, P.steel);
    b.box(0, 2.0, 0, b.w, 0.03, 0.03, P.steel);
    if (!b.interior) { b.box(0, 1.0, b.hd - 0.01, b.w, 1.5, 0.02, P.glass); return; }
    b.box(0, 1.0, b.hd - 0.01, b.w, 1.5, 0.02, P.glass);
    b.cyl(0, 1.2, b.hd - 0.04, 0.025, 0.9, P.steelLight);
    b.cyl(0, 1.95, b.hd - 0.1, 0.18, 0.03, P.steelLight);
    b.box(-b.hw + 0.02, 0.06, 0, 0.02, 1.9, b.d - 0.06, P.glass);
  };
}

// ---------- machines ----------

export function cncLathe(): Build {
  return b => {
    b.box(0, 0, 0.08 * b.d, b.w * 0.94, 1.1, b.d * 0.74, P.steel);
    b.box(0, 1.1, 0.12 * b.d, b.w * 0.9, 0.5, b.d * 0.62, P.offWhite);
    b.box(-b.w * 0.05, 1.12, 0.12 * b.d - b.d * 0.31 + 0.011, b.w * 0.55, 0.42, 0.02, P.glassDark);
    b.box(b.w * 0.38, 0.55, -b.hd + 0.12, b.w * 0.16, 0.45, 0.2, P.charcoal);
    b.box(b.w * 0.38, 0.75, -b.hd + 0.025, b.w * 0.12, 0.16, 0.02, P.screen);
    if (!b.interior) return;
    b.cylX(-b.w * 0.32, 1.35, -b.d * 0.12, b.w * 0.12, 0.25, P.metal);
    b.cylX(b.w * 0.3, 1.35, -b.d * 0.12, b.w * 0.15, 0.12, P.metal);
    b.box(0, 0, -b.hd * 0.86, b.w * 0.9, 0.12, b.d * 0.1, P.metalDark);
    b.cylX(0, 0.7, -b.hd + 0.12, b.w * 0.5, 0.03, P.steelLight);
  };
}

export function cncMill(): Build {
  return b => {
    b.box(0, 0, b.d * 0.05, b.w * 0.94, 1.0, b.d * 0.82, P.steel);
    b.box(0, 1.0, b.d * 0.1, b.w * 0.88, 1.0, b.d * 0.7, P.offWhite);
    b.box(0, 1.1, -b.d * 0.25 + 0.01 + b.d * 0.1, b.w * 0.55, 0.7, 0.02, P.glassDark);
    b.box(b.w * 0.37, 1.0, -b.hd + 0.15, b.w * 0.16, 0.4, 0.2, P.charcoal);
    if (!b.interior) return;
    b.box(b.w * 0.37, 1.2, -b.hd + 0.04, b.w * 0.12, 0.14, 0.02, P.screen);
    b.cyl(0, 2.0, b.d * 0.1, Math.min(0.3, b.w * 0.2), 0.25, P.metal);
    b.box(0, 0.5, -b.hd * 0.85, b.w * 0.8, 0.04, 0.02, P.metalDark);
  };
}

export function millingMachine(): Build {
  return b => {
    b.box(0, 0, 0.1 * b.d, b.w * 0.55, 0.3, b.d * 0.7, P.metalDark);
    b.box(0, 0.3, b.d * 0.22, b.w * 0.3, 1.6, b.d * 0.35, P.blue);
    b.box(0, 1.5, 0, b.w * 0.5, 0.4, b.d * 0.5, P.blue);
    b.box(0, 0.9, -b.d * 0.05, b.w * 0.85, 0.1, b.d * 0.45, P.metal);
    b.cyl(0, 1.1, -b.d * 0.05, 0.08, 0.4, P.steel);
    if (!b.interior) return;
    b.box(0, 0.78, -b.d * 0.05, b.w * 0.3, 0.12, b.d * 0.35, P.blue);
    b.cyl(b.w * 0.35, 0.75, -b.hd + 0.1, 0.06, 0.2, P.steel);
    b.box(-b.w * 0.3, 1.9, b.d * 0.22, b.w * 0.2, 0.3, b.d * 0.3, P.charcoal);
  };
}

export function drillPress(): Build {
  return b => {
    b.box(0, 0, b.hd * 0.2, b.w * 0.8, 0.06, b.d * 0.55, P.metalDark);
    b.cyl(0, 0.06, b.hd * 0.4, 0.09, 1.55, P.steel);
    b.box(0, 1.5, b.hd * 0.1, b.w * 0.45, 0.25, b.d * 0.5, P.green);
    b.box(0, 0.8, 0, b.w * 0.55, 0.05, b.d * 0.5, P.metal);
    b.cyl(0, 1.0, -b.hd * 0.1, 0.03, 0.5, P.steelLight);
    if (!b.interior) return;
    b.cyl(0, 1.75, b.hd * 0.1, b.w * 0.35, 0.12, P.charcoal);
    b.cylX(b.w * 0.25, 1.4, -b.hd * 0.2, b.w * 0.3, 0.025, P.black);
    b.sph(b.w * 0.4, 1.4, -b.hd * 0.2, 0.06, P.black);
  };
}

export function pressBrake(): Build {
  return b => {
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.2), 0, 0, 0.4, 2.0, b.d * 0.8, P.blue);
    b.box(0, 0.9, -b.d * 0.05, b.w - 0.8, 0.25, b.d * 0.35, P.metal);
    b.box(0, 1.5, -b.d * 0.05, b.w - 0.8, 0.4, b.d * 0.4, P.steel);
    b.box(0, 0, -b.hd + 0.2, 0.5, 0.1, 0.3, P.black);
    if (!b.interior) return;
    b.box(b.hw - 0.2, 1.0, -b.d * 0.4 - 0.01, 0.3, 0.4, 0.2, P.charcoal);
    b.box(b.hw - 0.2, 1.1, -b.hd + 0.02, 0.2, 0.15, 0.02, P.screen);
    b.cylX(0, 1.3, -b.d * 0.3, b.w - 0.9, 0.05, P.metalDark);
  };
}

export function laserCutter(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 0.85, b.d, P.charcoal);
    b.box(0, 0.85, 0, b.w, 0.35, b.d, P.offWhite);
    b.box(0, 1.0, -b.hd + 0.012, b.w * 0.7, 0.18, 0.02, P.orange);
    b.box(b.w * 0.38, 0.5, -b.hd + 0.012, b.w * 0.16, 0.3, 0.02, P.black);
    if (!b.interior) return;
    b.box(0, 1.2, b.hd * 0.6, b.w * 0.25, 0.08, b.d * 0.25, P.metal);
    b.box(b.w * 0.38, 0.62, -b.hd + 0.025, b.w * 0.1, 0.07, 0.01, P.screen);
  };
}

export function waterjetCutter(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.95, 0.7, b.d * 0.9, P.blue);
    b.box(0, 0.7, 0, b.w * 0.9, 0.12, b.d * 0.84, P.metal);
    for (const x of [-1, 1]) b.box(x * (b.hw * 0.9), 0.82, 0, 0.12, 0.6, b.d * 0.9, P.steel);
    b.box(0, 1.2, 0, b.w * 0.9, 0.2, 0.3, P.steel);
    b.cyl(0, 0.82, 0, 0.12, 0.4, P.black);
    if (!b.interior) return;
    b.box(b.w * 0.38, 0, -b.hd + 0.15, 0.5, 1.1, 0.3, P.charcoal);
    b.box(b.w * 0.38, 0.8, -b.hd + 0.31, 0.3, 0.2, 0.01, P.screen);
    b.cyl(-b.w * 0.3, 1.0, 0, 0.1, 0.2, P.steelLight);
  };
}

export function injectionMouldingMachine(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 0.9, b.d * 0.8, P.offWhite);
    b.box(-b.w * 0.3, 0.9, 0, b.w * 0.3, 1.1, b.d * 0.7, P.blue);
    b.cylX(b.w * 0.15, 1.15, 0, b.w * 0.5, 0.3, P.metal);
    b.cyl(b.w * 0.3, 1.3, 0, 0.35, 0.5, P.steel);
    if (!b.interior) return;
    b.box(-b.w * 0.05, 0.9, -b.hd + 0.2, b.w * 0.2, 1.0, 0.02, P.glassDark);
    b.box(b.w * 0.42, 0.9, -b.hd + 0.2, 0.4, 0.5, 0.3, P.charcoal);
    b.box(b.w * 0.42, 1.2, -b.hd + 0.06, 0.25, 0.15, 0.02, P.screen);
    b.cylX(b.w * 0.45, 1.15, 0, b.w * 0.08, 0.25, P.orange);
  };
}

export function robotCell(): Build {
  return b => {
    const post = 0.08;
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * (b.hw - post / 2), 0, z * (b.hd - post / 2), post, 2.0, post, P.yellow);
    if (b.interior) b.box(0, 0, 0, b.w * 0.2, 0.3, b.d * 0.2, P.charcoal);
    b.cyl(0, b.interior ? 0.3 : 0, 0, 0.28, 0.35, P.orange);
    b.tilt(0, 1.0, 0, 0.14, 0.9, 0.14, 0.3, P.orange);
    b.tilt(0, 1.55, -0.2, 0.11, 0.75, 0.11, -0.9, P.orange);
    if (!b.interior) { b.box(0, 1.9, -b.hd + post / 2, b.w - 2 * post, 0.06, post, P.yellow); return; }
    for (const z of [-1, 1]) { b.box(0, 1.9, z * (b.hd - post / 2), b.w - 2 * post, 0.06, post, P.yellow); b.box(0, 1.0, z * (b.hd - post / 2), b.w - 2 * post, 0.04, 0.03, P.yellow); }
    for (const x of [-1, 1]) { b.box(x * (b.hw - post / 2), 1.9, 0, post, 0.06, b.d - 2 * post, P.yellow); b.box(x * (b.hw - post / 2), 1.0, 0, 0.03, 0.04, b.d - 2 * post, P.yellow); }
    b.sph(0, 1.2, -0.15, 0.14, P.charcoal);
    b.box(0, 0, -b.hd * 0.7, b.w * 0.25, 0.8, b.d * 0.15, P.charcoal);
  };
}

export function conveyor(): Build {
  return b => {
    const belt = Math.min(b.d * 0.85, 0.9);
    b.box(0, 0.7, 0, b.w, 0.1, belt, P.charcoal);
    for (const z of [-1, 1]) b.box(0, 0.8, z * (belt / 2 - 0.02), b.w, 0.06, 0.04, P.steel);
    const legs = b.interior ? clamp(Math.round(b.w / 1.5) + 1, 2, 6) : 2;
    spread(legs, b.w - 0.2).forEach(x => { b.box(x, 0, -belt / 2 + 0.05, 0.05, 0.7, 0.05, P.metalDark); b.box(x, 0, belt / 2 - 0.05, 0.05, 0.7, 0.05, P.metalDark); });
    if (!b.interior) { b.box(0, 0.5, 0, b.w * 0.97, 0.05, belt * 0.9, P.blue); return; }
    spread(clamp(Math.round(b.w / 0.5), 2, 12), b.w - 0.3).forEach(x => b.cylZ(x, 0.76, 0, belt, 0.06, P.metal));
    b.box(0, 0.65, 0, b.w, 0.05, belt, P.blue);
  };
}

export function forklift(): Build {
  return b => {
    // Long axis along X; forks point toward -X.
    const L = b.w, W = b.d;
    b.box(L * 0.12, 0.3, 0, L * 0.6, 0.55, W * 0.9, P.yellow);
    b.box(L * 0.3, 0.85, 0, L * 0.25, 0.2, W * 0.8, P.charcoal);
    b.box(-L * 0.25, 0.1, 0, 0.1, 1.9, W * 0.7, P.metalDark);
    for (const z of [-1, 1]) b.box(-L * 0.4, 0.05, z * W * 0.3, L * 0.3, 0.05, 0.12, P.metal);
    if (!b.interior) { b.box(L * 0.1, 1.0, 0, L * 0.4, 0.05, W * 0.85, P.charcoal); return; }
    for (const z of [-1, 1]) { b.box(L * 0.2 + L * 0.1, 0.95, z * (W * 0.4), 0.05, 1.05, 0.05, P.charcoal); b.box(L * 0.0, 0.95, z * (W * 0.4), 0.05, 1.05, 0.05, P.charcoal); }
    b.box(L * 0.1, 2.0, 0, L * 0.4, 0.05, W * 0.85, P.charcoal);
    for (const x of [-0.12, 0.38]) for (const z of [-1, 1]) b.cylZ(L * x, 0.2, z * (W * 0.42), 0.16, 0.4, P.black);
    b.box(L * 0.5 - 0.1, 0.55, 0, 0.2, 0.5, W * 0.7, P.charcoal);
    b.box(L * 0.3, 1.05, 0, 0.4, 0.25, 0.4, P.black);
  };
}

export function palletJack(): Build {
  return b => {
    for (const z of [-1, 1]) b.box(-b.w * 0.2, 0.04, z * b.d * 0.3, b.w * 0.6, 0.09, 0.18, P.red);
    b.box(b.w * 0.38, 0.1, 0, b.w * 0.2, 0.2, b.d * 0.5, P.red);
    b.tilt(b.w * 0.4, 0.55, 0, 0.04, 0.9, 0.04, 0, P.black);
    if (!b.interior) { b.box(b.w * 0.4, 1.0, 0, 0.04, 0.04, b.d * 0.4, P.black); return; }
    b.cylZ(b.w * 0.4, 1.02, 0, b.d * 0.5, 0.03, P.black);
    for (const z of [-1, 1]) b.cylZ(-b.w * 0.45, 0.05, z * b.d * 0.3, 0.1, 0.08, P.black);
  };
}

export function forkliftChargingStation(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.5, 1.4, b.d * 0.5, P.charcoal);
    b.box(0, 1.1, -b.d * 0.25 + 0.01, b.w * 0.4, 0.2, 0.02, P.screen);
    b.box(-b.w * 0.3, 0, b.d * 0.2, b.w * 0.3, 0.1, b.d * 0.3, P.black);
    if (!b.interior) return;
    b.cylX(b.w * 0.2, 0.25, -b.d * 0.15, b.w * 0.3, 0.1, P.yellow);
    b.box(b.w * 0.25, 0.9, -b.d * 0.25 + 0.01, 0.06, 0.06, 0.02, P.ledGreen);
    b.box(0, 1.4, 0, b.w * 0.5, 0.12, b.d * 0.5, P.hazard);
  };
}

export function compressor(): Build {
  return b => {
    for (const x of [-1, 1]) b.box(x * (b.hw * 0.7), 0, 0, 0.1, 0.2, b.d * 0.7, P.metalDark);
    b.cylX(0, 0.55, 0, b.w * 0.9, Math.min(b.d * 0.7, 0.55), P.blue);
    b.box(0, 0.85, 0, b.w * 0.35, 0.35, b.d * 0.4, P.charcoal);
    if (!b.interior) return;
    b.cyl(b.w * 0.3, 0.85, 0, 0.1, 0.1, P.steel);
    b.cyl(-b.w * 0.3, 0.75, -b.d * 0.2, 0.08, 0.03, P.steelLight);
    b.sph(b.w * 0.3, 0.95, 0, 0.1, P.steelLight);
  };
}

export function boiler(): Build {
  return b => {
    const dm = Math.min(b.w, b.d) * 0.85;
    b.cyl(0, 0, 0, dm, 0.1, P.metalDark);
    b.cyl(0, 0.1, 0, dm, 1.5, P.steelLight);
    b.sph(0, 1.62, 0, dm, P.steelLight, 0.2);
    b.cyl(dm * 0.2, 1.65, 0, 0.12, 0.4, P.metalDark);
    if (!b.interior) return;
    b.box(0, 0.7, -dm / 2 + 0.02, dm * 0.4, 0.3, 0.04, P.charcoal);
    b.box(0, 0.88, -dm / 2 + 0.005, 0.1, 0.08, 0.02, P.led);
    b.cyl(-dm * 0.3, 0.35, dm * 0.3, 0.05, 0.9, P.orange);
  };
}

export function hvacUnit(): Build {
  return b => {
    b.box(0, 0.1, 0, b.w, 1.4, b.d, P.concrete);
    b.box(0, 0, 0, b.w * 0.95, 0.1, b.d * 0.95, P.metalDark);
    b.cyl(0, 1.5, 0, Math.min(b.w, b.d) * 0.7, 0.08, P.charcoal);
    if (!b.interior) return;
    for (let i = 0; i < 6; i++) b.box(0, 0.35 + i * 0.15, -b.hd + 0.01, b.w * 0.7, 0.04, 0.02, P.charcoal);
    b.box(b.w * 0.35, 0.3, -b.hd + 0.015, 0.3, 0.5, 0.02, P.metal);
  };
}

export function curingOven(): Build {
  return b => {
    b.box(0, 0.1, 0, b.w, 1.5, b.d, P.offWhite);
    b.box(0, 0, 0, b.w * 0.95, 0.1, b.d * 0.9, P.metalDark);
    b.box(0, 0.5, -b.hd + 0.01, b.w * 0.8, 0.7, 0.02, P.steel);
    b.cyl(b.w * 0.25, 1.6, b.d * 0.2, 0.2, 0.4, P.metal);
    if (!b.interior) return;
    b.cylX(0, 1.1, -b.hd + 0.04, b.w * 0.6, 0.03, P.steelLight);
    b.box(b.w * 0.38, 1.35, -b.hd + 0.015, 0.14, 0.1, 0.02, P.screen);
  };
}

export function powderStation(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.9, 0.5, b.d * 0.7, P.metalDark);
    b.box(0, 0.5, b.hd - 0.03, b.w * 0.95, 1.5, 0.05, P.steelLight);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.03), 0.5, 0, 0.05, 1.5, b.d, P.steelLight);
    b.box(0, 2.0, 0, b.w, 0.05, b.d, P.steelLight);
    if (!b.interior) return;
    b.cyl(-b.w * 0.15, 0.5, 0, Math.min(0.35, b.d * 0.5), 0.35, P.orange);
    b.box(b.w * 0.3, 0.55, -b.hd * 0.3, 0.15, 0.2, 0.12, P.charcoal);
    b.cylX(b.w * 0.15, 0.9, -b.hd * 0.4, 0.5, 0.025, P.black);
  };
}

export function weldingStation(): Build {
  return b => {
    b.box(0, 0.8, 0, b.w * 0.6, 0.06, b.d * 0.5, P.metal);
    for (const x of [-1, 1]) for (const z of [-1, 1]) b.box(x * b.w * 0.27, 0, z * b.d * 0.2, 0.06, 0.8, 0.06, P.metalDark);
    for (const x of [-1, 1]) b.box(x * (b.hw - 0.03), 0, 0, 0.05, 1.8, b.d * 0.9, P.orange);
    b.box(0, 0, b.hd - 0.03, b.w * 0.95, 1.8, 0.05, P.orange);
    if (!b.interior) return;
    b.box(b.w * 0.35, 0.05, -b.d * 0.1, 0.4, 0.7, 0.4, P.charcoal);
    b.cyl(-b.w * 0.25, 0.86, b.hd * 0.5, 0.05, 0.9, P.metal);
    b.cylX(-b.w * 0.15, 1.75, b.hd * 0.5, b.w * 0.25, 0.14, P.metal);
    b.box(0, 0.86, 0, b.w * 0.2, 0.02, b.d * 0.2, P.steelLight);
  };
}

export function coordinateMeasuringMachine(): Build {
  return b => {
    b.box(0, 0, 0, b.w * 0.85, 0.7, b.d * 0.75, P.charcoal);
    b.box(0, 0.7, 0, b.w * 0.8, 0.15, b.d * 0.7, P.concrete);
    for (const x of [-1, 1]) b.box(x * (b.hw * 0.75), 0.85, 0, 0.1, 0.9, 0.1, P.steel);
    b.box(0, 1.75, 0, b.w * 0.8, 0.12, 0.12, P.steel);
    b.cyl(0, 1.2, 0, 0.06, 0.55, P.metal);
    if (!b.interior) return;
    b.sph(0, 1.18, 0, 0.05, P.red);
    b.box(b.w * 0.4, 0.5, -b.hd + 0.15, 0.4, 0.5, 0.3, P.charcoal);
    b.box(b.w * 0.4, 0.8, -b.hd + 0.31, 0.3, 0.2, 0.01, P.screen);
  };
}

export function stairs(): Build {
  return b => {
    // Illustrative flight rising toward +Z (up direction is not recorded in the supplied data).
    const n = clamp(Math.round(b.d / 0.28), 3, 12), riser = 0.17;
    const steps = b.interior ? n : Math.min(n, 4);
    const sd = b.d / steps;
    for (let i = 0; i < steps; i++) b.box(0, 0, -b.hd + (i + 0.5) * sd, b.w, (i + 1) * (b.interior ? riser : riser * n / steps), sd, i % 2 ? P.steelLight : P.offWhite);
    if (b.interior && b.w >= 0.8) for (const x of [-1, 1]) b.box(x * (b.hw - 0.02), 0, 0, 0.04, 0.1 + n * riser * 0.5, b.d, P.metalDark);
  };
}

// ---------- fallback ----------

/** Visibly generic plinth: carries no type identity beyond "something stands here". */
export function genericBlock(): Build {
  return b => {
    b.box(0, 0, 0, b.w, 0.6, b.d, "#8f8aa8");
    b.box(0, 0.6, 0, b.w * 0.6, 0.06, b.d * 0.6, "#b8b4cc");
    if (b.interior) { b.box(0, 0.66, 0, b.w * 0.12, 0.12, b.d * 0.12, "#d7d4e6"); }
  };
}

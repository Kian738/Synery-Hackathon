// Part vocabulary and the metre-based builder every family is authored with.
//
// Local frame: origin at the footprint centre on the floor, +Y up, forward (the operator or sitting side) is -Z.
// Emitted X/Z positions and scales are fractions of the supplied width/depth; Y positions and heights stay
// in illustrative metres. An instanced renderer composes, per part:
//   translate(position.x * width, position.y, position.z * depth) * rotateXYZ(rotation) * scale(scale.x * width, scale.y, scale.z * depth)
// where the unit box has side 1, the unit cylinder has diameter 1, height 1 and its axis along Y, and the unit sphere has diameter 1.

export type Lod = "overview" | "interior";
export type Vec3 = [number, number, number];
export interface AssetPart {
  shape: "box" | "cylinder" | "sphere";
  position: Vec3;
  scale: Vec3;
  color: string;
  rotation?: Vec3;
}
export interface AssetVisual {
  family: string;
  illustrative: true;
  fallback: boolean;
  parts: AssetPart[];
}

export const PALETTE = {
  wood: "#b39a74", woodDark: "#7d6446", laminate: "#c9c1ae", white: "#e4e9e8", offWhite: "#cfd7d6",
  steel: "#aab6ba", steelLight: "#d3dbdc", metal: "#7f8f95", metalDark: "#45545b", black: "#1f2a30", charcoal: "#2f3d44",
  fabric: "#536b7c", fabricWarm: "#8a6a5a", fabricGreen: "#5b7a68", leather: "#4a4038",
  screen: "#2c695e", glass: "#6f9fb0", glassDark: "#26414c", led: "#ffd45c", ledGreen: "#6bd49a",
  red: "#c0463e", orange: "#d98a3d", yellow: "#d9b53c", blue: "#3f7fb0", green: "#4f8f6e", leaf: "#4d8a5c", leafLight: "#6aa36e", soil: "#4a3a2e",
  pot: "#a46c52", concrete: "#8d9799", hazard: "#e0c13a", bed: "#a3b3c4", pillow: "#e3e8ea", blanket: "#6d7f98",
  generic: "#8f8aa8", genericCap: "#b8b4cc",
} as const;

const MIN = 1e-4;
const r4 = (n: number) => Math.round(n * 1e4) / 1e4;

export class PartBuilder {
  readonly parts: AssetPart[] = [];
  readonly hw: number;
  readonly hd: number;
  constructor(readonly w: number, readonly d: number, readonly interior: boolean) {
    this.hw = w / 2;
    this.hd = d / 2;
  }

  /** Box by metre offsets from the footprint centre; y0 is the bottom. The box is clipped to the footprint. */
  box(cx: number, y0: number, cz: number, sx: number, h: number, sz: number, color: string) {
    const x0 = Math.max(cx - sx / 2, -this.hw), x1 = Math.min(cx + sx / 2, this.hw);
    const z0 = Math.max(cz - sz / 2, -this.hd), z1 = Math.min(cz + sz / 2, this.hd);
    if (x1 - x0 < MIN || z1 - z0 < MIN || h < MIN) return this;
    this.parts.push({ shape: "box", position: [r4((x0 + x1) / 2 / this.w), r4(y0 + h / 2), r4((z0 + z1) / 2 / this.d)], scale: [r4((x1 - x0) / this.w), r4(h), r4((z1 - z0) / this.d)], color });
    return this;
  }

  /** Upright cylinder with elliptical section; the diameters shrink to stay inside the footprint. */
  cyl(cx: number, y0: number, cz: number, dx: number, h: number, color: string, dz = dx) {
    const sx = Math.min(dx, 2 * (this.hw - Math.abs(cx))), sz = Math.min(dz, 2 * (this.hd - Math.abs(cz)));
    if (sx < MIN || sz < MIN || h < MIN) return this;
    this.parts.push({ shape: "cylinder", position: [r4(cx / this.w), r4(y0 + h / 2), r4(cz / this.d)], scale: [r4(sx / this.w), r4(h), r4(sz / this.d)], color });
    return this;
  }

  /** Sphere/ellipsoid centred at cy; the horizontal diameters shrink to stay inside the footprint. */
  sph(cx: number, cy: number, cz: number, dx: number, color: string, dy = dx, dz = dx) {
    const sx = Math.min(dx, 2 * (this.hw - Math.abs(cx))), sz = Math.min(dz, 2 * (this.hd - Math.abs(cz)));
    if (sx < MIN || sz < MIN || dy < MIN) return this;
    this.parts.push({ shape: "sphere", position: [r4(cx / this.w), r4(cy), r4(cz / this.d)], scale: [r4(sx / this.w), r4(dy), r4(sz / this.d)], color });
    return this;
  }

  /** Cylinder lying along local X (axis horizontal), centred at (cx, cy, cz). */
  cylX(cx: number, cy: number, cz: number, len: number, diam: number, color: string) {
    const l = Math.min(len, 2 * (this.hw - Math.abs(cx))), dm = Math.min(diam, 2 * (this.hd - Math.abs(cz)), 2 * cy);
    if (l < MIN || dm < MIN) return this;
    this.parts.push({ shape: "cylinder", position: [r4(cx / this.w), r4(cy), r4(cz / this.d)], scale: [r4(dm / this.w), r4(l), r4(dm / this.d)], color, rotation: [0, 0, r4(Math.PI / 2)] });
    return this;
  }

  /** Cylinder lying along local Z, centred at (cx, cy, cz). */
  cylZ(cx: number, cy: number, cz: number, len: number, diam: number, color: string) {
    const l = Math.min(len, 2 * (this.hd - Math.abs(cz))), dm = Math.min(diam, 2 * (this.hw - Math.abs(cx)), 2 * cy);
    if (l < MIN || dm < MIN) return this;
    this.parts.push({ shape: "cylinder", position: [r4(cx / this.w), r4(cy), r4(cz / this.d)], scale: [r4(dm / this.w), r4(l), r4(dm / this.d)], color, rotation: [r4(Math.PI / 2), 0, 0] });
    return this;
  }

  /**
   * Box rotated about X (positive angle leans its +Y end toward +Z). Dimensions are centre-based metres and
   * pre-rotation: sx wide, sy tall, sz thick. The caller keeps the rotated extent inside the footprint.
   */
  tilt(cx: number, cy: number, cz: number, sx: number, sy: number, sz: number, angle: number, color: string) {
    const x = Math.min(sx, 2 * (this.hw - Math.abs(cx)));
    if (x < MIN || sy < MIN || sz < MIN) return this;
    this.parts.push({ shape: "box", position: [r4(cx / this.w), r4(cy), r4(cz / this.d)], scale: [r4(x / this.w), r4(sy), r4(sz / this.d)], color, rotation: [r4(angle), 0, 0] });
    return this;
  }
}

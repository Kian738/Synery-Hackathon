/** One hue per floor, used on the floor rail, the wall outlines in 3D and the plan, so a floor is recognisable in the stack
 *  without a legend. Hues are kept away from the route amber (#ffd45c) and carry no meaning beyond identity. */
const HUES = ["#6ea8ff", "#4fd1c5", "#8fdc7a", "#c9a0ff", "#ff9f7a", "#f070a8", "#7fd0ff", "#b5d65c"];

/** Stable colour for a floor, by its level (ground floor first, basements get their own end of the ramp). */
export function floorColor(level: number): string {
  return HUES[((level % HUES.length) + HUES.length) % HUES.length];
}

import type { GuideStep, Route } from "./types";

/** Floor after floor in one stair or lift is one instruction: "Take the stairs up to Floor 5", not five of them.
 *  The merged step is the last hop (wording, target, arrival floor and point) with the metres added up. */
export function mergeFloorSteps<T extends Route>(route: T): T {
  const steps = route.guide?.steps;
  if (!steps?.length) return route;
  const out: GuideStep[] = [];
  for (const step of steps) {
    const prev = out[out.length - 1];
    if (prev && prev.kind === "floor" && step.kind === "floor" && prev.icon === step.icon) {
      out[out.length - 1] = { ...step, metres: prev.metres + step.metres };
    } else out.push(step);
  }
  return out.length === steps.length ? route : { ...route, guide: { ...route.guide, steps: out } };
}

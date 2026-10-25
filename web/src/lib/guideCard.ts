import type { Presentation } from "./playback";
import type { GuideStep, Route } from "./types";

/** What the Guide me card shows at one moment: the action AHEAD, how many metres until it, and what comes after. Shared by the on-screen card
 *  and the VR panel so both always say the same thing. */
export interface GuideCard { index: number; total: number; arrived: boolean; step: GuideStep | undefined; after: GuideStep | undefined; remaining: number }

export function guideCard(route: Route, model: Presentation, time: number, step: number): GuideCard {
  const steps = route.guide.steps, last = steps.length - 1;
  const safe = Math.max(0, Math.min(Number.isFinite(time) ? time : 0, model.duration));
  const arrived = safe >= model.duration - 0.011;
  const index = Math.min(step + 1, last);
  const t0 = model.chapters[Math.min(step, index)] ?? 0, t1 = model.chapters[index] ?? model.duration;
  const share = t1 > t0 ? Math.max(0, Math.min(1, (t1 - safe) / (t1 - t0))) : 0;
  return { index, total: last, arrived, step: steps[index], after: steps[index + 1], remaining: arrived ? 0 : Math.round((steps[index]?.metres ?? 0) * share) };
}

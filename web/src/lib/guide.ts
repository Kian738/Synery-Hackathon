import type { GuideStep } from "./types";

/** The line read aloud for one step: distance first so the listener can plan, then the action ("In 10 m, take the stairs down to Ground floor."). */
export function spokenStep(step: GuideStep): string {
  if (!step.headline) return step.text;
  const action = `${step.headline} ${step.target ?? ""}`.trim();
  const distance = step.cue && step.cue !== "now" ? `${step.cue.charAt(0).toUpperCase()}${step.cue.slice(1)}, ${action.charAt(0).toLowerCase()}${action.slice(1)}` : action;
  return `${distance.charAt(0).toUpperCase()}${distance.slice(1)}.`;
}

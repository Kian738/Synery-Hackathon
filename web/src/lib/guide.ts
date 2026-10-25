import type { GuideStep } from "./types";

/** The line read aloud for one step: distance first so the listener can plan, then the action ("In 10 m, take the stairs down to Ground floor."). */
export function spokenStep(step: GuideStep): string {
  if (!step.headline) return step.text;
  const ahead = !!step.cue && step.cue !== "now";
  // "In 10 metres, you have arrived Room 2" is not English: say where you will arrive.
  const action = step.kind === "arrive" && step.target ? `${ahead ? "you arrive at" : "You have arrived at"} ${step.target}` : `${step.headline} ${step.target ?? ""}`.trim();
  const distance = step.cue && step.cue !== "now" ? `${step.cue.charAt(0).toUpperCase()}${step.cue.slice(1)}, ${action.charAt(0).toLowerCase()}${action.slice(1)}` : action;
  return `${distance.charAt(0).toUpperCase()}${distance.slice(1)}.`;
}

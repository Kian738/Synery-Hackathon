import { expect, test } from "@playwright/test";
import { smoothTurn } from "../src/lib/turn";

const DEG = Math.PI / 180;

/** Simulates the camera heading chasing a target at a frame rate, with uneven frames like a loaded machine. */
function simulate(targets: (t: number) => number, seconds: number, fps: number, jitter = 0) {
  let heading = 0, velocity = 0, t = 0, seed = 7;
  const trace: { t: number; heading: number; velocity: number }[] = [];
  while (t < seconds) {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    const dt = Math.min(0.05, (1 / fps) * (1 + jitter * ((seed / 4294967296) * 2 - 1)));
    const turned = smoothTurn(targets(t) - heading, velocity, dt);
    heading += turned.step; velocity = turned.velocity; t += dt;
    trace.push({ t, heading, velocity });
  }
  return trace;
}
const peak = (trace: { velocity: number }[]) => Math.max(...trace.map(s => Math.abs(s.velocity))) / DEG;
const windowRate = (trace: { t: number; heading: number }[], window: number) => {
  let worst = 0;
  for (let i = 0; i < trace.length; i++) { const j = trace.findIndex((s, k) => k > i && s.t - trace[i].t >= window); if (j > 0) worst = Math.max(worst, Math.abs(trace[j].heading - trace[i].heading) / (trace[j].t - trace[i].t) / DEG); }
  return worst;
};

test("a 150 degree turn never exceeds the speed limit and starts and ends smoothly, even at 15 fps with uneven frames", () => {
  for (const fps of [60, 25, 15]) {
    const trace = simulate(() => 150 * DEG, 5, fps, 0.5);
    expect(peak(trace)).toBeLessThanOrEqual(70.5);
    expect(windowRate(trace, 0.1)).toBeLessThan(80);            // what the Guide me turn-rate test samples
    expect(Math.abs(trace.at(-1)!.heading - 150 * DEG)).toBeLessThan(0.5 * DEG);  // arrives
    expect(Math.max(...trace.map(s => s.heading)) - 150 * DEG).toBeLessThan(1 * DEG);  // no overshoot
    let accel = 0;                                                // angular acceleration is bounded: velocity ramps, it never jumps
    for (let i = 1; i < trace.length; i++) accel = Math.max(accel, Math.abs(trace[i].velocity - trace[i - 1].velocity) / (trace[i].t - trace[i - 1].t) / DEG);
    expect(accel).toBeLessThan(700);
  }
});

test("a target that flips by 180 degrees mid-turn reverses without a jump", () => {
  const trace = simulate(t => (t < 0.6 ? 150 : -150) * DEG, 6, 25, 0.4);
  expect(peak(trace)).toBeLessThanOrEqual(70.5);
  for (let i = 1; i < trace.length; i++) expect(Math.abs(trace[i].heading - trace[i - 1].heading) / DEG).toBeLessThan(5);  // per-frame step
});

test("a small correction settles within a second and a half without oscillating", () => {
  const trace = simulate(() => 8 * DEG, 3, 60, 0);
  expect(Math.abs(trace.find(s => s.t > 1.5)!.heading - 8 * DEG)).toBeLessThan(0.5 * DEG);
  expect(Math.max(...trace.map(s => s.heading))).toBeLessThanOrEqual(8 * DEG + 1e-9);
});

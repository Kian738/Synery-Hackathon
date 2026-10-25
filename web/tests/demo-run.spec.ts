import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });
test.beforeEach(({}, info) => test.skip(info.project.name === "phone", "desktop analysis view"));

test("Run demo tells the five beat story with spoken sentences, bars, amber capacity labels and an applied fix", async ({ page }, info) => {
  test.setTimeout(240000);
  let widened = 0;
  page.on("response", r => { if (/\/widen$/.test(r.url()) && r.ok()) widened++; });
  // The browser voice records each sentence; the server voice is off here (as without a key), so no credits are spent.
  await page.route("**/api/voice/status", r => r.fulfill({ json: { tts: false, stt: false, provider: "browser" } }));
  await page.route("**/api/voice/tts", r => r.fulfill({ status: 503, body: "off" }));
  await page.addInitScript(() => {
    const spoken: string[] = [], times: number[] = [];
    (window as unknown as { __times: number[] }).__times = times;
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    class Utterance { text: string; lang = ""; rate = 1; voice: unknown = null; onend: (() => void) | null = null; onerror: (() => void) | null = null; constructor(t: string) { this.text = t; } }
    (window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = Utterance;
    let speaking = false;
    const synth = { get speaking() { return speaking; }, pending: false, paused: false, getVoices: () => [], cancel() { speaking = false; },
      speak(u: Utterance) { spoken.push(u.text); times.push(performance.now()); speaking = true; setTimeout(() => { speaking = false; u.onend?.(); }, 300); }, pause() {}, resume() {}, addEventListener() {}, removeEventListener() {} };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  });
  // The story must not depend on ElevenLabs: with cloud TTS off, speak() falls back to the (stubbed) browser voice deterministically.
  await page.route(/\/api\/(voice\/)?tts$/, r => r.fulfill({ status: 503, body: "tts off in test" }));
  const scenario = await (await page.request.get("/api/demo/scenario")).json();
  await page.goto("/?demo=fire");
  const clicked = await page.evaluate(() => performance.now());
  const headline = page.locator(".scenario-headline");
  await expect(headline).toHaveText(/Everyone is out in \d+ s/, { timeout: 90000 });
  const before = Number((await headline.innerText()).match(/(\d+) s/)![1]);
  const bars = page.locator(".k-bar");
  await expect(bars).toHaveCount(scenario.ccrp_s ? 3 : 2);
  const seconds = await bars.evaluateAll(els => els.map(e => Number(e.getAttribute("data-seconds"))));
  expect(seconds[0]).toBe(before);
  await expect(page.getByText("Planned together (exact)")).toBeVisible();
  await expect(page.getByText("Prepared scenario. Exact flow over time, every number re-solved.")).toBeVisible();
  await expect(page.getByText(/people per second/).first()).toBeVisible({ timeout: 90000 });
  await expect.poll(async () => (await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).some(s => s.startsWith("Solved again")), { timeout: 60000 }).toBe(true);
  expect(widened).toBe(1);
  const said = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
  let at = -1;
  for (const start of ["Fire in", "fastest way out", "minimum cut", "Firefighters", "Widening this one saves", "Solved again"]) {
    const i = said.findIndex((s, k) => k > at && s.includes(start));
    expect(i, `sentence containing "${start}" in order`).toBeGreaterThan(at);
    at = i;
  }
  const times = await page.evaluate(() => (window as unknown as { __times: number[] }).__times);
  expect(times[said.findIndex(s => s.startsWith("Solved again"))] - clicked).toBeLessThan(50000);
  expect(times[0] - clicked).toBeLessThan(2500);
  expect(said.every(s => s.split(/\s+/).length <= 14)).toBe(true);
  expect(said.find(s => s.includes("fastest way out"))).toContain(`${before} seconds`);
  const after = Number((await headline.innerText()).match(/(\d+) s/)![1]);
  expect(after).toBeLessThan(before);
  expect(said.find(s => s.startsWith("Solved again"))).toContain(`${after} seconds`);
  await page.screenshot({ path: `test-results/demo-run-${info.project.name}.png` });
});

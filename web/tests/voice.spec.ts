import { test, expect } from "@playwright/test";

const URL = process.env.FLOORWISE_URL ?? "http://127.0.0.1:8000";

test("read aloud uses the server voice when configured and falls back to the browser voice when not", async ({ page }) => {
  const asked: string[] = [];
  await page.route("**/api/voice/status", r => r.fulfill({ json: { tts: true, stt: true, provider: "elevenlabs" } }));
  await page.route("**/api/voice/tts", r => { asked.push(r.request().postData() ?? ""); r.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from([0xff, 0xf3, 0x40]) }); });
  await page.addInitScript(() => {
    (window as any).__spoken = [];
    window.speechSynthesis.speak = (u: any) => (window as any).__spoken.push(u.text);
  });
  await page.goto(`${URL}/?building=swiss-1785`);
  await page.getByRole("button", { name: "Read aloud" }).first().click();
  await page.getByRole("button", { name: "Toilets" }).click();
  await expect.poll(() => asked.length, { timeout: 15000 }).toBeGreaterThan(0);
  expect(asked[0]).toContain('"text"');
});

test("a failing server voice drops to the browser voice", async ({ page }) => {
  await page.route("**/api/voice/status", r => r.fulfill({ json: { tts: true, stt: true, provider: "elevenlabs" } }));
  await page.route("**/api/voice/tts", r => r.fulfill({ status: 429, body: "budget" }));
  await page.addInitScript(() => {
    (window as any).__spoken = [];
    window.speechSynthesis.speak = (u: any) => (window as any).__spoken.push(u.text);
  });
  await page.goto(`${URL}/?building=swiss-1785`);
  await page.getByRole("button", { name: "Read aloud" }).first().click();
  await page.getByRole("button", { name: "Toilets" }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__spoken.length), { timeout: 15000 }).toBeGreaterThan(0);
});

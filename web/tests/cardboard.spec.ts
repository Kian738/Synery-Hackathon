import { test, expect } from "@playwright/test";

/** Cardboard VR on a (simulated) phone in landscape: mocked DeviceOrientationEvent + iOS-style requestPermission.
 *  Proves wiring, not comfort: real gyro signs, drift, lens fit, iOS fullscreen and wake lock need a real phone. */
test.use({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });

const ROUTE = "/?building=proc-factory-dev-003&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10";

test("Cardboard VR: permission from the click, head pose drives the camera, two eyes, tap = next step", async ({ page }) => {
  test.setTimeout(90_000);
  await page.addInitScript(() => {
    const w = window as any;
    w.__asked = 0;
    w.DeviceOrientationEvent.requestPermission = async () => { w.__asked++; return "granted"; };
    w.__pose = (alpha: number, beta: number, gamma: number) => window.dispatchEvent(new DeviceOrientationEvent("deviceorientation", { alpha, beta, gamma }));
  });
  await page.goto(ROUTE);
  await page.getByRole("button", { name: "Guide me step by step" }).click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Cardboard VR" }).click();
  await expect(page.getByRole("dialog", { name: "Cardboard VR" })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__asked)).toBe(0);   // nothing is requested before the user starts
  await page.getByRole("button", { name: "Start" }).click();
  expect(await page.evaluate(() => (window as any).__asked)).toBe(1);

  const angle = await page.evaluate(() => screen.orientation?.angle ?? 0);
  const level: Record<number, [number, number]> = { 0: [90, 0], 90: [0, -90], 180: [-90, 0], 270: [0, 90] };
  const [beta, gamma] = level[angle] ?? [90, 0];
  const canvas = page.locator("canvas").first();
  const quat = async () => JSON.parse((await canvas.getAttribute("data-camera-quaternion")) ?? "[0,0,0,1]") as number[];
  const forward = (q: number[]) => { const [x, y, z, w] = q; return [-(2 * (x * z + w * y)), -(2 * (y * z - w * x)), -(1 - 2 * (x * x + y * y))]; };
  const up = (q: number[]) => { const [x, y, z, w] = q; return [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)]; };

  await page.evaluate(([b, g]) => (window as any).__pose(10, b, g), [beta, gamma]);
  const surface = page.getByTestId("cardboard-surface");
  await expect(surface).toBeVisible();
  await expect(canvas).toHaveAttribute("data-stereo", "cardboard");
  await page.waitForTimeout(400);
  const q0 = await quat();
  expect(up(q0)[1]).toBeGreaterThan(0.99);   // level pose -> level horizon (route pitch is not applied)
  // turn the head 30 degrees left
  await page.evaluate(([b, g]) => (window as any).__pose(40, b, g), [beta, gamma]);
  await page.waitForTimeout(400);
  const f0 = forward(q0), f1 = forward(await quat());
  const turned = (Math.atan2(-f1[0], -f1[2]) - Math.atan2(-f0[0], -f0[2])) * 180 / Math.PI;
  expect(((turned + 540) % 360) - 180).toBeCloseTo(30, 0);

  // parallax: left and right halves differ but are the same scene
  const shot = await canvas.screenshot();
  const halves = await page.evaluate(async (b64) => {
    const img = new Image(); img.src = `data:image/png;base64,${b64}`; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; const x = c.getContext("2d")!; x.drawImage(img, 0, 0);
    const w = Math.floor(img.width / 2), a = x.getImageData(0, 0, w, img.height).data, b = x.getImageData(w, 0, w, img.height).data;
    let diff = 0, lit = 0; for (let i = 0; i < a.length; i += 4) { diff += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]); lit += a[i] + a[i + 1]; }
    return { diff: diff / (a.length / 4), lit: lit / (a.length / 4) };
  }, shot.toString("base64"));
  expect(halves.lit).toBeGreaterThan(10);
  expect(halves.diff).toBeGreaterThan(0.5);

  // tap = next step
  const count = page.locator(".k-guide-count");
  const before = await count.textContent();
  await surface.click({ position: { x: 600, y: 300 } });
  await expect(count).not.toHaveText(before ?? "", { timeout: 5_000 });

  await page.getByRole("button", { name: "Exit" }).click();
  await expect(surface).toHaveCount(0);
  await expect(canvas).not.toHaveAttribute("data-stereo", "cardboard");
});

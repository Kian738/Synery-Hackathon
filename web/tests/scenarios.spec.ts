import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const campus = "/?building=proc-campus-dev-000";
const shots = path.resolve("../runs/scenarios");
const open = async (page: Page) => {
  await page.goto(campus);
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
};

test("Building tools has one Scenarios entry instead of three tests", async ({ page }) => {
  await page.goto(campus);
  await page.getByLabel("Building tools", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Scenarios", exact: true })).toHaveCount(1);
  for (const old of ["Fire test", "Evacuation test", "Stress test"]) await expect(page.getByRole("button", { name: old, exact: true })).toHaveCount(0);
});

test("one scenario at a time, one shared scrubber, people dots in 3D", async ({ page }) => {
  await open(page);
  const chips = page.getByRole("group", { name: "Scenario" });
  await expect(chips.getByRole("button", { name: "Fire in a room" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  await expect(page.locator(".scenario-headline")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByLabel("Scenario results")).toContainText("Worst bottleneck");
  await expect(page.getByText(/No smoke or fire spread is modelled/)).toBeVisible();
  await expect(page.locator("[data-scrubber=shared]")).toHaveCount(1);
  const scene = page.getByTestId("building-scene");
  await expect.poll(async () => Number(await scene.getAttribute("data-scenario-dots") ?? 0), { timeout: 20_000 }).toBeGreaterThan(0);
  await fs.mkdir(shots, { recursive: true });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(shots, `${test.info().project.name}-${page.viewportSize()!.width}-fire.png`) });

  await chips.getByRole("button", { name: "Crowd surge" }).click();
  await expect(page.locator(".k-sheet.scenario")).toHaveCount(0);
  const stress = page.getByRole("region", { name: "Evacuation stress test" });
  await expect(stress.getByText("95 % out")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("[data-scrubber=shared]")).toHaveCount(1);
  await expect(scene).toHaveAttribute("data-scenario-kind", "rooms");

  await page.getByRole("button", { name: "Lift/stair outage" }).click();
  await expect(stress).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Building stress test" })).toBeVisible();
  await page.getByRole("button", { name: "Close stress test" }).click();
  await expect(page.getByRole("group", { name: "Scenario" })).toHaveCount(0);
  await expect(scene).not.toHaveAttribute("data-scenario-kind", /./);
});

test("on a phone the Scenarios sheet fits and the scrubber is reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  await expect(page.locator(".scenario-headline")).toBeVisible({ timeout: 90_000 });
  const box = (await page.locator(".k-sheet.scenario").boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(391);
  await expect(page.getByRole("group", { name: "Scenario" })).toBeVisible();
  await page.getByRole("slider", { name: "Replay time" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("slider", { name: "Replay time" })).toBeInViewport();
  await fs.mkdir(shots, { recursive: true });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(shots, "phone-390-fire.png") });
});

import { expect, test } from "@playwright/test";

const CAMPUS = "/?building=proc-campus-dev-000";

test("the fix card names the door and shows the checked before and after counts", async ({ page }) => {
  await page.route("**/api/sessions/*/chat", async (route) => {
    const session = route.request().url().split("/").at(-2);
    const result = await page.request.post(`/api/sessions/${session}/route`, { data: { start: "Main lobby", destination: "Print room 0.16", step_free: true, min_door_width_m: 1.1 } });
    const body = await result.json();
    await route.fulfill({ contentType: "text/event-stream", body: body.events.map((data: unknown) => `data: ${JSON.stringify({ type: "ui", data })}\n\n`).join("") + 'data: {"type":"done","data":null}\n\n' });
  });
  await page.goto(CAMPUS);
  await page.getByRole("textbox", { name: "Message" }).fill("Can a 1.1 metre trolley reach the print room?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const card = page.getByText(/Rooms reachable from here/);
  await expect(card).toBeVisible();
  await expect(card).toContainText("from 0.9 m to 1.1 m");
  await expect(card).toContainText(/\d+ of \d+ now, \d+ of \d+ after/);
});

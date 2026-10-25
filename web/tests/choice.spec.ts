import { expect, test } from "@playwright/test";

test("an ambiguous name becomes tappable options and the tapped option is sent as the answer", async ({ page }) => {
  const options = ["next to Flur, with 4 desks", "on the top-right of the plan"];
  const sent: string[] = [];
  await page.route("**/api/sessions/*/chat", async route => {
    sent.push(JSON.parse(route.request().postData() ?? "{}").text);
    const first = sent.length === 1;
    const events = first
      ? [{ type: "ui", data: { type: "choice", question: "Which Büro do you mean?", options } }, { type: "done", data: null }]
      : [{ type: "reply", data: { text: "Taking you to that one.", usage: {}, model: "test" } }, { type: "done", data: null }];
    await route.fulfill({ contentType: "text/event-stream", body: events.map(e => `data: ${JSON.stringify(e)}\n\n`).join("") });
  });
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("textbox", { name: "Message" }).fill("take me to the Büro");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Which Büro do you mean?")).toBeVisible();
  await page.getByRole("button", { name: /next to Flur/ }).click();
  await expect(page.getByText("Taking you to that one.")).toBeVisible();
  expect(sent).toEqual(["take me to the Büro", options[0]]);
});

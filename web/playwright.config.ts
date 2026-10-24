import { defineConfig } from "@playwright/test";

// Runs against the built app served by FastAPI (uv run fw start) on :8000, using the installed Chrome.
export default defineConfig({
  testDir: "tests",
  timeout: 30_000,
  // One uvicorn process serves every worker and the lab pages load 280 buildings: failures seen only at full parallelism, never alone.
  expect: { timeout: 15_000 },
  workers: 4,
  use: { baseURL: process.env.FLOORWISE_URL ?? "http://localhost:8000", channel: "chrome", headless: true },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  reporter: [["list"]],
});

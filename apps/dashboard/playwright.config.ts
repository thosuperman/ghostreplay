import { defineConfig, devices } from "@playwright/test";

// Runs against the one-process gateway (both labs + built dashboard) on a fresh store,
// or against an existing deployment when E2E_BASE_URL is set.
const external = process.env.E2E_BASE_URL;
const port = Number(process.env.E2E_PORT ?? 8199);
const baseURL = external ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : {
        command: `uv run --directory ../.. ghostreplay serve --port ${port} --db .ghostreplay/e2e-${Date.now()} --dashboard apps/dashboard/dist`,
        url: `${baseURL}/api/health`,
        reuseExistingServer: false,
        timeout: 60_000,
      },
});

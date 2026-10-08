import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: process.env.CI ? 600_000 : 240_000,
  reporter: [["list"], ["json", { outputFile: "artifacts/playwright.json" }]],
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:4179",
    locale: "en-US",
    timezoneId: "UTC",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium-engine", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox-engine", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit-engine", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: "node server.mjs",
    url: "http://127.0.0.1:4179",
    reuseExistingServer: !process.env.CI,
  },
});

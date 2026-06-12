const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/playwright/e2ee",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: process.env.CI ? 60_000 : 30_000,
  reporter: [["list"]],
  outputDir: "test-results/playwright-e2ee",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8080",
    browserName: "chromium",
    locale: "en-US",
    timezoneId: "UTC",
  },
});

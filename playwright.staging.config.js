const { defineConfig } = require("@playwright/test");

if (!process.env.PLAYWRIGHT_BASE_URL) {
  throw new Error("PLAYWRIGHT_BASE_URL is required for staging smoke tests");
}

module.exports = defineConfig({
  testDir: "./tests/playwright/staging",
  fullyParallel: false,
  forbidOnly: true,
  retries: 1,
  timeout: 60_000,
  reporter: [["list"]],
  outputDir: "test-results/playwright-staging",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    browserName: "chromium",
    locale: "en-US",
    timezoneId: "UTC",
  },
});

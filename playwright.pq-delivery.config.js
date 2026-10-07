const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/playwright/e2ee",
  testMatch: "client-side-encryption.spec.js",
  grep: /protected delivery retries/u,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: process.env.CI ? 120_000 : 90_000,
  reporter: [
    ["line"],
    ["json", { outputFile: "test-results/pq-delivery/results.json" }],
  ],
  outputDir: "test-results/pq-delivery/artifacts",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8080",
    locale: "en-US",
    timezoneId: "UTC",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    {
      name: "webkit-mobile-emulation",
      use: { ...devices["iPhone 15"] },
    },
  ],
});

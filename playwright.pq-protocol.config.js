const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/playwright/pq-protocol",
  timeout: process.env.CI ? 300_000 : 120_000,
  fullyParallel: false,
  workers: 1,
  webServer: {
    command: "node tests/playwright/pq-protocol/server.mjs",
    port: 4180,
    reuseExistingServer: false,
  },
  use: {
    baseURL: "http://127.0.0.1:4180",
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});

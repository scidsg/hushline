const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/playwright/pq-state",
  timeout: 30000,
  fullyParallel: true,
  use: {
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
